import asyncio
import base64
import json
import re
from datetime import date, datetime, time, timedelta, timezone
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from report import QUERY, SHEET_HEADERS, transform_orders


def setting(env, name, default=""):
    value = getattr(env, name, None)
    return value if isinstance(value, str) and value else default


def configuration(env):
    required = ("SHOPIFY_STORE", "GOOGLE_SHEET_ID", "GOOGLE_SERVICE_ACCOUNT_JSON")
    missing = [name for name in required if not setting(env, name)]
    client_id = setting(env, "SHOPIFY_CLIENT_ID")
    client_secret = setting(env, "SHOPIFY_CLIENT_SECRET")
    if client_id or client_secret:
        missing.extend(name for name in ("SHOPIFY_CLIENT_ID", "SHOPIFY_CLIENT_SECRET") if not setting(env, name))
    elif not setting(env, "SHOPIFY_ACCESS_TOKEN"):
        missing.append("SHOPIFY_ACCESS_TOKEN or both SHOPIFY_CLIENT_ID and SHOPIFY_CLIENT_SECRET")
    if missing:
        raise ValueError("Missing Worker settings: " + ", ".join(missing))
    store = setting(env, "SHOPIFY_STORE").strip()
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9-]*\.myshopify\.com", store):
        raise ValueError("SHOPIFY_STORE must be a myshopify.com hostname without https:// or paths")
    sheet_id = setting(env, "GOOGLE_SHEET_ID").strip()
    if not re.fullmatch(r"[a-zA-Z0-9_-]+", sheet_id):
        raise ValueError("GOOGLE_SHEET_ID must be the spreadsheet ID, not its URL")
    try:
        credentials = json.loads(setting(env, "GOOGLE_SERVICE_ACCOUNT_JSON"))
    except (ValueError, TypeError):
        raise ValueError("GOOGLE_SERVICE_ACCOUNT_JSON must contain the full service account JSON") from None
    if not isinstance(credentials, dict) or not all(
        isinstance(credentials.get(key), str) and credentials[key]
        for key in ("client_email", "private_key")
    ):
        raise ValueError("Google service account JSON needs client_email and private_key")
    store_timezone = setting(env, "SHOPIFY_STORE_TIMEZONE", "Europe/London")
    store_tz = ZoneInfo(store_timezone)
    report_date = date.fromisoformat(
        setting(env, "REPORT_DATE") or datetime.now(store_tz).date().isoformat()
    )
    start = datetime.combine(report_date, time.min, store_tz)
    end = datetime.combine(report_date + timedelta(days=1), time.min, store_tz)
    query = (
        f"created_at:>='{start.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}' "
        f"created_at:<'{end.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}'"
    )
    return {
        "store": store,
        "shopify_token": setting(env, "SHOPIFY_ACCESS_TOKEN"),
        "client_id": client_id,
        "client_secret": client_secret,
        "sheet_id": sheet_id,
        "credentials": credentials,
        "timezone": store_timezone,
        "report_date": report_date.isoformat(),
        "query": query,
        "excluded_skus": {
            sku.strip().casefold()
            for sku in setting(env, "EXCLUDED_LINEITEM_SKUS").split(",") if sku.strip()
        },
    }


async def request_json(url, *, method="GET", headers=None, body=None):
    from workers import fetch

    async def send():
        response = await fetch(url, method=method, headers=headers or {}, body=body)
        if not response.ok:
            hints = {
                400: "Check the request and credential format",
                401: "Check the access token or service account key",
                403: "Check API permissions; enable Google Sheets API and share the sheet with the service account as Editor",
                404: "Check the store hostname or spreadsheet ID and sharing",
                429: "API rate limit reached; retry later",
            }
            # Never log API response bodies: they may contain customer data or credentials.
            raise RuntimeError(f"HTTP {response.status}: {hints.get(response.status, 'Upstream API request failed')}")
        return await response.json()

    return await asyncio.wait_for(send(), timeout=60)


def base64url(value):
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


async def google_access_token(credentials):
    from js import Object, Uint8Array, crypto
    from pyodide.ffi import to_js

    def js_object(value):
        return to_js(value, dict_converter=Object.fromEntries)

    def js_bytes(value):
        return Uint8Array.new(to_js(list(value)))

    now = int(datetime.now(timezone.utc).timestamp())
    header = base64url(json.dumps({"alg": "RS256", "typ": "JWT"}).encode())
    claims = base64url(json.dumps({
        "iss": credentials["client_email"],
        "scope": "https://www.googleapis.com/auth/spreadsheets",
        "aud": "https://oauth2.googleapis.com/token",
        "iat": now,
        "exp": now + 3600,
    }).encode())
    signing_input = f"{header}.{claims}"
    pem = credentials["private_key"]
    key_bytes = base64.b64decode("".join(
        line for line in pem.splitlines() if not line.startswith("-----")
    ), validate=True)
    key = await crypto.subtle.importKey(
        "pkcs8", js_bytes(key_bytes),
        js_object({"name": "RSASSA-PKCS1-v1_5", "hash": "SHA-256"}),
        False, to_js(["sign"]),
    )
    signature = await crypto.subtle.sign(
        "RSASSA-PKCS1-v1_5", key, js_bytes(signing_input.encode())
    )
    assertion = signing_input + "." + base64url(bytes(Uint8Array.new(signature).to_py()))
    result = await request_json(
        "https://oauth2.googleapis.com/token", method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        body=urlencode({
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
            "assertion": assertion,
        }),
    )
    if not result.get("access_token"):
        raise RuntimeError("Google did not return an access token")
    return result["access_token"]


async def shopify_access_token(config):
    if not config["client_id"]:
        return config["shopify_token"]
    result = await request_json(
        f"https://{config['store']}/admin/oauth/access_token",
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        body=urlencode({
            "grant_type": "client_credentials",
            "client_id": config["client_id"],
            "client_secret": config["client_secret"],
        }),
    )
    token = result.get("access_token")
    if not isinstance(token, str) or not token:
        raise RuntimeError("Shopify did not return an access token; check app installation and organization ownership")
    return token


async def fetch_orders(config):
    orders = []
    cursor = None
    while True:
        result = await request_json(
            f"https://{config['store']}/admin/api/2026-10/graphql.json",
            method="POST",
            headers={"Content-Type": "application/json", "X-Shopify-Access-Token": config["shopify_token"]},
            body=json.dumps({"query": QUERY, "variables": {
                "first": 100, "after": cursor, "query": config["query"],
            }}),
        )
        if result.get("errors"):
            codes = sorted({error.get("extensions", {}).get("code", "GRAPHQL_ERROR") for error in result["errors"]})
            raise RuntimeError("Shopify GraphQL errors: " + ", ".join(codes) + "; check query fields and token scopes")
        page = result["data"]["orders"]
        orders.extend(page["nodes"])
        print(json.dumps({"stage": "shopify_page", "orders": len(orders)}))
        info = page["pageInfo"]
        if not info["hasNextPage"]:
            return orders
        next_cursor = info.get("endCursor")
        if not next_cursor or next_cursor == cursor:
            raise RuntimeError("Shopify pagination did not advance; sheet was not updated")
        cursor = next_cursor


def sheet_update(properties, rows):
    values = [SHEET_HEADERS] + rows
    grid = properties["gridProperties"]
    requests = []
    if grid["rowCount"] < len(values) or grid["columnCount"] < len(SHEET_HEADERS):
        requests.append({"updateSheetProperties": {
            "properties": {"sheetId": properties["sheetId"], "gridProperties": {
                "rowCount": max(grid["rowCount"], len(values)),
                "columnCount": max(grid["columnCount"], len(SHEET_HEADERS)),
            }},
            "fields": "gridProperties.rowCount,gridProperties.columnCount",
        }})
    # A full-sheet range clears stale values in the same atomic request as the new rows.
    requests.append({"updateCells": {
        "range": {"sheetId": properties["sheetId"]},
        "rows": [{"values": [
            {"userEnteredValue": {"stringValue": str(value) if value is not None else ""}}
            for value in row
        ]} for row in values],
        "fields": "userEnteredValue",
    }})
    return {"requests": requests}


async def run_sync(env):
    stage = "configuration"
    print(json.dumps({"stage": "sync_started"}))
    try:
        config = configuration(env)
        print(json.dumps({"stage": "configuration_checked", "report_date": config["report_date"], "timezone": config["timezone"]}))
        stage = "google_authentication"
        token = await google_access_token(config["credentials"])
        print(json.dumps({"stage": "google_authenticated"}))
        headers = {"Authorization": "Bearer " + token, "Content-Type": "application/json"}
        sheet_url = f"https://sheets.googleapis.com/v4/spreadsheets/{config['sheet_id']}"
        stage = "google_sheet_access"
        metadata = await request_json(sheet_url + "?fields=sheets(properties)", headers=headers)
        properties = min(metadata["sheets"], key=lambda sheet: sheet["properties"]["index"])["properties"]
        if properties.get("sheetType", "GRID") != "GRID":
            raise ValueError("The first spreadsheet tab must be a regular grid sheet")
        print(json.dumps({"stage": "google_sheet_access_checked"}))
        stage = "shopify_authentication"
        config["shopify_token"] = await shopify_access_token(config)
        print(json.dumps({"stage": "shopify_authenticated"}))
        stage = "shopify_fetch"
        orders = await fetch_orders(config)
        stage = "transform_orders"
        rows = transform_orders(orders, config["timezone"], config["excluded_skus"])
        print(json.dumps({"stage": "rows_prepared", "orders": len(orders), "rows": len(rows)}))
        stage = "google_sheet_write"
        await request_json(sheet_url + ":batchUpdate", method="POST", headers=headers,
                           body=json.dumps(sheet_update(properties, rows)))
        result = {"stage": "sync_completed", "report_date": config["report_date"], "orders": len(orders), "rows": len(rows)}
        print(json.dumps(result))
        return result
    except Exception as exc:
        # Only our validation/API errors have messages known to exclude secrets and customer data.
        detail = str(exc) if isinstance(exc, (ValueError, RuntimeError)) else type(exc).__name__
        print(json.dumps({"stage": "sync_failed", "failed_stage": stage, "error": detail}))
        raise RuntimeError(f"Report sync failed at {stage}; check Worker logs") from None

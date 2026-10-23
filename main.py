import os
import requests
from dotenv import load_dotenv
import json
from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo
import gspread
from google.oauth2.service_account import Credentials
from importlib import import_module

load_dotenv()

# The Worker bundles this same report module; keep CSV formatting in one place.
_report = import_module("shopify-order-sync.src.report")
QUERY = _report.QUERY
SHEET_HEADERS = _report.SHEET_HEADERS
_transform_orders = _report.transform_orders

GOOGLE_CREDENTIALS_FILE = "credentials/auto-line-item-zero-866d936fdaf3.json"

def write_to_google_sheet(rows):
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]

    credentials = Credentials.from_service_account_file(
        GOOGLE_CREDENTIALS_FILE,
        scopes=scopes,
    )

    client = gspread.authorize(credentials)

    spreadsheet = client.open_by_key(
        os.getenv("GOOGLE_SHEET_ID")
    )

    worksheet = spreadsheet.sheet1

    # Clear existing test data
    worksheet.clear()

    # Write headers
    worksheet.update(
        range_name="A1",
        values=[SHEET_HEADERS],
    )

    # Write transformed Shopify data
    if rows:
        worksheet.update(
            range_name="A2",
            values=rows,
        )

    print(
        f"Uploaded {len(rows)} rows to Google Sheets"
    )


STATE_FILE = "sync_state.json"

def load_last_sync():
    if not os.path.exists(STATE_FILE):
        return None

    with open(STATE_FILE, "r") as f:
        state = json.load(f)
        last_sync_str = state.get("last_sync")
    return last_sync_str

def save_lasr_sync(sync_time):
    with open(STATE_FILE, "w") as file:
        json.dump(
            {
                "last_sync": sync_time
            },
            file,
            indent=4
        )

SHOPIFY_STORE = os.getenv("SHOPIFY_STORE")
SHOPIFY_ACCESS_TOKEN = os.getenv("SHOPIFY_ACCESS_TOKEN")

API_VERSION = "2026-10"
STORE_TIMEZONE = os.getenv("SHOPIFY_STORE_TIMEZONE", "Europe/London")
EXCLUDED_LINEITEM_SKUS = {
    sku.strip().casefold()
    for sku in os.getenv("EXCLUDED_LINEITEM_SKUS", "").split(",")
    if sku.strip()
}

URL = f"https://{SHOPIFY_STORE}/admin/api/{API_VERSION}/graphql.json"

HEADERS = {
    "Content-Type": "application/json",
    "X-Shopify-Access-Token": SHOPIFY_ACCESS_TOKEN,
}


def fetch_orders():
    orders = []
    cursor = None
    # last_sync = load_last_sync()
    # print(f"Last sync: {last_sync}" )
    # if last_sync:
    #     shopify_query = f"updated_at:>{last_sync}"
    # else:
    #     shopify_query = None

    report_date = date.fromisoformat(
        os.getenv("REPORT_DATE")
        or datetime.now(ZoneInfo(STORE_TIMEZONE)).date().isoformat()
    )
    store_tz = ZoneInfo(STORE_TIMEZONE)
    start = datetime.combine(report_date, time.min, store_tz)
    end = datetime.combine(report_date.fromordinal(report_date.toordinal() + 1), time.min, store_tz)
    start_utc = start.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    end_utc = end.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    shopify_query = f"created_at:>='{start_utc}' created_at:<'{end_utc}'"

    print(f"Fetching orders from: {shopify_query}")

    while True:

        variables = {
            "first": 100,
            "after": cursor,
            "query": shopify_query
        }

        response = requests.post(
            URL,
            headers=HEADERS,
            json={
                "query": QUERY,
                "variables": variables,
            },
        )

        response.raise_for_status()

        result = response.json()

        if "errors" in result:
            print("Shopify API errors:")
            print(result["errors"])
            raise Exception("Shopify API request failed")

        order_data = result["data"]["orders"]

        current_orders = order_data["nodes"]

        orders.extend(current_orders)

        print(
            f"Fetched {len(current_orders)} orders | "
            f"Total: {len(orders)}"
        )

        page_info = order_data["pageInfo"]

        if not page_info["hasNextPage"]:
            break

        cursor = page_info["endCursor"]

    return orders



def transform_orders(orders):
    return _transform_orders(orders, STORE_TIMEZONE, EXCLUDED_LINEITEM_SKUS)


if __name__ == "__main__":
    orders = fetch_orders()

    print(f"\nTotal orders fetched: {len(orders)}")

    rows = transform_orders(orders)

    print(f"Total sheet rows generated: {len(rows)}")

    write_to_google_sheet(rows)

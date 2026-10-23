# Shopify order report on Cloudflare

The scheduled Worker fetches orders for the selected calendar day in the store's
timezone, applies the same formatting as the local `main.py` script, and replaces
the values in the spreadsheet's first tab. An empty report writes headers only.
Sheet values are replaced atomically after all orders have been fetched.

## Worker settings

Configure these in Cloudflare under the Worker's Settings → Variables and Secrets
(runtime settings, not build settings):

| Name | Type | Value |
| --- | --- | --- |
| `SHOPIFY_STORE` | Text | Store hostname ending in `.myshopify.com`; already in `wrangler.jsonc` |
| `SHOPIFY_CLIENT_ID` | Text or Secret | Dev Dashboard app's client ID; use together with its client secret |
| `SHOPIFY_CLIENT_SECRET` | Secret | Dev Dashboard app's client secret; exchanged for an access token once per report run |
| `SHOPIFY_ACCESS_TOKEN` | Secret, alternative | An actual Admin API token if not using client credentials; never put the client secret here |
| `GOOGLE_SHEET_ID` | Text | Spreadsheet ID, not its URL |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | Secret | Full Google service account JSON, including `client_email` and `private_key` |
| `SHOPIFY_STORE_TIMEZONE` | Text, optional | Defaults to `Europe/London`; use the store's timezone |
| `EXCLUDED_LINEITEM_SKUS` | Text, optional | Comma-separated SKUs to exclude |
| `REPORT_DATE` | Text, optional | `YYYY-MM-DD` override; leave unset for the current date in the store's timezone |
| `SYNC_TRIGGER_TOKEN` | Secret, optional | A long random token for manually running `POST /sync` |

Enable Google Sheets API for the service account's project and share the target
spreadsheet with its `client_email` as Editor. Secrets are never included in logs.
`keep_vars` retains dashboard variables on subsequent Wrangler deployments.

Client credentials take precedence over `SHOPIFY_ACCESS_TOKEN` when configured.
Both must be set, and the app must be installed on a store in the same Shopify
organization. The Worker obtains a new access token for each report run, avoiding
reuse of an expired 24-hour token. Apps installed on other merchants' stores need
the OAuth authorization flow instead of a client credentials grant.

## Deploy

Run from this directory:

```powershell
npm install
uv sync
npx wrangler login
npm run deploy
```

The existing cron `30 21 * * *` runs daily at 21:30 UTC, or 03:00 IST the next day.
The report uses the current calendar date in `SHOPIFY_STORE_TIMEZONE`, matching
the local script; it does not automatically select yesterday.

## Verify immediately

Add a `SYNC_TRIGGER_TOKEN` secret if you want to run a report without waiting:

```powershell
npx wrangler secret put SYNC_TRIGGER_TOKEN
npx wrangler tail
```

In another PowerShell window, replace the URL and enter that same token:

```powershell
$syncToken = Read-Host 'SYNC_TRIGGER_TOKEN' -AsSecureString
$syncCredential = [System.Net.NetworkCredential]::new('', $syncToken)
Invoke-RestMethod -Method Post -Uri 'https://YOUR-WORKER.workers.dev/sync' -Headers @{
    Authorization = 'Bearer ' + $syncCredential.Password
}
```

This writes the report to the first spreadsheet tab, replacing its current values.
Success returns `stage: sync_completed`, `report_date`, `orders`, and `rows`.
Opening `/` in a browser only checks the status page and does not change the sheet.
Unauthenticated requests to `/sync` cannot run a report.

Logs record configuration checks, Google authentication and sheet access, Shopify
page counts, prepared row counts, and completion. A failure includes `failed_stage`
and a safe error description. HTTP 401 indicates a credential problem; Google
403 usually indicates API access or spreadsheet sharing; Shopify `ACCESS_DENIED`
indicates token permissions. Use the logged stage to identify the affected service.

For local development, store runtime settings in an ignored `.dev.vars` file in
this directory, then run `npm run dev`. Invoke the local scheduled handler with
`curl.exe 'http://localhost:8787/cdn-cgi/local/scheduled?format=json'`.
Do not use production sheet credentials locally unless you intend to replace its data.

## Checks

From the repository root:

```powershell
.\.venv\Scripts\python.exe -m unittest test_main test_worker -v
```

From this directory, `npm run deploy -- --dry-run` checks the deployment bundle
without publishing it. Unit tests mock external APIs and do not write to a sheet.

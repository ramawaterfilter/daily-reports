# Shopify order report on Cloudflare

The scheduled Worker fetches orders from October 1, 2026 in the store's timezone
through the time each report starts, applies the same formatting as the local `main.py` script, and replaces
the values in the selected spreadsheet tab (the first tab when no name is configured). An empty report writes headers only.
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
| `GOOGLE_SHEET_TAB_ID` | Text, recommended | Numeric `gid` from the tab URL, including `0`; remains valid after renaming |
| `GOOGLE_SHEET_TAB` | Text, optional | Legacy selection by exact tab name; used only when no tab ID is set |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | Secret | Full Google service account JSON, including `client_email` and `private_key` |
| `SHOPIFY_STORE_TIMEZONE` | Text, optional | Defaults to `Europe/London`; use the store's timezone |
| `EXCLUDED_LINEITEM_SKUS` | Text, optional | Comma-separated SKUs to exclude |
| `REPORT_START_DATE` | Text | `2026-10-01`, configured in `wrangler.jsonc`; cumulative report starting at midnight in the store's timezone |
| `REPORT_DATE` | Text, optional | Single-day override only when `REPORT_START_DATE` is absent; remove it for cumulative reports |
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
Each run rebuilds the full report from `REPORT_START_DATE` through the run time,
including any orders already placed that day. Rows are replaced, so reruns do not
append duplicates and existing orders' current statuses are refreshed. The store
timezone controls the October 1 boundary and date formatting, while cron stays
fixed to 03:00 IST regardless of daylight saving changes in London.

The variable `START_DAT` is not used; set `REPORT_START_DATE` instead. Remove a
previously configured `REPORT_DATE` to avoid freezing the report to one day.

### Check a scheduled execution

After deployment, verify Settings → Trigger Events lists `30 21 * * *` and select
View events to inspect the scheduled invocation and its outcome. The cron may
have fired even when a report failed. Logs start with `cron_triggered` (including
the scheduled timestamp), followed by the normal sync stages. Trigger changes can
take up to 15 minutes to propagate. Live `wrangler tail` only shows new events
while connected, so use the dashboard for overnight execution history.

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

This writes the report to the selected spreadsheet tab, replacing its current values.
Success returns `stage: sync_completed`, `report_date`, `orders`, and `rows`.
Opening `/` in a browser only checks the status page and does not change the sheet.
Unauthenticated requests to `/sync` cannot run a report.

To target a particular tab, open it in Google Sheets and copy the number after
`gid=` in its URL. For `https://docs.google.com/spreadsheets/d/SPREADSHEET_ID/edit#gid=123456789`,
set the Text runtime variable `GOOGLE_SHEET_TAB_ID` to `123456789` in Cloudflare
and deploy this code. Keep `GOOGLE_SHEET_ID` as the ID of the whole spreadsheet.
Renaming or reordering the tab does not change this connection. A tab ID takes
precedence over `GOOGLE_SHEET_TAB`; when neither is set, the first tab is used.
If the selected tab is deleted or its ID is wrong, the report fails before writing
and never falls back to another tab. The access-check log shows the selected tab
name and numeric tab ID. Recreating a deleted tab requires updating the ID.

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

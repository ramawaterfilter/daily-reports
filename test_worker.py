import importlib
import io
import json
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).parent / "shopify-order-sync" / "src"))
sync = importlib.import_module("sync")


def environment(**overrides):
    values = dict(
        SHOPIFY_STORE="example.myshopify.com",
        SHOPIFY_ACCESS_TOKEN="private-shopify-token",
        GOOGLE_SHEET_ID="example-sheet-id",
        GOOGLE_SERVICE_ACCOUNT_JSON=json.dumps({
            "client_email": "example@example.iam.gserviceaccount.com",
            "private_key": "private-google-key",
        }),
        REPORT_DATE="2026-10-23",
    )
    return SimpleNamespace(**(values | overrides))


PROPERTIES = {"sheetId": 12, "index": 0, "gridProperties": {"rowCount": 1000, "columnCount": 100}}


class WorkerTests(unittest.IsolatedAsyncioTestCase):
    def test_cumulative_report_starts_october_first_and_ends_at_run_time(self):
        run_time = datetime(2026, 10, 23, 21, 30, tzinfo=timezone.utc)
        with patch.object(sync, "datetime", wraps=datetime) as clock:
            clock.now.return_value = run_time
            config = sync.configuration(environment(REPORT_DATE="", REPORT_START_DATE="2026-10-01"))
        self.assertEqual(config["query"], "created_at:>='2026-09-30T23:00:00Z' created_at:<'2026-10-23T21:30:00Z'")
        self.assertEqual(config["report_start_date"], "2026-10-01")
        self.assertEqual(config["report_end_at"], "2026-10-23T21:30:00Z")

    def test_cumulative_report_handles_london_daylight_saving_change(self):
        run_time = datetime(2026, 10, 25, 21, 30, tzinfo=timezone.utc)
        with patch.object(sync, "datetime", wraps=datetime) as clock:
            clock.now.return_value = run_time
            config = sync.configuration(environment(REPORT_DATE="", REPORT_START_DATE="2026-10-01"))
        self.assertEqual(config["query"], "created_at:>='2026-09-30T23:00:00Z' created_at:<'2026-10-25T21:30:00Z'")

    def test_cumulative_report_rejects_future_start_and_frozen_report_date(self):
        for overrides in (
            {"REPORT_DATE": "", "REPORT_START_DATE": "2099-10-01"},
            {"REPORT_DATE": "2026-10-23", "REPORT_START_DATE": "2026-10-01"},
            {"REPORT_DATE": "", "REPORT_START_DATE": "October 1"},
        ):
            with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                sync.configuration(environment(**overrides))

    async def test_client_credentials_exchange_takes_precedence_over_old_token(self):
        config = sync.configuration(environment(SHOPIFY_CLIENT_ID="client-id", SHOPIFY_CLIENT_SECRET="client-secret"))
        with patch.object(sync, "request_json", new=AsyncMock(return_value={"access_token": "fresh-token"})) as request:
            token = await sync.shopify_access_token(config)
        self.assertEqual(token, "fresh-token")
        self.assertEqual(request.call_args.args[0], "https://example.myshopify.com/admin/oauth/access_token")
        from urllib.parse import parse_qs
        self.assertEqual(parse_qs(request.call_args.kwargs["body"]), {
            "grant_type": ["client_credentials"], "client_id": ["client-id"], "client_secret": ["client-secret"],
        })

    async def test_static_token_needs_no_exchange(self):
        with patch.object(sync, "request_json", new=AsyncMock()) as request:
            self.assertEqual(await sync.shopify_access_token(sync.configuration(environment())), "private-shopify-token")
            request.assert_not_awaited()

    def test_credentials_pair_is_required_even_with_old_token(self):
        with self.assertRaisesRegex(ValueError, "SHOPIFY_CLIENT_SECRET"):
            sync.configuration(environment(SHOPIFY_CLIENT_ID="client-id"))
        config = sync.configuration(environment(SHOPIFY_ACCESS_TOKEN="", SHOPIFY_CLIENT_ID="id", SHOPIFY_CLIENT_SECRET="secret"))
        self.assertEqual(config["client_id"], "id")

    async def test_exchange_failure_is_logged_without_exposing_secret(self):
        output = io.StringIO()
        request = AsyncMock(side_effect=[{"sheets": [{"properties": PROPERTIES}]}, RuntimeError("HTTP 401")])
        with patch.object(sync, "google_access_token", new=AsyncMock(return_value="token")), \
             patch.object(sync, "request_json", new=request), redirect_stdout(output):
            with self.assertRaisesRegex(RuntimeError, "shopify_authentication"):
                await sync.run_sync(environment(SHOPIFY_CLIENT_ID="id", SHOPIFY_CLIENT_SECRET="private-client-secret"))
        self.assertEqual(request.await_count, 2)
        self.assertIn('"failed_stage": "shopify_authentication"', output.getvalue())
        self.assertNotIn("private-client-secret", output.getvalue())

    def test_configuration_requires_secrets(self):
        with self.assertRaisesRegex(ValueError, "SHOPIFY_ACCESS_TOKEN"):
            sync.configuration(environment(SHOPIFY_ACCESS_TOKEN=""))

    def test_configuration_date_timezone_and_exclusions(self):
        config = sync.configuration(environment(SHOPIFY_STORE_TIMEZONE="Asia/Kolkata", EXCLUDED_LINEITEM_SKUS=" TEST, xyz "))
        self.assertEqual(config["excluded_skus"], {"test", "xyz"})
        self.assertEqual(config["query"], "created_at:>='2026-10-22T18:30:00Z' created_at:<'2026-10-23T18:30:00Z'")

    def test_invalid_credentials_and_host(self):
        for overrides in (
            {"GOOGLE_SERVICE_ACCOUNT_JSON": "not-json"},
            {"GOOGLE_SERVICE_ACCOUNT_JSON": "[]"},
            {"SHOPIFY_STORE": "https://example.myshopify.com"},
            {"GOOGLE_SHEET_ID": "https://docs.google.com/spreadsheets/d/id/edit"},
        ):
            with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                sync.configuration(environment(**overrides))

    def test_sheet_write_clears_stale_values_atomically_and_uses_literal_text(self):
        body = sync.sheet_update(PROPERTIES, [["=1+1"]])
        self.assertEqual(len(body["requests"]), 1)
        update = body["requests"][0]["updateCells"]
        self.assertEqual(update["range"], {"sheetId": 12})
        self.assertEqual(update["fields"], "userEnteredValue")
        self.assertEqual(update["rows"][1]["values"][0], {"userEnteredValue": {"stringValue": "=1+1"}})

    def test_sheet_expands_before_write(self):
        body = sync.sheet_update(PROPERTIES | {"gridProperties": {"rowCount": 1, "columnCount": 1}}, [["x"]])
        resize = body["requests"][0]["updateSheetProperties"]["properties"]["gridProperties"]
        self.assertEqual(resize["rowCount"], 2)
        self.assertEqual(resize["columnCount"], len(sync.SHEET_HEADERS))

    async def test_fetch_paginates(self):
        pages = [
            {"data": {"orders": {"nodes": [{"id": "1"}], "pageInfo": {"hasNextPage": True, "endCursor": "next"}}}},
            {"data": {"orders": {"nodes": [{"id": "2"}], "pageInfo": {"hasNextPage": False}}}},
        ]
        with patch.object(sync, "request_json", new=AsyncMock(side_effect=pages)) as request:
            orders = await sync.fetch_orders(sync.configuration(environment()))
        self.assertEqual(len(orders), 2)
        self.assertEqual(json.loads(request.call_args.kwargs["body"])["variables"]["after"], "next")

    async def test_graphql_errors_do_not_write_sheet(self):
        with patch.object(sync, "request_json", new=AsyncMock(return_value={"errors": [{"extensions": {"code": "ACCESS_DENIED"}}]})):
            with self.assertRaisesRegex(RuntimeError, "ACCESS_DENIED"):
                await sync.fetch_orders(sync.configuration(environment()))

    async def test_success_logs_counts_and_writes_once(self):
        output = io.StringIO()
        request = AsyncMock(side_effect=[{"sheets": [{"properties": PROPERTIES}]}, {}])
        with patch.object(sync, "google_access_token", new=AsyncMock(return_value="secret-google-token")), \
             patch.object(sync, "fetch_orders", new=AsyncMock(return_value=[])), \
             patch.object(sync, "request_json", new=request), redirect_stdout(output):
            result = await sync.run_sync(environment())
        self.assertEqual(result["stage"], "sync_completed")
        self.assertEqual(result["rows"], 0)
        self.assertEqual(request.await_count, 2)
        self.assertEqual(request.call_args.kwargs["method"], "POST")
        self.assertNotIn("secret-google-token", output.getvalue())
        self.assertNotIn("private-google-key", output.getvalue())

    async def test_named_tab_is_selected_instead_of_first_tab(self):
        target = PROPERTIES | {"sheetId": 99, "index": 1, "title": "October's Orders"}
        request = AsyncMock(side_effect=[{"sheets": [
            {"properties": PROPERTIES | {"title": "Summary"}}, {"properties": target},
        ]}, {}])
        with patch.object(sync, "google_access_token", new=AsyncMock(return_value="token")), \
             patch.object(sync, "fetch_orders", new=AsyncMock(return_value=[])), \
             patch.object(sync, "request_json", new=request), redirect_stdout(io.StringIO()):
            await sync.run_sync(environment(GOOGLE_SHEET_TAB="October's Orders"))
        body = json.loads(request.call_args.kwargs["body"])
        self.assertEqual(body["requests"][-1]["updateCells"]["range"], {"sheetId": 99})

    async def test_missing_named_tab_fails_without_fetching_orders_or_writing(self):
        request = AsyncMock(return_value={"sheets": [{"properties": PROPERTIES | {"title": "Summary"}}]})
        output = io.StringIO()
        with patch.object(sync, "google_access_token", new=AsyncMock(return_value="token")), \
             patch.object(sync, "fetch_orders", new=AsyncMock()) as fetch_orders, \
             patch.object(sync, "request_json", new=request), redirect_stdout(output):
            with self.assertRaisesRegex(RuntimeError, "google_sheet_access"):
                await sync.run_sync(environment(GOOGLE_SHEET_TAB="Orders"))
        request.assert_awaited_once()
        fetch_orders.assert_not_awaited()
        self.assertIn("does not match an existing tab", output.getvalue())

    def test_tab_id_must_be_numeric(self):
        for value in ("-1", "1.5", "gid=123", "https://docs.google.com/spreadsheets/d/id/edit#gid=123"):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "numeric gid"):
                sync.configuration(environment(GOOGLE_SHEET_TAB_ID=value))

    async def test_tab_id_survives_rename_and_takes_precedence_over_name(self):
        for tab_id in (0, 99):
            with self.subTest(tab_id=tab_id):
                target = PROPERTIES | {"sheetId": tab_id, "index": 1, "title": "Accidentally renamed"}
                request = AsyncMock(side_effect=[{"sheets": [
                    {"properties": PROPERTIES | {"title": "Old tab name"}}, {"properties": target},
                ]}, {}])
                with patch.object(sync, "google_access_token", new=AsyncMock(return_value="token")), \
                     patch.object(sync, "fetch_orders", new=AsyncMock(return_value=[])), \
                     patch.object(sync, "request_json", new=request), redirect_stdout(io.StringIO()):
                    await sync.run_sync(environment(GOOGLE_SHEET_TAB_ID=str(tab_id), GOOGLE_SHEET_TAB="Old tab name"))
                body = json.loads(request.call_args.kwargs["body"])
                self.assertEqual(body["requests"][-1]["updateCells"]["range"], {"sheetId": tab_id})

    async def test_missing_tab_id_never_falls_back_to_name_or_first_tab(self):
        request = AsyncMock(return_value={"sheets": [{"properties": PROPERTIES | {"title": "Orders"}}]})
        with patch.object(sync, "google_access_token", new=AsyncMock(return_value="token")), \
             patch.object(sync, "fetch_orders", new=AsyncMock()) as fetch_orders, \
             patch.object(sync, "request_json", new=request), redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(RuntimeError, "google_sheet_access"):
                await sync.run_sync(environment(GOOGLE_SHEET_TAB_ID="999", GOOGLE_SHEET_TAB="Orders"))
        request.assert_awaited_once()
        fetch_orders.assert_not_awaited()

    async def test_shopify_failure_preserves_sheet_and_identifies_stage(self):
        output = io.StringIO()
        request = AsyncMock(return_value={"sheets": [{"properties": PROPERTIES}]})
        with patch.object(sync, "google_access_token", new=AsyncMock(return_value="token")), \
             patch.object(sync, "fetch_orders", new=AsyncMock(side_effect=RuntimeError("HTTP 401"))), \
             patch.object(sync, "request_json", new=request), redirect_stdout(output):
            with self.assertRaisesRegex(RuntimeError, "shopify_fetch"):
                await sync.run_sync(environment())
        self.assertEqual(request.await_count, 1)
        self.assertIn('"failed_stage": "shopify_fetch"', output.getvalue())

    async def test_manual_endpoint_requires_token_and_scheduled_runs_sync(self):
        fake_workers = SimpleNamespace(WorkerEntrypoint=object, Response=lambda body, **kwargs: SimpleNamespace(body=body, **kwargs))
        with patch.dict(sys.modules, {"workers": fake_workers}):
            entry = importlib.import_module("entry")
        worker = entry.Default()
        worker.env = environment(SYNC_TRIGGER_TOKEN="expected")
        request = SimpleNamespace(url="https://example.workers.dev/sync", method="POST", headers={})
        with patch.object(entry, "run_sync", new=AsyncMock()) as run:
            response = await worker.fetch(request)
            self.assertEqual(response.status, 401)
            run.assert_not_awaited()
            await worker.scheduled(SimpleNamespace(cron="30 21 * * *", scheduledTime=1792791000000), None, None)
            run.assert_awaited_once_with(worker.env)


if __name__ == "__main__":
    unittest.main()

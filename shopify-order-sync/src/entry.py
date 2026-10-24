import hmac
import json
from urllib.parse import urlsplit

from workers import Response, WorkerEntrypoint
from sync import run_sync, setting

class Default(WorkerEntrypoint):
    async def fetch(self, request):
        if urlsplit(request.url).path == "/sync":
            if request.method != "POST":
                return Response("Use POST with a Bearer token to run a report", status=405, headers={"Allow": "POST"})
            token = setting(self.env, "SYNC_TRIGGER_TOKEN")
            if not token:
                return Response("Configure the SYNC_TRIGGER_TOKEN Worker secret first", status=503)
            authorization = request.headers.get("Authorization", "")
            if not hmac.compare_digest(authorization.encode(), ("Bearer " + token).encode()):
                return Response("Unauthorized", status=401)
            try:
                return Response.from_json(await run_sync(self.env))
            except Exception:
                return Response("Report sync failed; check Worker logs for failed_stage", status=500)
        return Response("Shopify Order Sync Worker is running!")

    async def scheduled(self, controller, env, ctx):
        print(json.dumps({"stage": "cron_triggered", "cron": controller.cron, "scheduled_time_ms": controller.scheduledTime}))
        await run_sync(self.env)



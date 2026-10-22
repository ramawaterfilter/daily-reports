from workers import Response, WorkerEntrypoint

class Default(WorkerEntrypoint):
    async def fetch(self, request):
        return Response("Shopify Order Sync Worker is running!")

    async def scheduled(self, controller, env, ctx):
        print("Scheduled Shopify Order Sync test executed")
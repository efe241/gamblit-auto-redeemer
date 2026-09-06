"""
Mock Gamblit server for testing without contacting the live gamblit.net service.
Simulates success, expired, duplicate, level requirement, rate-limits, and server errors.
"""
from aiohttp import web
import asyncio


class MockGamblitServer:
    def __init__(self, host: str = "127.0.0.1", port: int = 8888):
        self.host = host
        self.port = port
        self.app = web.Application()
        self.runner = None
        self.site = None
        self._setup_routes()

    def _setup_routes(self):
        self.app.router.add_get("/api/user/me", self.handle_profile)
        self.app.router.add_post("/api/promo/redeem", self.handle_redeem)
        self.app.router.add_post("/api/codes/redeem", self.handle_redeem)

    async def handle_profile(self, request: web.Request) -> web.Response:
        # Check cookie presence
        cookies = request.cookies
        if not cookies.get("cf_clearance"):
            return web.json_response({"error": "Unauthorized / Cloudflare"}, status=403)

        return web.json_response({
            "user": {
                "id": "999888",
                "username": "GamblitProUser",
                "level": 125,
                "balance": 1500.0,
            }
        })

    async def handle_redeem(self, request: web.Request) -> web.Response:
        # Verify Cloudflare cookie
        if not request.cookies.get("cf_clearance"):
            return web.json_response({"error": "Missing cf_clearance cookie"}, status=403)

        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "Invalid JSON"}, status=400)

        code = str(body.get("code", "")).upper()

        if code == "SUCCESS2026":
            return web.json_response({
                "success": True,
                "message": "Promo code redeemed successfully!",
                "reward": "100 DL",
            }, status=200)

        elif code == "EXPIRED_CODE":
            return web.json_response({
                "success": False,
                "message": "This promo code has expired.",
            }, status=400)

        elif code == "ALREADY_USED":
            return web.json_response({
                "success": False,
                "message": "Promo code already redeemed by your account.",
            }, status=400)

        elif code == "HIGH_LEVEL":
            return web.json_response({
                "success": False,
                "message": "Account does not meet minimum level requirement.",
            }, status=400)

        elif code == "RATE_LIMIT_TEST":
            return web.json_response(
                {"message": "Too many requests. Please slow down."},
                status=429,
                headers={"Retry-After": "1"},
            )

        elif code == "SERVER_ERROR":
            return web.json_response({"error": "Database connection error"}, status=500)

        elif code == "TIMEOUT_SIM":
            await asyncio.sleep(4.0)
            return web.json_response({"message": "Too late"}, status=200)

        else:
            return web.json_response({
                "success": False,
                "message": "Invalid code. Does not exist.",
            }, status=400)

    async def start(self):
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, self.host, self.port)
        await self.site.start()

    async def stop(self):
        if self.runner:
            await self.runner.cleanup()

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

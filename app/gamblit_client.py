"""
High-performance Gamblit Client with dual WebSocket (MessagePack) and HTTP fallback.
- Primary: Persistent WebSocket to wss://ws.gamblit.net (sub-5ms round-trip via MessagePack).
- Fallback: HTTP ClientSession with connection pooling and cookie replay.
"""
import asyncio
import base64
import logging
import time
from typing import Dict, Any, Optional
import aiohttp
import msgpack
import websockets
from app.config import Config
from app.models import RedeemResult, RedeemStatus, RedeemLatency, AccountProfile

log = logging.getLogger("gamblit_redeemer.client")


class GamblitClient:
    def __init__(self, config: Config):
        self.config = config
        self._ws: Optional[Any] = None
        self._ws_lock = asyncio.Lock()
        self._profile: Optional[AccountProfile] = None
        self._connected = False
        self._listen_task: Optional[asyncio.Task] = None
        self._ping_task: Optional[asyncio.Task] = None
        self._pending_responses: Dict[str, asyncio.Future] = {}
        self._http_session: Optional[aiohttp.ClientSession] = None

    @property
    def ws_uri(self) -> str:
        return "wss://ws.gamblit.net"

    def _build_cookie_header(self) -> str:
        cookies = self.config.parsed_cookies
        return "; ".join([f"{k}={v}" for k, v in cookies.items()])

    async def get_http_session(self) -> aiohttp.ClientSession:
        """Returns or creates persistent HTTP session for fallback and profile checks."""
        if self._http_session is None or self._http_session.closed:
            connector = aiohttp.TCPConnector(limit=10, keepalive_timeout=60.0, ttl_dns_cache=300)
            jar = aiohttp.CookieJar(unsafe=True)
            timeout = aiohttp.ClientTimeout(
                sock_connect=self.config.connect_timeout_sec,
                sock_read=self.config.read_timeout_sec,
                total=self.config.connect_timeout_sec + self.config.read_timeout_sec + 2.0,
            )
            headers = {
                "User-Agent": self.config.gamblit_user_agent,
                "Accept": "application/json, text/plain, */*",
                "Origin": self.config.gamblit_base_url,
                "Referer": f"{self.config.gamblit_base_url}/",
            }
            self._http_session = aiohttp.ClientSession(
                connector=connector,
                cookie_jar=jar,
                headers=headers,
                timeout=timeout,
            )
            cookies = self.config.parsed_cookies
            if cookies:
                self._http_session.cookie_jar.update_cookies(
                    cookies,
                    response_url=aiohttp.client_reqrep.URL(self.config.gamblit_base_url),
                )
        return self._http_session

    get_session = get_http_session

    async def connect_ws(self) -> bool:
        """Establishes persistent WebSocket connection and authenticates."""
        async with self._ws_lock:
            if self._connected and self._ws:
                return True

            # If no cookies configured, skip WS
            if not self.config.parsed_cookies:
                return False

            cookie_header = self._build_cookie_header()
            # Dual-domain failover (gamblit.co is unblocked in TR; gamblit.net fallback)
            primary_co = "gamblit.co" in self.config.gamblit_base_url or "gamblit.co" in cookie_header
            ws_candidates = [
                ("wss://ws.gamblit.co", "https://gamblit.co"),
                ("wss://ws.gamblit.net", "https://gamblit.net"),
            ] if primary_co else [
                ("wss://ws.gamblit.co", "https://gamblit.co"),
                ("wss://ws.gamblit.net", "https://gamblit.net"),
            ]

            for target_ws_uri, target_origin in ws_candidates:
                headers = {
                    "User-Agent": self.config.gamblit_user_agent,
                    "Origin": target_origin,
                    "Cookie": cookie_header,
                }

                try:
                    log.debug(f"Connecting to Gamblit WebSocket ({target_ws_uri})...")
                    self._ws = await websockets.connect(
                        target_ws_uri,
                        additional_headers=headers,
                        open_timeout=4.0,
                        ping_interval=None,
                    )
                    self._connected = True
                    self._listen_task = asyncio.create_task(self._listen_loop())
                    self._ping_task = asyncio.create_task(self._ping_loop())

                    # Wait up to 3 seconds for UserData
                    for _ in range(20):
                        if self._profile and self._profile.is_authenticated:
                            log.info(f"✅ Gamblit WebSocket bağlandı! Giriş: '{self._profile.username}' (Bakiye: {self._profile.balance_dl} DL)")
                            return True
                        await asyncio.sleep(0.15)

                    if self._profile and self._profile.is_authenticated:
                        return True

                except Exception as e:
                    log.debug(f"WebSocket connect to {target_ws_uri} failed ({e}).")
                    if self._ws:
                        try:
                            await self._ws.close()
                        except Exception:
                            pass
                        self._ws = None
                    self._connected = False

            return self._profile.is_authenticated if self._profile else False

    async def _ping_loop(self):
        while self._connected:
            try:
                await asyncio.sleep(20)
                if self._ws and self._connected:
                    await self._ws.ping()
            except Exception:
                break

    async def _listen_loop(self):
        while self._connected and self._ws:
            try:
                raw_msg = await self._ws.recv()
                if not isinstance(raw_msg, bytes):
                    continue

                packet = msgpack.unpackb(raw_msg, raw=False)
                packet_id = packet.get("ID")

                if packet_id == "CHALLENGE":
                    pat_payload = {"token": "null"}
                    b64 = base64.b64encode(msgpack.packb(pat_payload)).decode("utf-8")
                    await self._ws.send(msgpack.packb({"ID": "PAT", "token": b64}))

                elif packet_id == "PAT":
                    await self._ws.send(msgpack.packb({"ID": "GetUserData"}))

                elif packet_id == "Ping":
                    await self._ws.send(msgpack.packb({"ID": "Pong"}))

                elif packet_id == "UserData":
                    if packet.get("username") or packet.get("success"):
                        self._profile = AccountProfile(
                            username=packet.get("username", "GamblitUser"),
                            user_id=str(packet.get("id", "")),
                            level=packet.get("level") or 1,
                            balance_dl=packet.get("balances", {}).get("wl", 0),
                            is_authenticated=True,
                            last_checked_at=time.time(),
                        )

                if packet_id in self._pending_responses:
                    fut = self._pending_responses.pop(packet_id)
                    if not fut.done():
                        fut.set_result(packet)

            except Exception as e:
                log.warning(f"Gamblit WebSocket connection dropped ({e}).")
                break

        self._connected = False
        # Trigger background reconnect if running
        if "gamblit" in self.config.gamblit_base_url and self.config.parsed_cookies:
            asyncio.create_task(self._auto_reconnect())

    async def _auto_reconnect(self):
        await asyncio.sleep(2)
        if not self._connected:
            await self.connect_ws()

    async def get_profile(self) -> AccountProfile:
        """Fetches account profile via WebSocket or HTTP."""
        if not self._profile or not self._profile.is_authenticated:
            # Try WS first
            if "gamblit" in self.config.gamblit_base_url:
                await self.connect_ws()
                if self._profile and self._profile.is_authenticated:
                    return self._profile

            # Try HTTP
            try:
                session = await self.get_http_session()
                url = f"{self.config.gamblit_base_url}/api/user/me"
                async with session.get(url) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        user = data.get("user") or data
                        self._profile = AccountProfile(
                            username=user.get("username", "GamblitUser"),
                            user_id=str(user.get("id", "")),
                            level=user.get("level"),
                            balance_dl=user.get("balance"),
                            is_authenticated=True,
                            last_checked_at=time.time(),
                        )
                        return self._profile
            except Exception:
                pass

        return self._profile or AccountProfile(is_authenticated=False)

    async def check_health(self) -> bool:
        p = await self.get_profile()
        return p.is_authenticated

    async def redeem_code(
        self,
        code: str,
        latency: Optional[RedeemLatency] = None,
        attempt: int = 1,
        captcha_token: str = "",
    ) -> RedeemResult:
        """
        Redeems code using WebSocket (if connected), or HTTP fallback.
        """
        if latency is None:
            latency = RedeemLatency()

        # If connected to Gamblit WebSocket, use lightning-fast MessagePack
        if self._connected and self._ws:
            return await self._redeem_ws(code, latency, attempt, captcha_token=captcha_token)

        # If live gamblit domain and not connected yet, try connecting
        if "gamblit" in self.config.gamblit_base_url and not self._connected:
            ws_ok = await self.connect_ws()
            if ws_ok and self._ws:
                return await self._redeem_ws(code, latency, attempt, captcha_token=captcha_token)

        # Fallback to HTTP
        return await self._redeem_http(code, latency, attempt)

    async def _redeem_ws(
        self,
        code: str,
        latency: RedeemLatency,
        attempt: int,
        captcha_token: str = "",
    ) -> RedeemResult:
        fut = asyncio.get_running_loop().create_future()
        self._pending_responses["ClaimPromoCode"] = fut

        claim_packet = {
            "ID": "ClaimPromoCode",
            "code": code,
            "captcha": captcha_token or "",
            "currency": "wl",
        }

        latency.t2_request_started = time.time()
        try:
            await self._ws.send(msgpack.packb(claim_packet))
            response = await asyncio.wait_for(fut, timeout=self.config.read_timeout_sec)
            latency.t3_response_received = time.time()

            success = response.get("success", False)
            err = str(response.get("error", "")).upper()
            amount = response.get("amount")
            curr = response.get("currency", "wl")

            if success:
                if response.get("choose"):
                    wl = response.get("wlAmount")
                    usd = response.get("usdAmount")
                    amt_str = f"{wl} WL / ${usd} USD" if wl and usd else str(wl or usd or "reward")
                else:
                    amt_str = f"{amount} {curr.upper()}"
                return RedeemResult(
                    code=code,
                    status=RedeemStatus.SUCCESS,
                    message=f"Claimed {amt_str}!",
                    response_data=response,
                    latency=latency,
                    attempts=attempt,
                )
            if "ALREADY" in err or "CLAIMED" in err:
                return RedeemResult(code=code, status=RedeemStatus.ALREADY_USED, message="Already claimed", response_data=response, latency=latency)
            if "EXPIRED" in err:
                return RedeemResult(code=code, status=RedeemStatus.EXPIRED, message="Code expired", response_data=response, latency=latency)
            if "LEVEL" in err:
                return RedeemResult(code=code, status=RedeemStatus.NOT_ELIGIBLE, message="Level too low", response_data=response, latency=latency)
            if "CAPTCHA" in err:
                return RedeemResult(code=code, status=RedeemStatus.RATE_LIMITED, message="Server requested captcha challenge (INVALID_CAPTCHA)", response_data=response, latency=latency)

            return RedeemResult(code=code, status=RedeemStatus.INVALID_CODE, message=err or "Invalid code", response_data=response, latency=latency)

        except Exception as e:
            self._pending_responses.pop("ClaimPromoCode", None)
            log.warning(f"WS redeem failed ({e}), trying HTTP fallback...")
            return await self._redeem_http(code, latency, attempt)

    async def _redeem_http(
        self,
        code: str,
        latency: RedeemLatency,
        attempt: int,
    ) -> RedeemResult:
        session = await self.get_http_session()
        payload = {"code": code, "promo_code": code}

        for ep in self.config.redeem_endpoints:
            url = f"{self.config.gamblit_base_url}{ep}"
            latency.t2_request_started = time.time()
            try:
                async with session.post(url, json=payload) as resp:
                    latency.t3_response_received = time.time()
                    try:
                        data = await resp.json()
                    except Exception:
                        data = {}

                    msg = data.get("message") or data.get("error") or ""
                    low = msg.lower()

                    if resp.status in (200, 201) and data.get("success") is not False and "error" not in data:
                        return RedeemResult(code=code, status=RedeemStatus.SUCCESS, message=msg or "Success", latency=latency)
                    if resp.status == 429 or "rate limit" in low:
                        return RedeemResult(code=code, status=RedeemStatus.RATE_LIMITED, retry_after=1.0, latency=latency)
                    if "already" in low:
                        return RedeemResult(code=code, status=RedeemStatus.ALREADY_USED, message=msg, latency=latency)
                    if "expired" in low:
                        return RedeemResult(code=code, status=RedeemStatus.EXPIRED, message=msg, latency=latency)
                    if "level" in low or "eligible" in low:
                        return RedeemResult(code=code, status=RedeemStatus.NOT_ELIGIBLE, message=msg, latency=latency)
                    if resp.status in (401, 403):
                        return RedeemResult(code=code, status=RedeemStatus.AUTH_ERROR, message="Auth failed", latency=latency)
                    if resp.status >= 500:
                        return RedeemResult(code=code, status=RedeemStatus.SERVER_ERROR, message=msg, latency=latency)
                    if resp.status == 400:
                        return RedeemResult(code=code, status=RedeemStatus.INVALID_CODE, message=msg, latency=latency)

            except Exception:
                pass

        latency.t3_response_received = time.time()
        return RedeemResult(code=code, status=RedeemStatus.UNKNOWN, message="Redeem failed", latency=latency)

    async def close(self):
        self._connected = False
        if self._ping_task:
            self._ping_task.cancel()
        if self._listen_task:
            self._listen_task.cancel()
        if self._ws:
            await self._ws.close()
            self._ws = None
        if self._http_session and not self._http_session.closed:
            await self._http_session.close()
            self._http_session = None

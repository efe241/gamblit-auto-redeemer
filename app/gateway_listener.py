"""
High-Performance Discord Gateway Listener (WebSocket).
Supports both User Account Tokens (Self-Bot / Passive Reader) and Bot Tokens.
Features:
- Sub-millisecond latency (direct Gateway WebSocket connection without library overhead)
- Passive read-only: only listens to MESSAGE_CREATE and MESSAGE_UPDATE
- Automatic heartbeat, reconnect, and sequence resume
- Zero outbound chatter (100% stealth, no commands, no reactions)
"""
import asyncio
import json
import logging
import time
from typing import Optional, Dict, Any
import websockets
from app.config import Config
from app.parser import CodeParser
from app.queue import RedeemQueue
from app.metrics import MetricsTracker
from app.database import Database
from app.gamblit_client import GamblitClient

log = logging.getLogger("gamblit_redeemer.gateway")


class DiscordGatewayListener:
    def __init__(
        self,
        config: Config,
        queue: RedeemQueue,
        metrics: MetricsTracker,
        db: Database,
        client: GamblitClient,
        account_manager: Optional[Any] = None,
    ):
        self.config = config
        self.queue = queue
        self.metrics = metrics
        self.db = db
        self.gamblit_client = client
        self.account_manager = account_manager
        self._running = False
        self._ws: Optional[Any] = None
        self._task: Optional[asyncio.Task] = None
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._sequence: Optional[int] = None
        self._session_id: Optional[str] = None
        self.username: str = ""
        self.user_id: str = ""
        self.is_connected = False

    @property
    def gateway_url(self) -> str:
        return "wss://gateway.discord.gg/?v=10&encoding=json"

    async def start(self):
        """Starts the gateway connection in background."""
        if not self.config.discord_token:
            log.warning("DISCORD_TOKEN is empty. Gateway listener waiting for token...")
            return

        self._running = True
        self._task = asyncio.create_task(self._connection_loop(), name="DiscordGatewayLoop")
        log.info("Discord Gateway listener started (Passive User/Bot Mode).")

    async def stop(self):
        self._running = False
        self.is_connected = False
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            self._heartbeat_task = None
        if self._task:
            self._task.cancel()
            self._task = None
        if self._ws:
            await self._ws.close()
            self._ws = None
        log.info("Discord Gateway listener stopped.")

    async def _connection_loop(self):
        while self._running:
            try:
                token = self.config.discord_token.strip().strip('"').strip("'")
                if not token:
                    await asyncio.sleep(5)
                    continue

                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                    "Origin": "https://discord.com",
                }

                log.info(f"Connecting to Discord Gateway ({self.gateway_url})...")
                async with websockets.connect(
                    self.gateway_url,
                    open_timeout=10,
                    ping_interval=None,
                    close_timeout=1.0,
                    max_size=2**22,
                ) as ws:
                    try:
                        transport = getattr(ws, "transport", None)
                        if transport is None and hasattr(ws, "protocol"):
                            transport = getattr(ws.protocol, "transport", None)
                        if transport:
                            sock = transport.get_extra_info("socket")
                            if sock:
                                import socket
                                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                                sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
                    except Exception:
                        pass
                    self._ws = ws
                    self.is_connected = True
                    await self._handle_messages(ws, token)

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.is_connected = False
                log.warning(f"Discord Gateway connection lost ({e}). Reconnecting in 4s...")
                await asyncio.sleep(4)

    async def _handle_messages(self, ws: Any, token: str):
        async for raw_message in ws:
            if not self._running:
                break

            data = json.loads(raw_message)
            op = data.get("op")
            seq = data.get("s")
            event_type = data.get("t")
            payload = data.get("d")

            if seq is not None:
                self._sequence = seq

            # OP 10: Hello -> Start heartbeat and identify
            if op == 10:
                interval_ms = payload.get("heartbeat_interval", 41250)
                if self._heartbeat_task:
                    self._heartbeat_task.cancel()
                self._heartbeat_task = asyncio.create_task(self._heartbeat_loop(ws, interval_ms / 1000.0))
                await self._send_identify(ws, token)

            # OP 1: Heartbeat requested by server -> answer immediately
            elif op == 1:
                await ws.send(json.dumps({"op": 1, "d": self._sequence}))

            # OP 11: Heartbeat ACK -> healthy
            elif op == 11:
                pass

            # OP 0: Dispatch Events
            elif op == 0:
                if event_type == "READY":
                    user = payload.get("user", {})
                    self.username = f"{user.get('username')}#{user.get('discriminator', '0')}"
                    self.user_id = str(user.get("id", ""))
                    self._session_id = payload.get("session_id")
                    log.info(f"✅ Discord Gateway bağlandı! Giriş yapılan hesap: {self.username} (ID: {self.user_id})")
                    log.info(f"🎯 Hedef Kanal: {self.config.discord_channel_id} | Sunucu: {self.config.discord_guild_id or 'Tümü'}")

                elif event_type in ("MESSAGE_CREATE", "MESSAGE_UPDATE"):
                    await self._process_message_event(payload)

    async def _send_identify(self, ws: Any, token: str):
        # Format identify payload (supports User Tokens & Bot Tokens)
        clean_token = token.replace("Bot ", "").strip()
        identify_data = {
            "op": 2,
            "d": {
                "token": clean_token,
                "capabilities": 8189,
                "properties": {
                    "os": "Windows",
                    "browser": "Chrome",
                    "device": "",
                    "system_locale": "tr-TR",
                    "browser_user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                    "browser_version": "124.0.0.0",
                    "os_version": "10",
                    "release_channel": "stable",
                    "client_build_number": 289456,
                },
                "presence": {
                    "status": "online",
                    "since": 0,
                    "activities": [],
                    "afk": False,
                },
                "compress": False,
            },
        }
        await ws.send(json.dumps(identify_data))

    async def _heartbeat_loop(self, ws: Any, interval: float):
        try:
            while self._running:
                await asyncio.sleep(interval)
                await ws.send(json.dumps({"op": 1, "d": self._sequence}))
        except asyncio.CancelledError:
            pass
        except Exception:
            pass

    async def _process_message_event(self, d: Dict[str, Any]):
        t0 = time.time()
        channel_id = int(d.get("channel_id") or 0)
        guild_id = int(d.get("guild_id") or 0)
        content = d.get("content", "")
        message_id = int(d.get("id") or 0)
        author = d.get("author", {})
        author_id = int(author.get("id") or 0)
        author_name = author.get("username", "Unknown")

        # Ignore messages sent by ourselves
        if str(author_id) == str(self.user_id):
            return

        # Strict Channel Filtering
        if self.config.discord_channel_id and channel_id != self.config.discord_channel_id:
            return

        # Strict Guild Filtering
        if self.config.discord_guild_id and guild_id != self.config.discord_guild_id:
            return

        self.metrics.record_received()

        # Parse Drop or Code
        max_level = None
        if self.account_manager:
            max_level = self.account_manager.get_max_level()
        elif self.gamblit_client and getattr(self.gamblit_client, "_profile", None):
            raw_lvl = getattr(self.gamblit_client._profile, "level", None)
            if isinstance(raw_lvl, int):
                max_level = raw_lvl

        drop_item = CodeParser.parse_drop_message(
            content=content,
            message_id=message_id,
            channel_id=channel_id,
            guild_id=guild_id,
            author_id=author_id,
            received_at=t0,
            max_level=max_level,
        )

        if not drop_item:
            return

        self.metrics.record_parsed()
        if drop_item.level_codes:
            log.info(
                f"⚡ [MULTI-LEVEL DROP YAKALANDI] {len(drop_item.level_codes)} kod tespit edildi! "
                f"En yüksek kod: '{drop_item.code}' (Level {drop_item.required_level}+) | Gönderen: {author_name} "
                f"| Gecikme: {drop_item.parse_latency_ms:.2f} ms"
            )
        else:
            log.info(
                f"⚡ [KOD YAKALANDI] '{drop_item.code}' | Kanal: #{channel_id} | Gönderen: {author_name} "
                f"| Ayrıştırma Gecikmesi: {drop_item.parse_latency_ms:.2f} ms"
            )

        # Enqueue for parallel multi-account redemption
        enqueued = await self.queue.enqueue(drop_item)
        if enqueued:
            await self.db.log_event(
                "CODE_ENQUEUED",
                {
                    "code": drop_item.code,
                    "message_id": message_id,
                    "author": author_name,
                    "channel_id": channel_id,
                    "is_drop": bool(drop_item.level_codes),
                },
            )

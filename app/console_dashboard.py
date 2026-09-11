"""
Live Console Status Monitor for Gamblit Promo Code Auto-Redeemer.
Continuously displays real-time system metrics, WebSocket health,
Captcha pool freshness, account balance, and code stats directly to the console.
"""
import asyncio
import sys
import time
from datetime import datetime
from typing import Optional, Any
from app.config import Config
from app.gamblit_client import GamblitClient
from app.captcha_pool import CaptchaPool
from app.metrics import MetricsTracker
from app.queue import RedeemQueue
from app.database import Database


class ConsoleDashboard:
    def __init__(
        self,
        config: Config,
        client: GamblitClient,
        captcha_pool: CaptchaPool,
        metrics: MetricsTracker,
        queue: RedeemQueue,
        db: Database,
        gateway_listener: Optional[Any] = None,
        account_manager: Optional[Any] = None,
        interval_sec: float = 3.0,
    ):
        self.config = config
        self.client = client
        self.captcha_pool = captcha_pool
        self.metrics = metrics
        self.queue = queue
        self.db = db
        self.gateway_listener = gateway_listener
        self.account_manager = account_manager
        self.interval_sec = interval_sec
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self):
        self._running = True
        self._task = asyncio.create_task(self._display_loop(), name="ConsoleDashboardLoop")

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None

    async def _display_loop(self):
        # Color codes
        CYAN = "\033[96m"
        GREEN = "\033[92m"
        YELLOW = "\033[93m"
        RED = "\033[91m"
        PURPLE = "\033[95m"
        BOLD = "\033[1m"
        DIM = "\033[2m"
        RESET = "\033[0m"

        # Wait 2 seconds on startup for connections to settle
        await asyncio.sleep(2)

        while self._running:
            try:
                profile = await self.client.get_profile()
                stats = await self.db.get_stats()
                now_str = self.config.get_tr_now().strftime("%H:%M:%S")

                # WebSocket & Account Status
                if self.account_manager and len(self.account_manager.accounts) > 1:
                    acc_sum = self.account_manager.get_summary()
                    conn = acc_sum["connected_accounts"]
                    tot = acc_sum["total_accounts"]
                    tot_dl = acc_sum["total_dl"]
                    c_badge = GREEN if conn > 0 else RED
                    ws_part = f"{c_badge}● {conn}/{tot} HESAP BAĞLI{RESET} (Toplam: {GREEN}{tot_dl} DL{RESET})"
                elif profile.is_authenticated:
                    ws_part = f"{GREEN}● WS BAĞLI{RESET} ({BOLD}{profile.username}{RESET} | {GREEN}{profile.balance_dl} DL{RESET})"
                elif self.client._connected:
                    ws_part = f"{YELLOW}● WS BAĞLANDI (Giriş Bekleniyor){RESET}"
                else:
                    ws_part = f"{RED}○ WS ÇEVRİMDIŞI{RESET}"

                # Captcha Status
                in_sched = self.config.is_in_schedule()
                rem = self.captcha_pool.remaining_seconds
                if not in_sched:
                    cap_part = f"{DIM}🛡️ UYKUDA ({self.config.schedule_start}-{self.config.schedule_end}){RESET}"
                elif self.captcha_pool.is_token_valid and rem > 0:
                    c_color = GREEN if rem > 25 else YELLOW
                    cap_part = f"{c_color}🛡️ TOKEN HAZIR ({int(rem)} sn){RESET}"
                elif self.captcha_pool.is_solving:
                    cap_part = f"{CYAN}🛡️ ÇÖZÜLÜYOR...{RESET}"
                else:
                    cap_part = f"{RED}🛡️ HAVUZ BOŞ (0 sn){RESET}"

                # Solver info
                if self.captcha_pool.nonecap_api_key:
                    solver_name = f"{GREEN}NoneCap{RESET}"
                elif self.captcha_pool.capsolver_api_key:
                    solver_name = f"{PURPLE}CapSolver{RESET}"
                elif self.captcha_pool.twocaptcha_api_key:
                    solver_name = f"{PURPLE}2Captcha{RESET}"
                else:
                    solver_name = f"{DIM}Manuel Mod{RESET}"


                # Discord listener info
                if self.gateway_listener and self.gateway_listener.is_connected:
                    user_tag = self.gateway_listener.username or "Self-User"
                    dc_part = f"{GREEN}Discord: ● {user_tag} (#{self.config.discord_channel_id}){RESET}"
                elif self.config.discord_token:
                    dc_part = f"{YELLOW}Discord: Bağlanıyor... (#{self.config.discord_channel_id}){RESET}"
                else:
                    dc_part = f"{DIM}Discord: Token Bekleniyor{RESET}"

                # Code stats
                succ = stats.get("successful", 0)
                fail = stats.get("failed", 0)
                tot = stats.get("total_codes", 0)
                stats_part = f"📊 Kod: {BOLD}{tot}{RESET} ({GREEN}✔ {succ}{RESET} / {RED}✖ {fail}{RESET})"

                # Latency
                avg_lat = stats.get("avg_latency_ms", 0.0)
                lat_part = f"⚡ {avg_lat:.1f} ms"

                # Single-line clean dashboard output
                status_line = (
                    f"[{DIM}{now_str}{RESET}] "
                    f"{ws_part} | "
                    f"{cap_part} [{solver_name}] | "
                    f"{dc_part} | "
                    f"{stats_part} | "
                    f"{lat_part}"
                )

                print(status_line, flush=True)

            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"[Console Error] {e}", flush=True)

            await asyncio.sleep(self.interval_sec)

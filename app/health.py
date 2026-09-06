"""
Periodic health check and watchdog monitor for Gamblit session, DB, and Discord.
"""
import asyncio
import logging
from typing import Optional
from app.gamblit_client import GamblitClient
from app.database import Database

log = logging.getLogger("gamblit_redeemer.health")


class HealthMonitor:
    def __init__(
        self,
        client: GamblitClient,
        db: Database,
        interval_sec: float = 60.0,
    ):
        self.client = client
        self.db = db
        self.interval_sec = interval_sec
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self.is_gamblit_healthy = False

    async def start(self):
        """Starts watchdog background task."""
        self._running = True
        self._task = asyncio.create_task(self._monitor_loop(), name="HealthMonitorLoop")
        log.info("HealthMonitor watchdog started.")

    async def stop(self):
        """Stops watchdog background task."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        log.info("HealthMonitor watchdog stopped.")

    async def check_once(self) -> bool:
        """Runs a single comprehensive health probe."""
        # 1. Check Gamblit session
        profile = await self.client.get_profile()
        self.is_gamblit_healthy = profile.is_authenticated

        # 2. Save snapshot in DB
        await self.db.save_account_state(
            account_name=profile.username,
            level=profile.level,
            balance_dl=profile.balance_dl,
            status="ONLINE" if self.is_gamblit_healthy else "EXPIRED_COOKIES",
        )

        if not self.is_gamblit_healthy:
            log.warning(
                "Health check warning: Gamblit session is NOT authenticated! "
                "Browser cookies may have expired (cf_clearance or session token)."
            )
        else:
            log.debug(f"Health check OK. Logged in as: {profile.username}")

        return self.is_gamblit_healthy

    async def _monitor_loop(self):
        while self._running:
            try:
                await self.check_once()
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error(f"Error during health check: {e}", exc_info=True)

            try:
                await asyncio.sleep(self.interval_sec)
            except asyncio.CancelledError:
                break

"""
Discord Webhook Notifier for Gamblit Auto-Redeemer.
Completely decoupled, fail-safe, and asynchronous.
Handles:
- Account disconnect / expiration alerts (with direct link to /cc)
- Account reconnection notices
- Pre-drop readiness report at 20:15 (TR time)
- Real-time redeem results & rewards notifications
"""
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List
import aiohttp
from app.config import Config

log = logging.getLogger("gamblit_redeemer.notifier")

# Turkey Time Zone (UTC+3)
TR_TZ = timezone(timedelta(hours=3))


async def send_discord_webhook(
    webhook_url: str,
    title: str,
    description: str,
    color: int = 3711992,
    fields: Optional[List[Dict[str, Any]]] = None,
    footer_text: str = "Gamblit Auto-Redeemer Pro",
) -> bool:
    """Sends an embed to Discord Webhook asynchronously. Never raises exceptions."""
    if not webhook_url or not webhook_url.startswith("https://discord.com/api/webhooks/"):
        return False

    payload = {
        "embeds": [
            {
                "title": title,
                "description": description,
                "color": color,
                "fields": fields or [],
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "footer": {"text": footer_text},
            }
        ]
    }

    try:
        timeout = aiohttp.ClientTimeout(total=5.0)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(webhook_url, json=payload) as resp:
                if resp.status in (200, 204):
                    return True
                log.debug(f"Discord webhook responded with status: {resp.status}")
                return False
    except Exception as e:
        log.debug(f"Discord webhook send error: {e}")
        return False


class Notifier:
    def __init__(
        self,
        config: Config,
        account_manager: Optional[Any] = None,
        captcha_pool: Optional[Any] = None,
        metrics: Optional[Any] = None,
    ):
        self.config = config
        self.account_manager = account_manager
        self.captcha_pool = captcha_pool
        self.metrics = metrics
        self.webhook_url = config.discord_webhook_url
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._last_account_states: Dict[str, bool] = {}
        self._initialized = False
        self._pre_drop_sent_date: Optional[str] = None

    async def start(self):
        """Starts background monitoring task."""
        if not self.webhook_url:
            log.info("Discord webhook URL not configured, notifier disabled.")
            return

        self._running = True
        self._task = asyncio.create_task(self._monitoring_loop(), name="DiscordNotifierLoop")
        log.info("Discord Webhook Notifier started.")

    async def stop(self):
        """Stops background monitoring task."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        log.info("Discord Webhook Notifier stopped.")

    async def notify_account_offline(self, acc_name: str, username: str, level: int):
        """Sends an urgent warning when an account disconnects or cookies expire."""
        panel_url = self.config.gamblit_base_url
        cc_url = "https://gamblit-auto-redeemer.onrender.com/cc"
        fields = [
            {"name": "👤 Hesap", "value": f"**{username}** (`{acc_name}`)", "inline": True},
            {"name": "⭐ Seviye", "value": f"Level {level}", "inline": True},
            {"name": "⚠️ Durum", "value": "ÇEVRİMDIŞI / Çerez Süresi Doldu", "inline": False},
            {
                "name": "🔧 Çözüm",
                "value": f"[Çerez Ayrıştırıcıya Git ({cc_url})]({cc_url}) sayfasına gidip yeni çerezi yapıştırın.",
                "inline": False,
            },
        ]
        await send_discord_webhook(
            webhook_url=self.webhook_url,
            title="🚨 [DİKKAT] Gamblit Hesabı Çevrimdışı Oldu!",
            description=f"**{username}** hesabının bağlantısı koptu veya oturum çerezi geçersiz hale geldi.",
            color=16007990,  # Red / Rose
            fields=fields,
        )

    async def notify_account_online(self, acc_name: str, username: str, level: int):
        """Sends a notification when an account reconnects."""
        fields = [
            {"name": "👤 Hesap", "value": f"**{username}** (`{acc_name}`)", "inline": True},
            {"name": "⭐ Seviye", "value": f"Level {level}", "inline": True},
            {"name": "✅ Durum", "value": "● BAĞLI ve Hazır", "inline": True},
        ]
        await send_discord_webhook(
            webhook_url=self.webhook_url,
            title="🟢 [BİLGİ] Gamblit Hesabı Yeniden Bağlandı!",
            description=f"**{username}** hesabı başarıyla bağlandı ve drop için hazır.",
            color=1095977,  # Green
            fields=fields,
        )

    async def notify_pre_drop_status(self):
        """Sends a readiness check at 20:15 TR time (15 mins before 20:30 drop)."""
        tr_time_str = datetime.now(TR_TZ).strftime("%H:%M")
        total_accounts = 0
        connected_accounts = 0
        total_dl = 0.0

        if self.account_manager:
            summary = self.account_manager.get_summary()
            total_accounts = summary.get("total_accounts", 0)
            connected_accounts = summary.get("connected_accounts", 0)
            total_dl = summary.get("total_dl", 0.0)

        total_credits = 0
        if self.captcha_pool:
            balances = await self.captcha_pool.get_balances()
            total_credits = balances.get("total_remaining_credits", 0)

        all_ok = total_accounts > 0 and connected_accounts == total_accounts
        status_text = "TÜM HESAPLAR HAZIR 🔥" if all_ok else f"⚠️ {total_accounts - connected_accounts} HESAP ÇEVRİMDIŞI!"
        color = 1095977 if all_ok else 16098851

        fields = [
            {"name": "👥 Bağlı Hesaplar", "value": f"**{connected_accounts} / {total_accounts}** Aktif", "inline": True},
            {"name": "💳 NoneCap Havuzu", "value": f"**{total_credits:,}** Kredi".replace(",", "."), "inline": True},
            {"name": "💰 Toplam Bakiye", "value": f"**{total_dl:.2f} DL**", "inline": True},
            {"name": "⏰ Hedef Drop Saati", "value": "20:30 - 20:45 (TR)", "inline": True},
            {"name": "🎯 Sistem Durumu", "value": status_text, "inline": True},
        ]

        await send_discord_webhook(
            webhook_url=self.webhook_url,
            title=f"🛡️ [Drop Öncesi Durum Raporu — {tr_time_str}]",
            description="Saat 20:30 drop'u öncesinde tüm sistemin sağlık taraması tamamlandı.",
            color=color,
            fields=fields,
        )

    async def notify_redeem(
        self,
        code: str,
        status: str,
        message: str,
        latency_ms: float = 0.0,
        multi_claims: Optional[List[Dict[str, Any]]] = None,
    ):
        """Sends a notification when a promo code is redeemed."""
        is_success = "SUCCESS" in str(status).upper() or "CLAIMED" in str(status).upper()
        color = 1095977 if is_success else 16007990

        fields = [
            {"name": "🏷️ Kod", "value": f"`{code}`", "inline": True},
            {"name": "⚡ Yanıt Süresi", "value": f"**{latency_ms:.1f} ms**", "inline": True},
            {"name": "📊 Durum", "value": str(status), "inline": True},
        ]

        if multi_claims:
            claim_lines = []
            for item in multi_claims[:10]:
                acc_name = item.get("account_name", "Hesap")
                res = item.get("result")
                res_status = res.status.value if hasattr(res, "status") else str(res)
                claim_lines.append(f"• **{acc_name}**: {res_status}")
            fields.append({"name": "👥 Hesap Sonuçları", "value": "\n".join(claim_lines), "inline": False})
        else:
            fields.append({"name": "💬 Sunucu Mesajı", "value": str(message)[:300], "inline": False})

        title = "🎉 [KOD YAKALANDI!] Başarılı Redeem!" if is_success else "ℹ️ [Promo Kod İşlendi]"
        await send_discord_webhook(
            webhook_url=self.webhook_url,
            title=title,
            description=f"Discord'dan yakalanan **`{code}`** kodu işlendi.",
            color=color,
            fields=fields,
        )

    async def _monitoring_loop(self):
        """Periodic background monitor (every 30 seconds)."""
        await asyncio.sleep(5)  # initial wait for accounts to connect

        while self._running:
            try:
                # 1. Check Account States
                if self.account_manager and hasattr(self.account_manager, "accounts"):
                    current_accounts = dict(self.account_manager.accounts)
                    for acc_id, acc in current_accounts.items():
                        if not acc.enabled:
                            continue

                        is_connected = bool(acc.client and acc.client._connected)
                        username = acc.client._profile.username if (acc.client and acc.client._profile) else acc.name
                        level = acc.client._profile.level if (acc.client and acc.client._profile) else 1

                        prev_connected = self._last_account_states.get(acc_id)

                        if self._initialized:
                            # Transition: was connected -> now disconnected
                            if prev_connected is True and not is_connected:
                                log.warning(f"Account {username} ({acc.name}) went OFFLINE. Sending alert...")
                                await self.notify_account_offline(acc.name, username, level)
                            # Transition: was disconnected -> now reconnected
                            elif prev_connected is False and is_connected:
                                log.info(f"Account {username} ({acc.name}) came back ONLINE. Sending notice...")
                                await self.notify_account_online(acc.name, username, level)

                        self._last_account_states[acc_id] = is_connected

                    self._initialized = True

                # 2. Check 20:15 TR Time for Pre-Drop Readiness Report
                now_tr = datetime.now(TR_TZ)
                today_str = now_tr.strftime("%Y-%m-%d")
                if now_tr.hour == 20 and 14 <= now_tr.minute <= 16:
                    if self._pre_drop_sent_date != today_str:
                        self._pre_drop_sent_date = today_str
                        log.info("Sending 20:15 Pre-Drop Readiness Report to Discord...")
                        await self.notify_pre_drop_status()

            except asyncio.CancelledError:
                break
            except Exception as e:
                log.debug(f"Notifier loop error: {e}")

            await asyncio.sleep(30)

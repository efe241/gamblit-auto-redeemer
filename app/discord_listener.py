"""
Discord message listener for Gamblit promo code channel.
Zero-blocking event handler that parses messages and enqueues codes.
"""
import time
import logging
from typing import Optional
import discord
from discord.ext import commands
from app.config import Config
from app.parser import CodeParser
from app.queue import RedeemQueue
from app.metrics import MetricsTracker
from app.database import Database
from app.gamblit_client import GamblitClient

log = logging.getLogger("gamblit_redeemer.listener")


class DiscordCodeListener(commands.Bot):
    def __init__(
        self,
        config: Config,
        queue: RedeemQueue,
        metrics: MetricsTracker,
        db: Database,
        client: GamblitClient,
        account_manager: Optional[Any] = None,
    ):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.guilds = True
        intents.messages = True

        super().__init__(
            command_prefix="!",
            intents=intents,
            help_command=None,
        )
        self.config = config
        self.queue = queue
        self.metrics = metrics
        self.db = db
        self.gamblit_client = client
        self.account_manager = account_manager

    async def setup_hook(self):
        """Registers commands and initializes internal hooks."""
        log.info("Setting up Discord listener commands...")

    async def on_ready(self):
        log.info(f"Discord Listener connected as: {self.user} (ID: {self.user.id})")
        log.info(f"Target Guild ID: {self.config.discord_guild_id}")
        log.info(f"Target Channel ID: {self.config.discord_channel_id}")

        # Check guild/channel existence if configured
        if self.config.discord_guild_id:
            guild = self.get_guild(self.config.discord_guild_id)
            if guild:
                log.info(f"Verified Guild: {guild.name}")
            else:
                log.warning(f"Configured Guild ID {self.config.discord_guild_id} not found in bot guilds.")

        if self.config.discord_channel_id:
            channel = self.get_channel(self.config.discord_channel_id)
            if channel:
                log.info(f"Verified Channel: #{channel.name}")
            else:
                log.warning(f"Configured Channel ID {self.config.discord_channel_id} not visible or not accessible.")

    async def on_message(self, message: discord.Message):
        # 1. Capture exact arrival timestamp immediately (Hot Path T0)
        t0 = time.time()

        # Ignore self messages
        if message.author == self.user:
            return

        # 2. Strict Channel Filtering
        if self.config.discord_channel_id and message.channel.id != self.config.discord_channel_id:
            await self.process_commands(message)
            return

        # 3. Strict Guild Filtering (if specified)
        if self.config.discord_guild_id and message.guild and message.guild.id != self.config.discord_guild_id:
            return

        self.metrics.record_received()

        # 4. Parse Drop or Code
        max_level = None
        if self.account_manager:
            max_level = self.account_manager.get_max_level()
        elif self.gamblit_client and getattr(self.gamblit_client, "_profile", None):
            raw_lvl = getattr(self.gamblit_client._profile, "level", None)
            if isinstance(raw_lvl, int):
                max_level = raw_lvl

        drop_item = CodeParser.parse_drop_message(
            content=message.content,
            message_id=message.id,
            channel_id=message.channel.id,
            guild_id=message.guild.id if message.guild else 0,
            author_id=message.author.id,
            received_at=t0,
            max_level=max_level,
        )

        if not drop_item:
            await self.process_commands(message)
            return

        self.metrics.record_parsed()
        if drop_item.level_codes:
            log.info(
                f"⚡ [MULTI-LEVEL DROP] {len(drop_item.level_codes)} kod tespit edildi! "
                f"En yüksek: '{drop_item.code}' (Level {drop_item.required_level}+)"
            )
        else:
            log.info(
                f"⚡ [Kod Algılandı] '{drop_item.code}' (#{message.channel}, {message.author}) "
                f"(Gecikme: {drop_item.parse_latency_ms:.2f} ms)"
            )

        # 5. Non-blocking Enqueue (Hot Path -> Queue -> Worker)
        enqueued = await self.queue.enqueue(drop_item)
        if enqueued:
            await self.db.log_event("CODE_ENQUEUED", {
                "code": drop_item.code,
                "message_id": message.id,
                "author": str(message.author),
                "is_drop": bool(drop_item.level_codes),
            })

        await self.process_commands(message)

    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        """Processes edited messages if a code was corrected or posted after an edit."""
        if before.content != after.content:
            await self.on_message(after)


def register_listener_commands(bot: DiscordCodeListener):
    """Registers /status and info commands."""

    @bot.command(name="status")
    async def cmd_status(ctx: commands.Context):
        """Reports bot status, connection health, metrics, and latest codes."""
        stats = await bot.db.get_stats()
        metrics = bot.metrics.summary()
        gamblit_ok = await bot.gamblit_client.check_health()

        profile = bot.gamblit_client._profile

        embed = discord.Embed(
            title="⚡ Gamblit Promo Code Redeemer Status",
            color=discord.Color.green() if gamblit_ok else discord.Color.gold(),
        )
        embed.add_field(
            name="🤖 Services",
            value=(
                f"**Discord Bot:** ONLINE\n"
                f"**Gamblit Session:** {'CONNECTED' if gamblit_ok else 'UNAUTHENTICATED'}\n"
                f"**Queue Depth:** {bot.queue.qsize}"
            ),
            inline=False,
        )
        if profile and profile.is_authenticated:
            embed.add_field(
                name="👤 Gamblit Account",
                value=(
                    f"**User:** {profile.username}\n"
                    f"**Level:** {profile.level if profile.level is not None else 'N/A'}\n"
                    f"**Balance:** {profile.balance_dl or 0} DL"
                ),
                inline=False,
            )

        embed.add_field(
            name="📊 Code Metrics",
            value=(
                f"**Detected:** {stats['total_codes']}\n"
                f"**Success:** {stats['successful']}\n"
                f"**Failed:** {stats['failed']}\n"
                f"**Avg Latency:** {stats['avg_latency_ms']} ms"
            ),
            inline=True,
        )

        last_code = stats.get("last_code") or "None"
        last_status = stats.get("last_status") or "N/A"
        last_lat = stats.get("last_latency_ms") or 0.0
        embed.add_field(
            name="🎯 Last Code",
            value=f"**Code:** `{last_code}`\n**Status:** {last_status}\n**Latency:** {last_lat:.1f} ms",
            inline=True,
        )

        embed.set_footer(text=f"Uptime: {metrics['uptime_seconds']}s")
        await ctx.send(embed=embed)

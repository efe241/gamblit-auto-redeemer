"""
Configuration loader for Gamblit Promo Code Auto-Redeemer.
Loads from environment variables and .env file.
"""
import os
import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from pathlib import Path
from dotenv import load_dotenv

# Load .env if present
load_dotenv()


@dataclass
class Config:
    # Discord Settings
    discord_token: str = field(default_factory=lambda: os.getenv("DISCORD_TOKEN", ""))
    discord_guild_id: int = field(default_factory=lambda: int(os.getenv("DISCORD_GUILD_ID", "0") or 0))
    discord_channel_id: int = field(default_factory=lambda: int(os.getenv("DISCORD_CHANNEL_ID", "0") or 0))

    # Gamblit Account Settings
    gamblit_base_url: str = field(
        default_factory=lambda: os.getenv("GAMBLIT_BASE_URL", "https://gamblit.net").rstrip("/")
    )
    raw_cookies: str = field(default_factory=lambda: os.getenv("GAMBLIT_COOKIES", "{}"))
    gamblit_user_agent: str = field(
        default_factory=lambda: os.getenv(
            "GAMBLIT_USER_AGENT",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        )
    )

    # Redeem Endpoints (list of candidates to probe or execute)
    redeem_endpoints: List[str] = field(
        default_factory=lambda: [
            ep.strip()
            for ep in os.getenv(
                "REDEEM_ENDPOINTS",
                "/api/promo/redeem,/api/codes/redeem,/api/promocode/redeem,/api/user/redeem",
            ).split(",")
            if ep.strip()
        ]
    )

    # Network / Timeout Optimizations
    connect_timeout_sec: float = field(
        default_factory=lambda: float(os.getenv("CONNECT_TIMEOUT_SEC", "3.0"))
    )
    read_timeout_sec: float = field(
        default_factory=lambda: float(os.getenv("READ_TIMEOUT_SEC", "5.0"))
    )
    max_retries: int = field(default_factory=lambda: int(os.getenv("MAX_RETRIES", "2")))
    rate_limit_backoff_factor: float = field(
        default_factory=lambda: float(os.getenv("RATE_LIMIT_BACKOFF_FACTOR", "1.5"))
    )

    # Captcha Solvers (NoneCap / CapSolver / 2Captcha)
    nonecap_api_key: str = field(default_factory=lambda: os.getenv("NONECAP_API_KEY", ""))
    capsolver_api_key: str = field(default_factory=lambda: os.getenv("CAPSOLVER_API_KEY", ""))
    twocaptcha_api_key: str = field(default_factory=lambda: os.getenv("TWOCAPTCHA_API_KEY", ""))

    # Operating Schedule Window (e.g. 20:25 - 21:00)
    schedule_enabled: bool = field(
        default_factory=lambda: os.getenv("SCHEDULE_ENABLED", "true").lower() in ("true", "1", "yes")
    )
    schedule_start: str = field(default_factory=lambda: os.getenv("SCHEDULE_START", "20:25"))
    schedule_end: str = field(default_factory=lambda: os.getenv("SCHEDULE_END", "21:00"))


    # Database & Logs
    database_path: str = field(
        default_factory=lambda: os.getenv("DATABASE_PATH", "data/gamblit.db")
    )
    port: int = field(default_factory=lambda: int(os.getenv("PORT", "5050") or 5050))
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))
    log_file: str = field(default_factory=lambda: os.getenv("LOG_FILE", "logs/app.log"))

    @property
    def parsed_cookies(self) -> Dict[str, str]:
        """Parses cookies from JSON or semicolon-delimited cookie string."""
        raw = self.raw_cookies.strip()
        if not raw:
            return {}

        # Try JSON first
        if raw.startswith("{"):
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    return {str(k): str(v) for k, v in parsed.items()}
            except Exception:
                pass

        # Try standard Cookie header format "key=val; key2=val2"
        cookies = {}
        for part in raw.split(";"):
            if "=" in part:
                k, v = part.strip().split("=", 1)
                cookies[k.strip()] = v.strip()
        return cookies

    @staticmethod
    def get_tr_now():
        """Returns current datetime in Turkey timezone (UTC+3)."""
        import datetime
        tr_tz = datetime.timezone(datetime.timedelta(hours=3))
        return datetime.datetime.now(tr_tz)

    def is_in_schedule(self) -> bool:
        """Checks if current time falls within schedule_start and schedule_end (HH:MM) in Turkey Time (UTC+3)."""
        if not self.schedule_enabled:
            return True
        try:
            import datetime
            now = self.get_tr_now().time()
            s_h, s_m = map(int, self.schedule_start.split(":"))
            e_h, e_m = map(int, self.schedule_end.split(":"))
            start_t = datetime.time(s_h, s_m)
            end_t = datetime.time(e_h, e_m)
            if start_t <= end_t:
                return start_t <= now <= end_t
            else:
                # Crosses midnight (e.g. 23:00 - 02:00)
                return now >= start_t or now <= end_t
        except Exception:
            return True

    def get_schedule_countdown(self) -> Dict[str, Any]:
        """Calculates exact countdown: time left until waking up (if sleeping) or until ending (if active)."""
        if not self.schedule_enabled:
            return {"is_active": True, "countdown_text": "Sürekli Aktif", "remaining_sec": 0}
        try:
            import datetime
            now = self.get_tr_now()
            s_h, s_m = map(int, self.schedule_start.split(":"))
            e_h, e_m = map(int, self.schedule_end.split(":"))

            start_dt = now.replace(hour=s_h, minute=s_m, second=0, microsecond=0)
            end_dt = now.replace(hour=e_h, minute=e_m, second=0, microsecond=0)

            is_active = self.is_in_schedule()

            if is_active:
                if now > end_dt:
                    end_dt += datetime.timedelta(days=1)
                rem = max(0, int((end_dt - now).total_seconds()))
                hours = rem // 3600
                mins = (rem % 3600) // 60
                secs = rem % 60
                time_str = f"{mins} dk {secs} sn" if hours == 0 else f"{hours} sa {mins} dk"
                return {
                    "is_active": True,
                    "remaining_sec": rem,
                    "countdown_text": f"Bitmesine: {time_str} kaldı",
                }
            else:
                if now >= start_dt:
                    start_dt += datetime.timedelta(days=1)
                rem = max(0, int((start_dt - now).total_seconds()))
                hours = rem // 3600
                mins = (rem % 3600) // 60
                secs = rem % 60
                time_str = f"{mins} dk {secs} sn" if hours == 0 else f"{hours} sa {mins} dk"
                return {
                    "is_active": False,
                    "remaining_sec": rem,
                    "countdown_text": f"Uyanmaya: {time_str} kaldı",
                }
        except Exception:
            return {"is_active": True, "countdown_text": "Aktif", "remaining_sec": 0}

    def validate_for_production(self) -> List[str]:
        """Returns list of missing/invalid configuration items."""
        errors = []
        if not self.discord_token:
            errors.append("DISCORD_TOKEN is not set.")
        if not self.discord_channel_id:
            errors.append("DISCORD_CHANNEL_ID is not set.")
        if not self.parsed_cookies:
            errors.append("GAMBLIT_COOKIES is empty.")
        return errors



# Global config instance
cfg = Config()

"""
Setup wizard for Gamblit Promo Code Auto-Redeemer.
Helps the user configure Discord credentials, Gamblit cookies, and channels.
"""
import os
import sys
import json
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


def prompt_setup():
    print("==========================================================")
    print("       ⚡ Gamblit Promo Code Auto-Redeemer Setup ⚡        ")
    print("==========================================================")
    print()

    # Discord Bot Token
    discord_token = input("1. Enter Discord Bot Token: ").strip()

    # Discord Channel ID
    discord_channel_id = input("2. Enter Discord #codes Channel ID: ").strip()

    # Discord Guild ID
    discord_guild_id = input("3. Enter Discord Server (Guild) ID (optional, press Enter to skip): ").strip()

    # Gamblit Base URL
    gamblit_url = input("4. Gamblit Base URL [https://gamblit.net]: ").strip() or "https://gamblit.net"

    print("\nGamblit Authentication Cookies:")
    print("Log into https://gamblit.net in Chrome/Firefox, open DevTools -> Application -> Cookies.")
    print("You can paste either the full JSON export or a Cookie header string (key=value; ...)")
    raw_cookies = input("5. Paste Gamblit cookies: ").strip()

    env_content = f"""# Gamblit Promo Code Auto-Redeemer Configuration
DISCORD_TOKEN={discord_token}
DISCORD_GUILD_ID={discord_guild_id or 0}
DISCORD_CHANNEL_ID={discord_channel_id or 0}

GAMBLIT_BASE_URL={gamblit_url}
GAMBLIT_COOKIES='{raw_cookies}'
GAMBLIT_USER_AGENT=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36

REDEEM_ENDPOINTS=/api/promo/redeem,/api/codes/redeem,/api/promocode/redeem,/api/user/redeem
CONNECT_TIMEOUT_SEC=3.0
READ_TIMEOUT_SEC=5.0
MAX_RETRIES=2
RATE_LIMIT_BACKOFF_FACTOR=1.5

DATABASE_PATH=data/gamblit.db
LOG_LEVEL=INFO
LOG_FILE=logs/app.log
"""

    env_file = Path(".env")
    with open(env_file, "w", encoding="utf-8") as f:
        f.write(env_content)

    print("\n✅ Configuration written to .env!")
    print("You can now test your authentication with:")
    print("    python main.py --test-auth")
    print()


if __name__ == "__main__":
    prompt_setup()

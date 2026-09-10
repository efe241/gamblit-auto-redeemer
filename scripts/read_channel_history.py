import asyncio
import json
import sys
import aiohttp

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import os
TOKEN = os.getenv("DISCORD_TOKEN", "")
CHANNEL_ID = os.getenv("DISCORD_CHANNEL_ID", "1369748391680016484")

async def main():
    headers = {
        "Authorization": TOKEN,
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    
    url = f"https://discord.com/api/v10/channels/{CHANNEL_ID}/messages?limit=10"
    
    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.get(url) as resp:
            if resp.status == 200:
                messages = await resp.json()
                print(f"[OK] Kanaldan {len(messages)} mesaj basariyla okundu!\n")
                print("="*65)
                for m in reversed(messages):
                    author = m.get("author", {}).get("username", "Bilinmeyen")
                    content = m.get("content", "")
                    ts = m.get("timestamp", "")
                    print(f"[{ts[:19]}] @{author}: {content}")
                print("="*65)
            else:
                body = await resp.text()
                print(f"[HATA] Kanal okunamadi! HTTP {resp.status}: {body}")

asyncio.run(main())

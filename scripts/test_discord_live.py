import asyncio
import json
import time
import sys
import websockets
import aiohttp

# UTF-8 stdout
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
    print(f"[*] Discord Token ve Kanal kontrol ediliyor...")
    print(f"[*] Kanal ID: {CHANNEL_ID}")
    
    headers = {"Authorization": TOKEN, "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.get("https://discord.com/api/v10/users/@me") as resp:
            if resp.status == 200:
                u = await resp.json()
                print(f"[OK] Token GECERLI! Discord Hesabi: {u.get('username')} (ID: {u.get('id')})")
            else:
                print(f"[HATA] Token gecersiz! Status: {resp.status}")
                return

        # Kanal bilgisi kontrol
        async with session.get(f"https://discord.com/api/v10/channels/{CHANNEL_ID}") as resp:
            if resp.status == 200:
                ch = await resp.json()
                ch_name = ch.get('name', 'kanal').encode('ascii', 'replace').decode('ascii')
                print(f"[OK] Hedef Kanal Bulundu: #{ch_name} (Guild ID: {ch.get('guild_id')})")
            else:
                print(f"[BILGI] Kanal dogrudan sorgulanamadi ({resp.status}), gateway uzerinden dinlenecek.")

    print("\n" + "="*60)
    print(">> CANLI DINLEME BASLADI!")
    print(f">> Discord'da o kanala herhangi bir mesaj yaz (Orn: 'KOD: TEST123')")
    print(">> Mesaj atildigi anda burada gozukecektir.")
    print("="*60 + "\n")

    # Gateway dinleme (WebSocket)
    gateway_url = "wss://gateway.discord.gg/?v=9&encoding=json"
    async with websockets.connect(gateway_url, max_size=10_000_000) as ws:
        hello_msg = json.loads(await ws.recv())
        hb_interval = hello_msg["d"]["heartbeat_interval"] / 1000.0

        async def heartbeat():
            try:
                while True:
                    await asyncio.sleep(hb_interval)
                    await ws.send(json.dumps({"op": 1, "d": None}))
            except asyncio.CancelledError:
                pass

        hb_task = asyncio.create_task(heartbeat())

        # Identify payload (Discord self-bot / client)
        identify_payload = {
            "op": 2,
            "d": {
                "token": TOKEN,
                "capabilities": 8189,
                "properties": {
                    "os": "Windows",
                    "browser": "Chrome",
                    "device": "",
                    "system_locale": "tr-TR",
                    "browser_user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "browser_version": "130.0.0.0",
                    "os_version": "10",
                    "referrer": "",
                    "referring_domain": "",
                    "referrer_current": "",
                    "referring_domain_current": "",
                    "release_channel": "stable",
                    "client_build_number": 334992,
                    "client_event_source": None
                },
                "presence": {
                    "status": "online",
                    "since": 0,
                    "activities": [],
                    "afk": False
                },
                "compress": False,
                "client_state": {
                    "guild_versions": {},
                    "highest_last_message_id": "0",
                    "read_state_version": 0,
                    "user_guild_settings_version": -1,
                    "user_settings_version": -1
                }
            }
        }
        await ws.send(json.dumps(identify_payload))

        start_time = time.time()
        # 120 saniye boyunca mesaj bekle
        while time.time() - start_time < 120:
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=120.0)
            except asyncio.TimeoutError:
                print("[-] 120 saniye boyunca mesaj gelmedi.")
                break

            data = json.loads(msg)
            t = data.get("t")
            d = data.get("d")

            if t == "READY":
                user = d.get("user", {})
                print(f"[OK] Discord Gateway'e BAGLANDI! Aktif Kullanici: {user.get('username')}")
                print("[*] Hedef kanal dinleniyor... Mesaj bekleniyor...")

            elif t == "MESSAGE_CREATE":
                ch_id = str(d.get("channel_id"))
                author = d.get("author", {}).get("username", "Bilinmeyen")
                content = d.get("content", "")
                
                if ch_id == CHANNEL_ID:
                    print(f"\n========================================================")
                    print(f"🎉 MESAJ ANINDA YAKALANDI!")
                    print(f"Kanal ID : #{ch_id}")
                    print(f"Gonderen : {author}")
                    print(f"Mesaj    : {content}")
                    print(f"Zaman    : {time.strftime('%H:%M:%S')}")
                    print(f"========================================================\n")
                    break
                else:
                    # Başka kanaldan da gelse test amaçlı haber verelim
                    pass

        hb_task.cancel()

asyncio.run(main())

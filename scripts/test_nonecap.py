import asyncio
import aiohttp
import time

import os

API_KEY = os.getenv("NONECAP_API_KEY", "")
SITEKEY = "60fa63fa-7302-4baa-9d64-8b60bc80a6dc"
PAGE_URL = "https://gamblit.net"

async def test_nonecap():
    print(f"[*] NoneCap API Testi Basliyor...")
    print(f"[*] Hedef Sitekey: {SITEKEY}")
    print(f"[*] Hedef URL: {PAGE_URL}")
    
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "type": "hcaptcha",
        "sitekey": SITEKEY,
        "url": PAGE_URL
    }
    
    t0 = time.perf_counter()
    async with aiohttp.ClientSession(headers=headers) as session:
        # NoneCap wait parametresi ile tek istekte bekleyip çözümü dönebiliyor
        url = "https://api.nonecap.com/v1/solves?wait=45"
        print("[*] NoneCap sunucusuna cozum istegi gonderildi, bekleniyor...")
        
        async with session.post(url, json=payload, timeout=50) as resp:
            elapsed = time.perf_counter() - t0
            print(f"[*] HTTP Yanit Kodu: {resp.status} (Gecen sure: {elapsed:.2f}s)")
            data = await resp.json()
            print(f"[*] Yanit: {data}")
            
            token = data.get("token") or (data.get("solution", {}).get("token") if isinstance(data.get("solution"), dict) else None)
            if token:
                print("\n========================================================")
                print(f"🎉 NONECAP CAPTCHA'YI BASARIYLA COZDU!")
                print(f"--> Cozum Suresi: {elapsed:.2f} saniye")
                print(f"--> Token Boyutu: {len(token)} karakter")
                print(f"--> Token Ilk 40: {token[:40]}...")
                print("========================================================\n")
                return token
            else:
                print(f"[!] Token donmedi veya beklenmeyen format: {data}")

asyncio.run(test_nonecap())

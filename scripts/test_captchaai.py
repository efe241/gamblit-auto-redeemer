import asyncio
import aiohttp
import time

API_KEY = "xevjse6oa7sp6au4ltju4vqcmnmaui8j"
SITEKEY = "60fa63fa-7302-4baa-9d64-8b60bc80a6dc"
PAGEURL = "https://gamblit.net"

async def test_captchaai():
    print(f"[*] CaptchaAI API Key test ediliyor: {API_KEY[:8]}...")
    
    # 1. Bakiye / Thread sorgulama
    async with aiohttp.ClientSession() as session:
        bal_url = f"https://ocr.captchaai.com/res.php?key={API_KEY}&action=getbalance&json=1"
        try:
            async with session.get(bal_url, timeout=10) as r:
                text = await r.text()
                print(f"[*] Bakiye / Durum Yaniti: {text}")
        except Exception as e:
            print(f"[!] Bakiye hatasi: {e}")

        # 2. Görev Gönderme (in.php)
        print("\n[*] hCaptcha Çözüm Görevi Gönderiliyor...")
        post_url = "https://ocr.captchaai.com/in.php"
        data = {
            "key": API_KEY,
            "method": "hcaptcha",
            "sitekey": SITEKEY,
            "pageurl": PAGEURL,
            "invisible": 1,
            "json": 1
        }
        
        t0 = time.time()
        async with session.post(post_url, data=data, timeout=15) as r:
            res = await r.json(content_type=None)
            print(f"[*] Görev Yanıtı: {res}")
            if res.get("status") != 1:
                print(f"[HATA] Görev kabul edilmedi: {res.get('request')}")
                return
            task_id = res.get("request")
            print(f"[OK] Görev ID Alındı: {task_id}")

        # 3. Sonuç Bekleme (res.php polling)
        print("[*] Çözüm bekleniyor (her 5 sn)...")
        res_url = f"https://ocr.captchaai.com/res.php?key={API_KEY}&action=get&id={task_id}&json=1"
        
        for attempt in range(25):
            await asyncio.sleep(5)
            async with session.get(res_url, timeout=10) as r:
                poll_res = await r.json(content_type=None)
                req = poll_res.get("request")
                if poll_res.get("status") == 1:
                    elapsed = time.time() - t0
                    print(f"\n🎉 CAPTCHA BAŞARIYLA ÇÖZÜLDÜ!")
                    print(f"--> Geçen Süre: {elapsed:.2f} saniye")
                    print(f"--> Token: {req[:40]}... (Toplam {len(req)} karakter)")
                    return req
                elif req == "CAPCHA_NOT_READY":
                    print(f"[{int(time.time()-t0)}s] Çözülüyor...")
                else:
                    print(f"[!] Beklenmeyen durum: {req}")
                    return

asyncio.run(test_captchaai())

import asyncio
import aiohttp
import re
import sys

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

async def inspect():
    async with aiohttp.ClientSession() as s:
        async with s.get("https://gamblit.net") as r:
            html = await r.text()
            print("HTML length:", len(html))
            scripts = re.findall(r'src=["\']([^"\']+\.js)["\']', html)
            print("Found scripts:", scripts)
            for sc in scripts:
                url = f"https://gamblit.net{sc}" if sc.startswith("/") else sc
                async with s.get(url) as sr:
                    js = await sr.text()
                    print(f"\nAnalyzing {sc} (size: {len(js)} bytes)...")
                    # Search promo / redeem
                    promo_matches = re.findall(r'.{0,50}(?:promo|redeem|coupon|bonus).{0,50}', js, re.IGNORECASE)
                    if promo_matches:
                        print(f"Promo/Redeem snippets ({len(promo_matches)} found):")
                        for snippet in promo_matches[:5]:
                            print("  ->", repr(snippet.strip()))
                    
                    # Search for API URLs
                    urls = set(re.findall(r'https?://[a-zA-Z0-9_\-\.:]+', js))
                    interesting_urls = [u for u in urls if "gamblit" in u or "api" in u or "backend" in u]
                    if interesting_urls:
                        print("Interesting URLs:", interesting_urls)
                    
                    # Search for socket/websocket
                    socket_matches = re.findall(r'.{0,40}(?:socket|websocket|io\().{0,40}', js, re.IGNORECASE)
                    if socket_matches:
                        print("Socket snippets:")
                        for sn in socket_matches[:3]:
                            print("  ->", repr(sn.strip()))

if __name__ == "__main__":
    asyncio.run(inspect())

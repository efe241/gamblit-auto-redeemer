import asyncio
import aiohttp
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from app.config import cfg

async def probe():
    cookies = cfg.parsed_cookies
    print(f"Loaded {len(cookies)} cookies: {list(cookies.keys())}")
    
    headers = {
        "User-Agent": cfg.gamblit_user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://gamblit.net/",
    }
    
    jar = aiohttp.CookieJar(unsafe=True)
    jar.update_cookies(cookies, response_url=aiohttp.client_reqrep.URL("https://gamblit.net"))
    
    async with aiohttp.ClientSession(cookie_jar=jar, headers=headers) as session:
        endpoints = [
            "/",
            "/api/user/me",
            "/api/user",
            "/api/profile",
            "/api/user/balance",
            "/api/tips",
            "/api/codes",
            "/api/promo",
        ]
        for ep in endpoints:
            url = f"https://gamblit.net{ep}"
            try:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    text = await resp.text()
                    title = ""
                    if "<title>" in text:
                        title = text.split("<title>")[1].split("</title>")[0].strip()
                    print(f"{ep:<20} -> HTTP {resp.status} | Title: {title} | Sample: {text[:120].strip()}")
            except Exception as e:
                print(f"{ep:<20} -> Error: {e}")

if __name__ == "__main__":
    asyncio.run(probe())

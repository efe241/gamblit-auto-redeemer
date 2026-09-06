import urllib.request
import sys

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

url = "https://gamblit.net/assets/Promo-3OVhMfxG.js"
req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
data = urllib.request.urlopen(req).read().decode("utf-8")

print(f"Promo chunk size: {len(data)} bytes")
print("Content:\n")
print(data)

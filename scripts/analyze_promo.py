import urllib.request
import re
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

with open("data/promo_raw.js", "w", encoding="utf-8") as f:
    f.write(data)

print(f"Saved {len(data)} bytes to data/promo_raw.js")

# Find function calls, API URLs, socket events
urls = set(re.findall(r'["\'](/[^"\']+)["\']', data))
print("Paths found in Promo:", urls)

# Search for emit or post or fetch
calls = re.findall(r'.{0,40}(?:fetch|post|emit|axios|api).{0,40}', data)
for c in calls[:10]:
    print("Call snippet:", repr(c.strip()))

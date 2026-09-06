import urllib.request
import re
import sys

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

url = "https://gamblit.net/assets/index-QiJiRETz.js"
req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
data = urllib.request.urlopen(req).read().decode("utf-8")

matches = re.findall(r'PromoModal[^:]*:\s*\(\)\s*=>\s*se\(\(\)\s*=>\s*import\(([^)]+)\)', data)
print("PromoModal imports:", matches)

# Find all occurrences of PromoModal in the file
for m in re.finditer(r'PromoModal', data):
    start = max(0, m.start() - 100)
    end = min(len(data), m.end() + 150)
    print("Snippet around PromoModal:\n", data[start:end], "\n---")

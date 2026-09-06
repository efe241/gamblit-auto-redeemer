import urllib.request
import re
import sys

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

req = urllib.request.Request("https://gamblit.net/assets/index-QiJiRETz.js", headers={"User-Agent": "Mozilla/5.0"})
data = urllib.request.urlopen(req).read().decode("utf-8")

for m in re.finditer(r'case\s*["\'`]CHALLENGE["\'`]\s*:', data):
    idx = m.start()
    print("Found case CHALLENGE:")
    print(data[idx:idx+600])
    print("="*60)

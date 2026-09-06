import urllib.request

req = urllib.request.Request("https://gamblit.net/assets/index-QiJiRETz.js", headers={"User-Agent": "Mozilla/5.0"})
data = urllib.request.urlopen(req).read().decode("utf-8")

idx = data.find('case"PAT":')
print(data[idx:idx+1000])

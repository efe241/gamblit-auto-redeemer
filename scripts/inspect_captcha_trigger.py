with open("data/promo_raw.js", encoding="utf-8") as f:
    text = f.read()

idx = text.find('size:"invisible"')
print(text[max(0, idx-300):min(len(text), idx+300)])

with open("data/promo_raw.js", encoding="utf-8") as f:
    text = f.read()

idx = text.find('ID:"ClaimPromoCode"')
print(text[max(0, idx-400):min(len(text), idx+600)])

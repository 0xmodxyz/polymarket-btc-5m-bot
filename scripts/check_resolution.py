import json, requests

r = requests.get('https://clob.polymarket.com/markets/0x1011176cc0e2f0c08b04e3c25fbf2965457ca1bc6709592e1199c2f0018718db')
data = r.json()
print('Active:', data.get('active'))
print('Closed:', data.get('closed'))
print('Tokens:')
for t in data.get('tokens', []):
    print(f"  {t['outcome']}: price={t['price']}, winner={t.get('winner')}")

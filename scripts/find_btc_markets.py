import requests

r = requests.get("https://clob.polymarket.com/markets", params={"limit": 1000}, timeout=30)
data = r.json()
markets = data.get("data", [])

btc_markets = []
for m in markets:
    slug = m.get("slug", "")
    title = m.get("title", m.get("question", ""))
    if "btc" in slug.lower() or "bitcoin" in title.lower() or "updown" in slug.lower():
        btc_markets.append((slug, title))

print(f"Found {len(btc_markets)} BTC-related markets:")
for slug, title in btc_markets[:20]:
    print(f"  {slug}: {str(title)[:80]}")

import requests

url = "https://gamma-api.polymarket.com/events"

# Search for BTC/crypto markets
for search_term in ["btc", "bitcoin", "crypto", "btc-updown"]:
    r = requests.get(url, params={"tag": search_term, "limit": 5}, timeout=10)
    if r.status_code == 200:
        data = r.json()
        for ev in data[:5]:
            s = ev.get("slug", "")
            t = ev.get("title", "")[:80]
            print(f"[{search_term}] {s}: {t}")

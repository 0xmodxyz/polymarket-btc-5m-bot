import requests

# Try different API endpoints
endpoints = [
    ("/markets", {"tag": "btc", "limit": 5}),
    ("/markets", {"closed": "false", "limit": 20}),
    ("/events", {"closed": "false", "limit": 10, "order": "createdAt:desc"}),
]

for path, params in endpoints:
    url = f"https://gamma-api.polymarket.com{path}"
    r = requests.get(url, params=params, timeout=15)
    data = r.json()
    print(f"{path} ({params}): {len(data)} results")
    for item in data[:10]:
        slug = item.get("slug", "")
        title = item.get("title", item.get("question", ""))[:60]
        if "btc" in slug.lower() or "bitcoin" in title.lower() or "5m" in slug.lower() or "updown" in slug.lower():
            print(f"  >> {slug}: {title}")

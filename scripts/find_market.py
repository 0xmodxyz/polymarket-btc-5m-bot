import requests, time
ts = int(time.time())
window_start = (ts // 300) * 300
slug = f"btc-updown-5m-{window_start}"
print(f"Current time UTC: {time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(ts))}")
print(f"Current slug: {slug}")

url = "https://gamma-api.polymarket.com/events"
r = requests.get(url, params={"slug": slug}, timeout=10)
print(f"Status: {r.status_code}")
if r.status_code == 200:
    data = r.json()
    print(f"Found {len(data)} events")
    if data:
        e = data[0]
        print(f"Title: {e.get('title')}")
        print(f"Slug: {e.get('slug')}")
    else:
        # Search API
        r2 = requests.get(url, params={"tag": "btc-updown-5m"}, timeout=10)
        data2 = r2.json()
        print(f"Search by tag: found {len(data2)} events")
        for ev in data2[:5]:
            print(f"  {ev.get('slug')}: {ev.get('title','')[:60]}")

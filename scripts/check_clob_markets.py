import requests

# Check CLOB markets endpoint
r = requests.get("https://clob.polymarket.com/markets", params={"limit": 5}, timeout=10)
print(f"Status: {r.status_code}")
data = r.json()
print(f"Response type: {type(data).__name__}")
if isinstance(data, dict):
    print(f"Keys: {list(data.keys())[:10]}")
    for k, v in list(data.items())[:5]:
        if isinstance(v, list):
            print(f"  {k}: list of {len(v)} items")
        else:
            print(f"  {k}: {str(v)[:100]}")
elif isinstance(data, list):
    print(f"List of {len(data)} items")
    for m in data[:5]:
        print(f"  {m.get('slug', '')[:80]}")

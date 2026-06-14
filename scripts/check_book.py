import json, sys
from dotenv import load_dotenv
load_dotenv()
sys.path.insert(0, ".")
from bot.config import settings
from bot.client import build_deposit_wallet_client
from bot.markets import fetch_market

client = build_deposit_wallet_client(settings)
m = fetch_market()

for side, tid in [("Up", m.up.token_id), ("Down", m.down.token_id)]:
    book = client.get_book(tid)
    bids = book.get("bids", [])
    asks = book.get("asks", [])
    print(f"{side}:")
    print(f"  best_bid={bids[0]['price'] if bids else '-'}  best_ask={asks[0]['price'] if asks else '-'}")
    print(f"  bids: {[(b['price'], b['size']) for b in bids[:3]]}")
    print(f"  asks: {[(a['price'], a['size']) for a in asks[:3]]}")

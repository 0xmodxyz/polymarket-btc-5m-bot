import sys, json, logging
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from py_clob_client_v2 import ClobClient, SignatureTypeV2
from py_clob_client_v2.clob_types import AssetType, BalanceAllowanceParams
from bot.config import load_settings

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
settings = load_settings()
funder = settings.deposit_wallet_address or settings.funder
client = ClobClient('https://clob.polymarket.com', key=settings.private_key, chain_id=settings.chain_id, signature_type=SignatureTypeV2.POLY_1271, funder=funder)
creds = client.create_or_derive_api_key()
client.set_api_creds(creds)

# Check the specific order
order_id = "0x4e57a3cef22aedc925ac31d1c89f72e3fac5477f700bae0f969f6922ac81e6ce"
order = client.get_order(order_id)
print("=== Order ===")
print(json.dumps(order, indent=2)[:1500])

# Check trades
trades = client.get_trades()
print("\n=== Trades ===")
print(json.dumps(trades[:3], indent=2)[:2000] if trades else "None")

# Get market by token to find condition ID
token_id = '19381737554030529431432490254576380375639458534197377848565069177242730202310'
token_info = client.get_market_by_token(token_id)
print("\n=== Token Info ===")
print(json.dumps(token_info, indent=2)[:2000])

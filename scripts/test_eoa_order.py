from __future__ import annotations

import json, logging, sys, time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from py_clob_client_v2 import ClobClient, MarketOrderArgsV2, OrderType, PartialCreateOrderOptions, SignatureTypeV2
from py_clob_client_v2.order_builder.constants import BUY
from py_clob_client_v2.clob_types import AssetType, BalanceAllowanceParams
from bot.config import load_settings
from bot.markets import fetch_market
from bot.orders import pick_cheaper_outcome, _get_best_ask, _get_tick_size, _get_neg_risk

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')

settings = load_settings()
# For signature_type=1, funder = signer EOA
funder = settings.funder
client = ClobClient('https://clob.polymarket.com', key=settings.private_key, chain_id=settings.chain_id, signature_type=SignatureTypeV2.POLY_1271 if settings.signature_type == 3 else SignatureTypeV2.EOA, funder=funder)
creds = client.create_or_derive_api_key()
client.set_api_creds(creds)

# Sync + check balance
sync = client.update_balance_allowance(BalanceAllowanceParams(asset_type=AssetType.COLLATERAL))
print("Sync:", sync)

bal = client.get_balance_allowance(BalanceAllowanceParams(asset_type=AssetType.COLLATERAL))
print(json.dumps(bal, indent=2))

# Find market
market = fetch_market()
outcome = pick_cheaper_outcome(market)
token = outcome

tick_size = _get_tick_size(token.token_id)
neg_risk = _get_neg_risk(token.token_id)
print(f"Token: {token.token_id}, Outcome: {token.outcome}, Tick: {tick_size}, NegRisk: {neg_risk}")

# Place $1 FOK buy
resp = client.create_and_post_market_order(
    MarketOrderArgsV2(token_id=token.token_id, amount=1.0, side=BUY),
    options=PartialCreateOrderOptions(tick_size=tick_size, neg_risk=neg_risk),
    order_type=OrderType.FOK,
)
print("Order result:", json.dumps(resp, indent=2))

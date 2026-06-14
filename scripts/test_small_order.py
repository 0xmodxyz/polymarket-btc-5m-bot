import sys, json, logging
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from py_clob_client_v2 import ClobClient, MarketOrderArgsV2, OrderType, PartialCreateOrderOptions, SignatureTypeV2
from py_clob_client_v2.clob_types import AssetType, BalanceAllowanceParams
from py_clob_client_v2.order_builder.constants import BUY
from bot.config import load_settings
from bot.markets import fetch_market
from bot.orders import pick_cheaper_outcome, _get_best_ask, _get_tick_size, _get_neg_risk

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')

settings = load_settings()
funder = settings.deposit_wallet_address or settings.funder
client = ClobClient('https://clob.polymarket.com', key=settings.private_key, chain_id=settings.chain_id, signature_type=SignatureTypeV2.POLY_1271, funder=funder)
creds = client.create_or_derive_api_key()
client.set_api_creds(creds)

# Sync balance
sync = client.update_balance_allowance(BalanceAllowanceParams(asset_type=AssetType.COLLATERAL))
print("Balance sync response:", sync)

bal = client.get_balance_allowance(BalanceAllowanceParams(asset_type=AssetType.COLLATERAL))
print(json.dumps(bal, indent=2))

market = fetch_market()
outcome = pick_cheaper_outcome(market)
token = outcome

best_ask = _get_best_ask(token.token_id)
tick_size = _get_tick_size(token.token_id)
neg_risk = _get_neg_risk(token.token_id)
print(f'Token: {token.token_id}')
print(f'Outcome: {token.outcome}')
print(f'Best ask: {best_ask}')
print(f'Tick size: {tick_size}')
print(f'Neg risk: {neg_risk}')

amt = 1.0
resp = client.create_and_post_market_order(
    MarketOrderArgsV2(token_id=token.token_id, amount=amt, side=BUY),
    options=PartialCreateOrderOptions(tick_size=tick_size, neg_risk=neg_risk),
    order_type=OrderType.FOK,
)
print(f"amount={amt}: SUCCESS", json.dumps(resp, indent=2))

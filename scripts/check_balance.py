from dotenv import load_dotenv
load_dotenv()
import sys
sys.path.insert(0, ".")
from bot.config import load_settings
from bot.client import build_deposit_wallet_client
from py_clob_client_v2.clob_types import BalanceAllowanceParams, AssetType

s = load_settings()
c = build_deposit_wallet_client(s)
c.update_balance_allowance(BalanceAllowanceParams(asset_type=AssetType.COLLATERAL, signature_type=s.signature_type))
bal = c.get_balance_allowance(BalanceAllowanceParams(asset_type=AssetType.COLLATERAL, signature_type=s.signature_type))
usdc = float(bal["balance"]) / 1e6
print(f"Balance: ${usdc:.2f}")

import os
from dataclasses import dataclass, field
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

HOST = "https://clob.polymarket.com"
GAMMA_API = "https://gamma-api.polymarket.com"


@dataclass(frozen=True)
class BuilderCreds:
    api_key: str
    secret: str
    passphrase: str


@dataclass(frozen=True)
class Settings:
    private_key: str
    funder: str
    signature_type: int
    chain_id: int
    max_budget_usd: float
    max_per_window_usd: float
    test_order_usd: float
    builder_creds: Optional[BuilderCreds] = None
    relayer_url: str = "https://relayer-v2.polymarket.com"
    deposit_wallet_address: Optional[str] = None
    pusd_address: str = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"


def load_settings() -> Settings:
    private_key = os.environ.get("POLYMARKET_PRIVATE_KEY", "").strip()
    funder = os.environ.get("POLYMARKET_FUNDER", "").strip()
    if not private_key or not funder:
        raise ValueError("POLYMARKET_PRIVATE_KEY and POLYMARKET_FUNDER must be set in .env")

    builder_key = os.environ.get("BUILDER_API_KEY", "").strip()
    builder_secret = os.environ.get("BUILDER_SECRET", "").strip()
    builder_passphrase = os.environ.get("BUILDER_PASSPHRASE", "").strip()
    builder_creds = None
    if builder_key and builder_secret and builder_passphrase:
        builder_creds = BuilderCreds(
            api_key=builder_key,
            secret=builder_secret,
            passphrase=builder_passphrase,
        )

    dw = os.environ.get("DEPOSIT_WALLET_ADDRESS", "").strip()

    return Settings(
        private_key=private_key,
        funder=funder,
        signature_type=int(os.environ.get("POLYMARKET_SIGNATURE_TYPE", "1")),
        chain_id=int(os.environ.get("POLYMARKET_CHAIN_ID", "137")),
        max_budget_usd=float(os.environ.get("MAX_BUDGET_USD", "50")),
        max_per_window_usd=float(os.environ.get("MAX_PER_WINDOW_USD", "5")),
        test_order_usd=float(os.environ.get("TEST_ORDER_USD", "1")),
        builder_creds=builder_creds,
        relayer_url=os.environ.get("RELAYER_URL", "https://relayer-v2.polymarket.com"),
        deposit_wallet_address=dw if dw else None,
        pusd_address=os.environ.get("PUSD_ADDRESS", "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"),
    )

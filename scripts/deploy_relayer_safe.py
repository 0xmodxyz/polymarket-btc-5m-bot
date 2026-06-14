from __future__ import annotations

import logging, sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from py_builder_relayer_client.client import RelayClient
from py_builder_signing_sdk.config import BuilderConfig
from py_builder_signing_sdk.sdk_types import BuilderApiKeyCreds
from polymarket.environments import PRODUCTION as PROD
from bot.config import load_settings
settings = load_settings()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("deploy_relayer_safe")

def main():
    key = settings.builder_creds.api_key
    secret = settings.builder_creds.secret
    passphrase = settings.builder_creds.passphrase
    if not all([key, secret, passphrase]):
        logger.error("BUILDER_API_KEY, BUILDER_SECRET, BUILDER_PASSPHRASE must be set")
        return 1

    builder_creds = BuilderApiKeyCreds(
        key=key, secret=secret, passphrase=passphrase
    )
    builder_config = BuilderConfig(local_builder_creds=builder_creds)

    # Use old EOA as signer (the builder API key owner)
    relayer = RelayClient(
        settings.relayer_url,
        settings.chain_id,
        private_key=settings.private_key,
        builder_config=builder_config,
    )

    safe_address = relayer.get_expected_safe()
    logger.info("Expected Safe address: %s", safe_address)
    logger.info("Signer address: %s", relayer.signer.address())

    deployed = relayer.get_deployed(safe_address)
    logger.info("Already deployed (via relayer): %s", deployed)

    if deployed:
        logger.info("Safe already deployed. No action needed.")
    else:
        logger.info("Deploying Safe via relayer...")
        response = relayer.deploy()
        logger.info("Deploy submitted: %s", response.transaction_id)
        confirmed = relayer.poll_until_state(
            response.transaction_id,
            ["CONFIRMED"],
            "FAILED",
            max_polls=60,
            poll_frequency=5000,
        )
        if confirmed:
            logger.info("Safe deployed at: %s", confirmed.get("proxyAddress", safe_address))
        else:
            logger.error("Deploy failed!")
            return 1

    print("\n=== Safe Info ===")
    print(f"Safe address: {safe_address}")
    print(f"Signer: {relayer.signer.address()}")
    print(f"Factory: {relayer.contract_config.safe_factory}")

if __name__ == "__main__":
    raise SystemExit(main())

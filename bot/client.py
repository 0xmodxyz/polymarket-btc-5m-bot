"""Polymarket CLOB client wrapper."""

from py_clob_client_v2 import ClobClient, SignatureTypeV2

from bot.config import HOST, Settings


def build_client(settings: Settings) -> ClobClient:
    client = ClobClient(
        HOST,
        key=settings.private_key,
        chain_id=settings.chain_id,
        signature_type=settings.signature_type,
        funder=settings.funder,
    )
    creds = client.create_or_derive_api_key()
    client.set_api_creds(creds)
    return client


def build_deposit_wallet_client(settings: Settings) -> ClobClient:
    funder = settings.deposit_wallet_address or settings.funder
    client = ClobClient(
        HOST,
        key=settings.private_key,
        chain_id=settings.chain_id,
        signature_type=SignatureTypeV2.POLY_1271,
        funder=funder,
    )
    creds = client.create_or_derive_api_key()
    client.set_api_creds(creds)
    return client

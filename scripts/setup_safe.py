from __future__ import annotations

import logging, sys, time, json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from py_builder_relayer_client.client import RelayClient
from py_builder_relayer_client.models import DepositWalletCall, TransactionType
from py_builder_signing_sdk.config import BuilderApiKeyCreds, BuilderConfig
from web3 import Web3
from polymarket.environments import PRODUCTION as PROD
from eth_account.messages import encode_typed_data

from bot.config import load_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("setup_safe")

PUSD = "0xC011a7E12a19f7B1f670d46F03B03f3342E82DFB"
SAFE_ADDRESS = "0x53cac4079f996a4caa76db02f7320ef806d924b6"
EXCHANGES = [
    "0xE111180000d2663C0091e4f400237545B87B996B",
    "0xe2222d279d744050d28e00520010520000310F59",
    "0xd91E80cF2E7be2e162c6513ceD06f1dD0dA35296",
]

ERC20_ABI = [{"constant":True,"inputs":[{"name":"who","type":"address"}],"name":"balanceOf","outputs":[{"name":"","type":"uint256"}],"type":"function"}]

SAFE_ABI = [
    {"inputs":[{"internalType":"address","name":"to","type":"address"},{"internalType":"uint256","name":"value","type":"uint256"},{"internalType":"bytes","name":"data","type":"bytes"},{"internalType":"enum.Enum.Operation","name":"operation","type":"uint8"},{"internalType":"uint256","name":"safeTxGas","type":"uint256"},{"internalType":"uint256","name":"baseGas","type":"uint256"},{"internalType":"uint256","name":"gasPrice","type":"uint256"},{"internalType":"address","name":"gasToken","type":"address"},{"internalType":"address payable","name":"refundReceiver","type":"address"},{"internalType":"bytes","name":"signatures","type":"bytes"}],"name":"execTransaction","outputs":[{"internalType":"bool","name":"","type":"bool"}],"stateMutability":"payable","type":"function"},
    {"inputs":[],"name":"nonce","outputs":[{"internalType":"uint256","name":"","type":"uint256"}],"stateMutability":"view","type":"function"},
    {"inputs":[{"internalType":"bytes32","name":"dataHash","type":"bytes32"},{"internalType":"bytes","name":"signatures","type":"bytes"}],"name":"checkNSignatures","outputs":[],"stateMutability":"view","type":"function"},
]

def _approve_calldata(spender: str) -> str:
    return f"0x095ea7b3{spender[2:].lower().zfill(64)}{'ff' * 32}"

def _run_relayer_batch(relayer, calls, dw, nonce):
    response = relayer.execute_deposit_wallet_batch(
        calls=calls, wallet_address=dw,
        nonce=nonce, deadline=str(int(time.time()) + 600),
    )
    logger.info("Submitted! Tx ID: %s", response.transaction_id)
    confirmed = relayer.poll_until_state(
        response.transaction_id, states=["STATE_CONFIRMED"],
        fail_state="STATE_FAILED", max_polls=60, poll_frequency=3000,
    )
    if not confirmed:
        logger.error("Failed or timed out")
        return False
    return True

def safe_tx_hash_data(w3, safe, to, value, data, operation, safe_tx_gas, base_gas, gas_price, gas_token, refund_receiver, nonce):
    """Compute SafeTx EIP-712 encoding"""
    from eth_utils.abi import function_abi_to_4byte_selector
    # keccak of "SafeTx(address to,uint256 value,bytes data,uint8 operation,uint256 safeTxGas,uint256 baseGas,uint256 gasPrice,address gasToken,address refundReceiver,uint256 nonce)"
    SAFE_TX_TYPEHASH = Web3.keccak(text="SafeTx(address to,uint256 value,bytes data,uint8 operation,uint256 safeTxGas,uint256 baseGas,uint256 gasPrice,address gasToken,address refundReceiver,uint256 nonce)")
    return Web3.solidity_keccak(
        ["bytes32", "address", "uint256", "bytes32", "uint8", "uint256", "uint256", "uint256", "address", "address", "uint256"],
        [SAFE_TX_TYPEHASH, to, value, Web3.keccak(hexstr=data), operation, safe_tx_gas, base_gas, gas_price, gas_token, refund_receiver, nonce]
    )

def compute_safe_tx_hash(w3, safe, to, value, data, operation, safe_tx_gas, base_gas, gas_price, gas_token, refund_receiver, nonce):
    chain_id = w3.eth.chain_id
    # EIP-712 domain for Safe v1.3.0: keccak256("EIP712Domain(uint256 chainId,address verifyingContract)")
    DOMAIN_SEPARATOR_TYPEHASH = Web3.keccak(text="EIP712Domain(uint256 chainId,address verifyingContract)")
    domain_separator = Web3.solidity_keccak(
        ["bytes32", "uint256", "address"],
        [DOMAIN_SEPARATOR_TYPEHASH, chain_id, safe]
    )
    tx_hash = safe_tx_hash_data(w3, safe, to, value, data, operation, safe_tx_gas, base_gas, gas_price, gas_token, refund_receiver, nonce)
    return Web3.solidity_keccak(["bytes1", "bytes1", "bytes32", "bytes32"], [b"\x19", b"\x01", domain_separator, tx_hash])

def approve_from_safe(w3, acct, safe_contract, safe_address, spender, nonce):
    call_data = Web3.to_hex(Web3.to_bytes(hexstr=_approve_calldata(spender)))
    to_addr = Web3.to_checksum_address(PUSD)
    null_addr = Web3.to_checksum_address("0x0000000000000000000000000000000000000000")

    safe_tx_hash = compute_safe_tx_hash(
        w3, safe_address, to_addr, 0, _approve_calldata(spender),
        0, 0, 0, 0, null_addr, null_addr, nonce
    )

    sig = acct.unsafe_sign_hash(safe_tx_hash)
    sig_bytes = sig.r.to_bytes(32, "big") + sig.s.to_bytes(32, "big") + bytes([sig.v]) + b"\x00"

    tx = safe_contract.functions.execTransaction(
        to_addr, 0, call_data, 0, 0, 0, 0,
        null_addr, null_addr, sig_bytes
    ).build_transaction({
        "from": acct.address, "nonce": w3.eth.get_transaction_count(acct.address),
        "gas": 200000, "gasPrice": w3.eth.gas_price, "chainId": 137,
    })
    signed = acct.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
    return receipt["status"] == 1

def main() -> int:
    settings = load_settings()
    w3 = Web3(Web3.HTTPProvider(PROD.rpc_url))
    acct = w3.eth.account.from_key(settings.private_key)
    dw = settings.deposit_wallet_address
    safe = Web3.to_checksum_address(SAFE_ADDRESS)

    if not settings.builder_creds:
        logger.error("BUILDER_API_KEY not set"); return 1
    builder_config = BuilderConfig(local_builder_creds=BuilderApiKeyCreds(
        key=settings.builder_creds.api_key, secret=settings.builder_creds.secret,
        passphrase=settings.builder_creds.passphrase,
    ))
    relayer = RelayClient(settings.relayer_url, settings.chain_id, settings.private_key, builder_config)

    bal_contract = w3.eth.contract(address=Web3.to_checksum_address(PUSD), abi=ERC20_ABI)

    # Step 1: Transfer pUSD from deposit wallet to Safe
    pusd_bal = bal_contract.functions.balanceOf(dw).call()
    logger.info("Deposit wallet pUSD: %s", pusd_bal)
    if pusd_bal > 0:
        nonce = str(relayer.get_nonce(relayer.signer.address(), TransactionType.WALLET.value)["nonce"])
        transfer_calldata = f"0xa9059cbb{safe[2:].lower().zfill(64)}{hex(pusd_bal)[2:].zfill(64)}"
        call = DepositWalletCall(target=PUSD, value="0", data=transfer_calldata)
        if not _run_relayer_batch(relayer, [call], dw, nonce):
            return 1
        logger.info("pUSD transferred to Safe")

    # Step 2: Send MATIC to Safe
    nonce = str(relayer.get_nonce(relayer.signer.address(), TransactionType.WALLET.value)["nonce"])
    if not _run_relayer_batch(relayer, [DepositWalletCall(target=safe, value=str(300_000_000_000_000_000), data="0x")], dw, nonce):
        return 1
    logger.info("MATIC sent to Safe")

    # Step 3: Approve exchanges from Safe
    safe_contract = w3.eth.contract(address=safe, abi=SAFE_ABI)
    safe_nonce = safe_contract.functions.nonce().call()

    for ex in EXCHANGES:
        logger.info("Approving %s...", ex)
        ok = approve_from_safe(w3, acct, safe_contract, safe, Web3.to_checksum_address(ex), safe_nonce)
        logger.info("Approved %s: %s", ex, ok)
        safe_nonce += 1
        if not ok:
            return 1

    logger.info("Safe pUSD: %s", bal_contract.functions.balanceOf(safe).call())
    print(f"\nSAFE_ADDRESS={SAFE_ADDRESS}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

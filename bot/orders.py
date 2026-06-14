"""Order placement helpers."""

from __future__ import annotations

import logging
from typing import Any

import requests
from py_clob_client_v2 import ClobClient, MarketOrderArgsV2, OrderArgs, OrderType, PartialCreateOrderOptions
from py_clob_client_v2.order_builder.constants import BUY, SELL

from bot.markets import Sol5mMarket, OutcomeToken

logger = logging.getLogger(__name__)

CLOB_HOST = "https://clob.polymarket.com"

_TOKEN_META_CACHE: dict[str, tuple[str, bool]] = {}


def _http_get(url: str, params: dict | None = None, timeout: int = 20, max_retries: int = 3) -> requests.Response:
    import time as tmod
    for attempt in range(max_retries):
        try:
            r = requests.get(url, params=params, timeout=timeout)
            if r.status_code == 429:
                wait = 0.5 * (2 ** attempt)
                logger.warning("Rate limited (429), retrying in %.1fs", wait)
                tmod.sleep(wait)
                continue
            r.raise_for_status()
            return r
        except requests.RequestException as e:
            if attempt == max_retries - 1:
                raise
            wait = 0.3 * (2 ** attempt)
            logger.debug("HTTP error %s, retry %d/%d in %.1fs", e, attempt + 1, max_retries, wait)
            tmod.sleep(wait)
    raise RuntimeError(f"HTTP GET failed after {max_retries} retries: {url}")


def cache_token_meta(token_id: str) -> None:
    if token_id in _TOKEN_META_CACHE:
        return
    ts = _get_tick_size(token_id)
    nr = _get_neg_risk(token_id)
    _TOKEN_META_CACHE[token_id] = (ts, nr)


def get_tick_size_cached(token_id: str) -> str:
    if token_id in _TOKEN_META_CACHE:
        return _TOKEN_META_CACHE[token_id][0]
    ts = _get_tick_size(token_id)
    _TOKEN_META_CACHE.setdefault(token_id, (ts, False))
    return ts


def get_neg_risk_cached(token_id: str) -> bool:
    if token_id in _TOKEN_META_CACHE:
        return _TOKEN_META_CACHE[token_id][1]
    nr = _get_neg_risk(token_id)
    _TOKEN_META_CACHE.setdefault(token_id, ("0.001", nr))
    return nr


def _get_tick_size(token_id: str) -> str:
    r = _http_get(f"{CLOB_HOST}/tick-size", params={"token_id": token_id})
    data = r.json()
    return str(data.get("minimum_tick_size") or data.get("tick_size") or "0.001")


def _get_neg_risk(token_id: str) -> bool:
    r = _http_get(f"{CLOB_HOST}/neg-risk", params={"token_id": token_id})
    data = r.json()
    return bool(data.get("neg_risk") if "neg_risk" in data else data.get("negRisk", False))


def _get_best_bid(token_id: str) -> float:
    r = _http_get(f"{CLOB_HOST}/book", params={"token_id": token_id})
    book = r.json()
    bids = book.get("bids") or []
    if not bids:
        raise RuntimeError("No bids in orderbook (illiquid market?)")
    return float(bids[0]["price"])


def place_market_buy_usd(
    client: ClobClient,
    token: OutcomeToken,
    amount_usd: float,
    current_price: float,
) -> dict[str, Any]:
    tick_size = get_tick_size_cached(token.token_id)
    neg_risk = get_neg_risk_cached(token.token_id)

    resp = client.create_and_post_market_order(
        MarketOrderArgsV2(
            token_id=token.token_id,
            amount=amount_usd,
            side=BUY,
        ),
        options=PartialCreateOrderOptions(tick_size=tick_size, neg_risk=neg_risk),
        order_type=OrderType.FAK,
    )
    logger.info(
        "Buy %.2f USD on %s @ price=%.4f (token=%s...): %s",
        amount_usd,
        token.outcome,
        current_price,
        token.token_id[:12],
        resp,
    )
    return resp


def place_market_sell_usd(
    client: ClobClient,
    token: OutcomeToken,
    amount_usd: float,
) -> dict[str, Any]:
    tick_size = get_tick_size_cached(token.token_id)
    neg_risk = get_neg_risk_cached(token.token_id)

    resp = client.create_and_post_market_order(
        MarketOrderArgsV2(
            token_id=token.token_id,
            amount=amount_usd,
            side=SELL,
        ),
        options=PartialCreateOrderOptions(tick_size=tick_size, neg_risk=neg_risk),
        order_type=OrderType.FAK,
    )
    logger.info(
        "Sell %.2f USD on %s (token=%s...): %s",
        amount_usd,
        token.outcome,
        token.token_id[:12],
        resp,
    )
    return resp


def cancel_all_open_orders(client: ClobClient) -> dict[str, Any] | None:
    try:
        resp = client.cancel_all()
        logger.info("All open orders cancelled: %s", resp)
        return resp
    except Exception as exc:
        logger.error("Cancel all orders failed: %s", exc)
        return None


async def async_get_best_bid(token_id: str) -> float:
    import asyncio
    return await asyncio.to_thread(_get_best_bid, token_id)


async def async_place_market_buy(client: ClobClient, token: OutcomeToken, amount_usd: float, current_price: float) -> dict[str, Any]:
    import asyncio
    return await asyncio.to_thread(place_market_buy_usd, client, token, amount_usd, current_price)


async def async_place_market_sell(client: ClobClient, token: OutcomeToken, amount_usd: float) -> dict[str, Any]:
    import asyncio
    return await asyncio.to_thread(place_market_sell_usd, client, token, amount_usd)


def place_limit_buy_shares(
    client: ClobClient,
    token: OutcomeToken,
    price: float,
    shares: float,
) -> dict[str, Any]:
    tick_size = get_tick_size_cached(token.token_id)
    neg_risk = get_neg_risk_cached(token.token_id)

    resp = client.create_and_post_order(
        OrderArgs(
            price=price,
            size=shares,
            side=BUY,
            token_id=token.token_id,
        ),
        options=PartialCreateOrderOptions(tick_size=tick_size, neg_risk=neg_risk),
        order_type=OrderType.GTC,
    )
    logger.info(
        "LIMIT BUY %.2f shares on %s @ price=%.4f (token=%s...): %s",
        shares, token.outcome, price, token.token_id[:12], resp
    )
    return resp


async def async_place_limit_buy_shares(client: ClobClient, token: OutcomeToken, price: float, shares: float) -> dict[str, Any]:
    import asyncio
    return await asyncio.to_thread(place_limit_buy_shares, client, token, price, shares)


def place_limit_buy_fak(
    client: ClobClient,
    token: OutcomeToken,
    price: float,
    shares: float,
) -> dict[str, Any]:
    """FAK limit buy — fills at target price or doesn't fill at all."""
    tick_size = get_tick_size_cached(token.token_id)
    neg_risk = get_neg_risk_cached(token.token_id)

    resp = client.create_and_post_order(
        OrderArgs(
            price=price,
            size=shares,
            side=BUY,
            token_id=token.token_id,
        ),
        options=PartialCreateOrderOptions(tick_size=tick_size, neg_risk=neg_risk),
        order_type=OrderType.FAK,
    )
    logger.info(
        "FAK BUY %.2f shares on %s @ price=%.4f (token=%s...): %s",
        shares, token.outcome, price, token.token_id[:12], resp
    )
    return resp


async def async_place_limit_buy_fak(client: ClobClient, token: OutcomeToken, price: float, shares: float) -> dict[str, Any]:
    import asyncio
    return await asyncio.to_thread(place_limit_buy_fak, client, token, price, shares)

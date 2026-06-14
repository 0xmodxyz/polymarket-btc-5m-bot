"""SOL 5-minute Up/Down market discovery via Gamma API."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import requests
from requests.adapters import HTTPAdapter, Retry

from bot.config import GAMMA_API

# Session with retry
_HTTP = requests.Session()
_HTTP.mount("https://", HTTPAdapter(max_retries=Retry(total=3, backoff_factor=0.5, status_forcelist=[429, 500, 502, 503, 504])))

WINDOW_SECONDS = 300


@dataclass(frozen=True)
class OutcomeToken:
    outcome: str
    token_id: str
    price: float | None


@dataclass(frozen=True)
class Sol5mMarket:
    slug: str
    event_id: str
    title: str
    up: OutcomeToken
    down: OutcomeToken
    window_start_ts: int


def current_window_start_ts(now: float | None = None) -> int:
    ts = int(now if now is not None else time.time())
    # SOL 5m markets are created for the next/ongoing window
    # Try current window first, fallback to next window
    return (ts // WINDOW_SECONDS) * WINDOW_SECONDS


def slug_for_ts(window_start_ts: int) -> str:
    return f"sol-updown-5m-{window_start_ts}"


def seconds_until_window_end(now: float | None = None) -> float:
    ts = now if now is not None else time.time()
    end = current_window_start_ts(ts) + WINDOW_SECONDS
    return max(0.0, end - ts)


def fetch_market(window_start_ts: int | None = None) -> Sol5mMarket:
    candidates: list[int] = []
    if window_start_ts is not None:
        candidates = [window_start_ts]
    else:
        now_ts = int(time.time())
        base = (now_ts // WINDOW_SECONDS) * WINDOW_SECONDS
        candidates = [base, base + WINDOW_SECONDS]  # current, then next window

    url = f"{GAMMA_API}/events"
    for start in candidates:
        slug = slug_for_ts(start)
        resp = _HTTP.get(url, params={"slug": slug}, timeout=30)
        events: list[dict[str, Any]] = resp.json()
        if events:
            break
    else:
        raise LookupError(f"No market found for slugs={[slug_for_ts(s) for s in candidates]}")

    event = events[0]
    markets = event.get("markets") or []
    if not markets:
        raise LookupError(f"Event has no markets: {slug}")

    market = markets[0]
    outcomes = market.get("outcomes") or []
    token_ids = market.get("clobTokenIds") or market.get("clob_token_ids") or []
    prices = market.get("outcomePrices") or market.get("outcome_prices") or []

    if isinstance(outcomes, str):
        import json

        outcomes = json.loads(outcomes)
    if isinstance(token_ids, str):
        import json

        token_ids = json.loads(token_ids)
    if isinstance(prices, str):
        import json

        prices = json.loads(prices)

    if len(outcomes) < 2 or len(token_ids) < 2:
        raise LookupError(f"Unexpected market shape for {slug}")

    tokens: dict[str, OutcomeToken] = {}
    for i, name in enumerate(outcomes):
        label = str(name).strip().lower()
        price = float(prices[i]) if i < len(prices) and prices[i] is not None else None
        tokens[label] = OutcomeToken(
            outcome=str(name),
            token_id=str(token_ids[i]),
            price=price,
        )

    up = tokens.get("up") or tokens.get("yes")
    down = tokens.get("down") or tokens.get("no")
    if not up or not down:
        raise LookupError(f"Could not resolve Up/Down tokens for {slug}: {outcomes}")

    title = event.get("title") or market.get("question") or slug
    return Sol5mMarket(
        slug=slug,
        event_id=str(event.get("id", "")),
        title=str(title),
        up=up,
        down=down,
        window_start_ts=start,
    )

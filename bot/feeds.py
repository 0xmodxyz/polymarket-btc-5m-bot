"""Real-time data feeds — RTDS (Chainlink SOL/USD), Binance WS, Coinbase WS, Gamma & CLOB."""

from __future__ import annotations

import asyncio
import json
import logging
import time
import aiohttp
import websockets

logger = logging.getLogger(__name__)

GAMMA_API = "https://gamma-api.polymarket.com"
BINANCE_WS = "wss://stream.binance.com:9443/ws"
RTDS_URL = "wss://ws-live-data.polymarket.com"
COINBASE_WS = "wss://advanced-trade-ws.coinbase.com"


class PriceFeed:
    def __init__(self):
        self.price: float = 0.0
        self.price_timestamp: float = 0.0
        self.price_source: str = "none"
        self.up_price: float = 0.5
        self.down_price: float = 0.5
        self.last_update: float = 0.0
        self._market_ended: bool = False
        self._price_history: list[tuple[float, float, str]] = []
        self._window_start_price: float = 0.0
        self.cvd_value: float = 0.0
        self.order_books: dict[str, dict] = {}
        self._up_history: list[tuple[float, float]] = []  # (ts, up_price)
        self._down_history: list[tuple[float, float]] = []  # (ts, down_price)

    @property
    def is_ready(self) -> bool:
        return self.price > 0

    def change_pct(self, window_s: float = 30.0) -> float:
        """% price change over last `window_s` seconds."""
        now = time.time()
        recent = [p for ts, p, s in self._price_history if now - ts <= window_s]
        if len(recent) < 2:
            return 0.0
        return ((recent[-1] - recent[0]) / recent[0]) * 100.0 if recent[0] > 0 else 0.0

    @property
    def outcome_trend_pct(self) -> float:
        """% change in Up token price over last 10s — Polymarket sentiment signal."""
        now = time.time()
        recent = [p for ts, p in self._up_history if now - ts <= 10.0]
        if len(recent) < 2:
            return 0.0
        return ((recent[-1] - recent[0]) / recent[0]) * 100.0 if recent[0] > 0 else 0.0

    def record_price(self, price: float, quantity: float = 0.0, is_buyer_maker: bool | None = None, source: str = "unknown") -> None:
        now = time.time()
        self.price = price
        self.price_timestamp = now
        self.price_source = source
        self._price_history.append((now, price, source))
        cutoff = now - 120.0
        self._price_history = [(ts, p, s) for ts, p, s in self._price_history if ts >= cutoff]

    def record_outcome_prices(self, up: float, down: float) -> None:
        now = time.time()
        self.up_price = up
        self.down_price = down
        self._up_history.append((now, up))
        self._down_history.append((now, down))
        cutoff = now - 15.0
        self._up_history = [(ts, p) for ts, p in self._up_history if ts >= cutoff]
        self._down_history = [(ts, p) for ts, p in self._down_history if ts >= cutoff]


class RtdsWebSocket:
    """Polymarket RTDS — Chainlink SOL/USD via websockets library."""

    def __init__(self, feed: PriceFeed):
        self.feed = feed

    async def start(self) -> None:
        while True:
            try:
                async with websockets.connect(RTDS_URL, ping_interval=20) as ws:
                    sub = {
                        "action": "subscribe",
                        "subscriptions": [{
                            "topic": "crypto_prices_chainlink",
                            "type": "*",
                            "filters": json.dumps({"symbol": "sol/usd"}),
                        }],
                    }
                    await ws.send(json.dumps(sub))
                    logger.info("RTDS subscribed: crypto_prices_chainlink sol/usd")

                    async def _ping():
                        try:
                            while True:
                                await ws.send("PING")
                                await asyncio.sleep(5)
                        except Exception:
                            pass

                    ping_task = asyncio.create_task(_ping())

                    async for msg in ws:
                        if msg == "PONG":
                            continue
                        try:
                            data = json.loads(msg)
                        except json.JSONDecodeError:
                            continue
                        payload = data.get("payload") if isinstance(data, dict) else None
                        if payload is None:
                            continue
                        values = payload.get("data")
                        if isinstance(values, list) and values:
                            last = values[-1]
                            v = last.get("value") if isinstance(last, dict) else None
                            if v is not None:
                                self.feed.record_price(price=float(v), source="rtds")

                    ping_task.cancel()
            except websockets.ConnectionClosed:
                logger.warning("RTDS connection closed — Reconnecting in 2s...")
                await asyncio.sleep(2)
            except Exception as exc:
                logger.warning("RTDS error (%s) — Reconnecting in 2s...", exc)
                await asyncio.sleep(2)


class CoinbaseWebSocket:
    """Coinbase Advanced Trade WS — SOL-USD ticker (fallback if RTDS silent)."""

    def __init__(self, feed: PriceFeed):
        self.feed = feed

    async def start(self) -> None:
        await asyncio.sleep(15)
        while True:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.ws_connect(COINBASE_WS, heartbeat=30) as ws:
                        sub = {
                            "type": "subscribe",
                            "product_ids": ["SOL-USD"],
                            "channel": "ticker",
                        }
                        await ws.send_json(sub)
                        logger.info("Coinbase WS subscribed: ticker SOL-USD")
                        async for msg in ws:
                            if msg.type == aiohttp.WSMsgType.TEXT:
                                data = json.loads(msg.data)
                                if data.get("channel") != "ticker":
                                    continue
                                for ev in data.get("events", []):
                                    for t in ev.get("tickers", []):
                                        if t.get("product_id") == "SOL-USD":
                                            self.feed.record_price(price=float(t["price"]), source="coinbase")
                            elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                                break
            except Exception as exc:
                logger.warning("Coinbase WS disconnected (%s) — Reconnecting in 2s...", exc)
                await asyncio.sleep(2)


class BinanceWebSocket:
    """Binance WS — SOL-USDT 1s ticker (best ask price for trend)."""

    def __init__(self, feed: PriceFeed):
        self.feed = feed

    async def start(self) -> None:
        url = f"{BINANCE_WS}/solusdt@ticker"
        while True:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.ws_connect(url, heartbeat=30) as ws:
                        logger.info("Binance WS connected successfully.")
                        async for msg in ws:
                            if msg.type == aiohttp.WSMsgType.TEXT:
                                data = json.loads(msg.data)
                                ask = float(data.get("a", 0))
                                if ask > 0:
                                    self.feed.record_price(price=ask, source="binance")
                            elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                                break
            except Exception as exc:
                logger.warning("Binance WS disconnected (%s) — Reconnecting in 2s...", exc)
                await asyncio.sleep(2)


class GammaPoller:
    def __init__(self, feed: PriceFeed, slug: str):
        self.feed = feed
        self.slug = slug

    async def start(self, poll_s: float = 0.15) -> None:
        url = f"{GAMMA_API}/events"
        params = {"slug": self.slug}
        async with aiohttp.ClientSession() as session:
            while True:
                try:
                    async with session.get(url, params=params, timeout=5) as r:
                        if r.status == 429:
                            await asyncio.sleep(1)
                            continue
                        events = await r.json()
                    if events and events[0].get("markets"):
                        market_data = events[0]["markets"][0]
                        raw = market_data.get("outcomePrices") or "[]"
                        if isinstance(raw, str):
                            raw = json.loads(raw)
                        if len(raw) >= 2:
                            up = float(raw[0])
                            down = float(raw[1])
                            self.feed.record_outcome_prices(up, down)
                            self.feed.last_update = time.time()
                except Exception:
                    pass
                await asyncio.sleep(poll_s)


class ClobBookPoller:
    def __init__(self, feed: PriceFeed, token_ids: list[str]):
        self.feed = feed
        self.token_ids = token_ids

    async def start(self, poll_s: float = 1.0) -> None:
        book_url = "https://clob.polymarket.com/book"
        mid_url = "https://clob.polymarket.com/midpoint"
        async with aiohttp.ClientSession() as session:
            while True:
                for tid in self.token_ids:
                    try:
                        async with session.get(book_url, params={"token_id": tid}, timeout=5) as r:
                            if r.status == 200:
                                self.feed.order_books[tid] = await r.json()
                    except Exception:
                        pass
                    try:
                        async with session.get(mid_url, params={"token_id": tid}, timeout=5) as r:
                            if r.status == 200:
                                data = await r.json()
                                mid = data.get("mid")
                                if mid is not None:
                                    if tid not in self.feed.order_books:
                                        self.feed.order_books[tid] = {}
                                    self.feed.order_books[tid]["midpoint"] = mid
                    except Exception:
                        pass
                await asyncio.sleep(poll_s)

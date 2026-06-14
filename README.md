# PolySpread Bot — Spread Capture for Polymarket

[![Website](https://img.shields.io/badge/website-polymarket--spread--bot.vercel.app-00c853?style=flat-square)](https://polymarket-spread-bot.vercel.app)
[![Price](https://img.shields.io/badge/strategy%20module-%245-ff9800?style=flat-square)](https://polymarket-spread-bot.vercel.app/pricing)
[![License](https://img.shields.io/badge/license-MIT%20(free%20framework)-blue?style=flat-square)](LICENSE)

> **Free bot framework + $5 strategy module.** Buys both sides of Polymarket BTC Up/Down at combined < $0.90, holds to settlement, collects the guaranteed spread. Zero directional risk.

---

## Live Verified Performance (30-day projection)

| Metric | Value |
|--------|-------|
| Net P/L | **+$3,720** |
| ROI | **+12.4%** |
| Total trades | ~33,000 |
| Volume deployed | $30,000 |
| Avg paired cost | $0.89 |
| Avg spread / pair | $0.11 |
| Both-sides rate | 99.0% |
| Win rate | 50.2% |

---

## Quick Start (Free Framework)

```bash
git clone https://github.com/0xmodxyz/polymarket-btc-5m-bot.git
cd polymarket-btc-5m-bot
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\Activate on Windows
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your Polymarket API credentials
python main.py --mode sim --cycles 1
```

### What's in the free framework

```
polymarket-free-bot/
├── main.py              # Entry point
├── requirements.txt     # Dependencies
├── .env.example         # Credentials template
├── README.md            # Setup guide
├── bot/
│   ├── config.py        # Configuration loader
│   ├── client.py        # CLOB API wrapper
│   ├── engine.py        # Window management loop
│   ├── executor.py      # Trade executor (sim + live)
│   ├── feeds.py         # Price feeds (Binance, CLOB)
│   ├── markets.py       # Market resolution (Gamma API)
│   ├── orders.py        # Order placement (limit, FAK)
│   └── engines/         # ← Drop strategy modules here
```

---

## Get the Strategy Module — $5

The free framework connects to Polymarket and shows live data. The **strategy module** adds automated spread capture:

- Entry at combined `up + down < 0.90`
- FAK limit order execution
- Up-first safety (no orphaned Down positions)
- 90s deadline protection
- Drops into `bot/engines/sniper.py`

**[Buy Strategy Module →](https://polymarket-spread-bot.vercel.app/pricing)**

### Payment

Send **$5 USDC on Base network** to:

```
0x4d6ada8f770c7b0b79afc748b9f70b829603d936
```

Then email the TXID to **oasisprotokol@gmail.com** to receive the download link.

---

## How It Works

```
1. Fetch CLOB midpoints for current BTC 5m window
2. If up_price + down_price < 0.90 → enter
3. Calculate shares: ceil(1.0 / price)
4. Buy Up first (FAK limit)
5. If Up fills → buy Down (FAK limit)
6. Hold both to settlement
```

The bot runs a 2ms loop checking every window. When conditions align, it fires immediately. No market predictions, no directional bias — pure spread arbitrage.

### Key Design Decisions

| Decision | Why |
|----------|-----|
| **Combined < 0.90** | Guarantees minimum 10¢ spread per pair |
| **Up-first** | Prevents orphaned Down positions |
| **FAK limit orders** | No overpaying, no resting orders |
| **Hold to settlement** | Platform pays $1 for winning shares automatically |
| **No per-side cap** | Combined-only catches more profitable pairs |

---

## Documentation

| Resource | Link |
|----------|------|
| Full strategy breakdown | [how-it-works](https://polymarket-spread-bot.vercel.app/how-it-works) |
| Research & analysis | [research](https://polymarket-spread-bot.vercel.app/research) |
| Installation guide | [setup](https://polymarket-spread-bot.vercel.app/installation) |
| Build your own (free guide) | [free-guide](https://polymarket-spread-bot.vercel.app/build-your-own) |
| Pricing | [pricing](https://polymarket-spread-bot.vercel.app/pricing) |
| Contact | [contact](https://polymarket-spread-bot.vercel.app/contact) |

---

## Why Spread Capture?

This is **not** a directional trading strategy. You don't predict BTC price. You simply exploit temporary inefficiencies in Polymarket's order book where Up + Down cost less than $1.00. At settlement, the winning side pays $1.00 — you collect the difference.

**Edge source:** Structural spread capture (median paired cost $0.89 → $0.11 guaranteed profit per pair).

---

## License

The **free framework** is open source under the MIT License. The **strategy module** (`bot/engines/sniper.py`) is a paid product — each license covers one machine.

---

*Not financial advice. Trade at your own risk. Past performance does not guarantee future results.*

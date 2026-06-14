# PolySpread Bot — The Bot Behind JetFadil

[![Website](https://img.shields.io/badge/website-polyspread.tech-00c853?style=flat-square)](https://polyspread.tech)
[![Price](https://img.shields.io/badge/strategy%20module-%245-ff9800?style=flat-square)](https://polyspread.tech/pricing)
[![Report](https://img.shields.io/badge/research-JetFadil%20analysis-4fc3f7?style=flat-square)](https://polyspread.tech/research)

> **Free bot framework + $5 strategy module.** The same software powering the JetFadil wallet — 234,596 trades, +$43,577 net P&L in 26 days.

---

## Live On-Chain Performance — JetFadil Wallet

| Metric | Value |
|--------|-------|
| Net P&L (26 days) | **+$43,577** |
| Total trades | 234,596 (0 SELLs) |
| Volume deployed | $2,476,758 |
| Both-sides rate | 97.3% |
| Median clip size | $10.55 |
| Win rate | 56.3% |
| Median inter-trade gap | 4 seconds |
| Operation | 24/7 continuous |
| LP rewards earned | +$58,597 |

[View full research report →](https://polyspread.tech/research)

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

The free framework connects to Polymarket. The **strategy module** adds the full JetFadil liquidity-farming engine:

- Posts both sides of every BTC 5m window — 24/7
- Fixed $10.55 clip sizing — no conviction errors
- LP rewards optimization — earns Polymarket liquidity mining rewards
- High-conviction dominance filter — flips trading P&L to +$40,727 (+4.35% ROI)
- Drops into `bot/engines/sniper.py`

**[Buy Strategy Module →](https://polyspread.tech/pricing)**

### Payment

Send **$5 USDC on Base network** to:

```
0x4d6ada8f770c7b0b79afc748b9f70b829603d936
```

Then email the TXID to **oasisprotokol@gmail.com** to receive the download link.

---

## How It Works

```
1. Scan all open BTC 5m Up/Down windows
2. Check both-sides liquidity availability
3. Post fixed clip (~$10) on first available side
4. Post opposing side within 21s median lag
5. Repeat until window close or budget exhausted
6. Hold all positions to settlement — 0 SELLs
```

The bot runs 24/7 with a 4s median inter-trade gap. It posts into every available BTC 5-minute market on Polymarket, cycling ~$95K of capital per day. The trading book loses -$15,020 (structural spread cost), but LP rewards of +$58,597 flip the net to +$43,577.

The **high-conviction mode** (dominance ≥2x) isolates 66,833 trades that win 97.6% of the time and generate +$40,727 trading P&L independently (+4.35% ROI).

---

## Documentation

| Resource | Link |
|----------|------|
| Full JetFadil analysis | [research](https://polyspread.tech/research) |
| Strategy breakdown | [how-it-works](https://polyspread.tech/how-it-works) |
| Installation guide | [setup](https://polyspread.tech/installation) |
| Build your own (free guide) | [free-guide](https://polyspread.tech/build-your-own) |
| Pricing | [pricing](https://polyspread.tech/pricing) |
| Wallet on Polymarket | [JetFadil](https://polymarket.com/@jetfadil) |

---

## Why This Strategy?

This is **liquidity farming** — not directional trading. The bot posts both sides of every BTC 5-minute market at fixed clip sizes, absorbs a small structural loss on the spread, and earns Polymarket LP rewards that far exceed the trading loss.

**The math:** Trading P&L -$15,020 + LP rewards +$58,597 = **+$43,577 net profit** in 26 days.

This only works at scale and with 24/7 uptime. The strategy module handles both.

---

## License

The **free framework** is open source under the MIT License. The **strategy module** (`bot/engines/sniper.py`) is a paid product — each license covers one machine.

---

*Not financial advice. Trade at your own risk. Past performance does not guarantee future results. On-chain data from Polymarket wallet 0xe0229e...6603 (JetFadil), analyzed by PolySpread Research.*

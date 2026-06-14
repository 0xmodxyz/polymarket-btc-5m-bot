#!/usr/bin/env python3
"""SOL 5m Polymarket HFT bot — Async Execution Launcher."""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv()

from bot.config import load_settings
from bot.engine import Engine
from bot.markets import seconds_until_window_end

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("main")


def parse_args():
    import argparse
    p = argparse.ArgumentParser(description="SOL 5m Sniper Bot")
    p.add_argument("--mode", choices=["simulate", "live"], default="simulate")
    p.add_argument("--cycles", type=int, default=5, help="Number of 5-min windows")
    p.add_argument("--budget", type=float, default=50.0, help="Max budget USD")
    p.add_argument("--yes", action="store_true", help="Skip confirmation flag")
    return p.parse_args()


async def wait_for_next_window(engine: Engine) -> None:
    secs = seconds_until_window_end()
    logger.info("Next window ends in %.0fs...", secs)
    if secs > 10:
        # Window already active — run immediately, don't skip it
        return
    if secs > 1:
        await asyncio.sleep(secs + 5)
    await engine.prewarm()
    await asyncio.sleep(5)


async def main() -> int:
    args = parse_args()
    load_settings()

    if args.mode == "live" and not args.yes:
        c = input("LIVE MODE — Deploy? (yes/no): ")
        if c.strip().lower() != "yes":
            logger.info("Aborted.")
            return 1

    logger.info("=" * 55)
    logger.info("JETFADIL SNIPER DEPLOYED — MODE: %s", args.mode.upper())
    logger.info("Budget: $%.0f | Windows: %d", args.budget, args.cycles)
    logger.info("=" * 55)

    engine = Engine(simulation=(args.mode == "simulate"), budget=args.budget)

    # Prewarm feeds before first window — saves ~5s connect time
    await engine.prewarm()
    await asyncio.sleep(3)

    try:
        for cycle in range(args.cycles):
            print("")
            logger.info("CYCLE [%d/%d]", cycle + 1, args.cycles)
            await engine.run_window()
            if cycle < args.cycles - 1:
                await wait_for_next_window(engine)
    except KeyboardInterrupt:
        logger.info("Interrupted by operator.")
    except Exception:
        logger.exception("Critical engine exception")

    print("")
    print(engine.final_summary())
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except KeyboardInterrupt:
        pass

"""
worker.py – Telegram bot + periodic scrape checker.

Uses asyncio.sleep for scheduling instead of the `schedule` library,
which cannot run inside an already-running event loop.

Run:
    python worker.py          # starts bot + 5-minute checker
    python worker.py --once   # single check, no bot
"""

import argparse
import asyncio
import logging

from db import init_db, upsert_internships, count_internships
from scraper import fetch_if_changed

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

CHECK_INTERVAL_SECONDS = 5 * 60  # 5 minutes


async def run_check(app=None):
    logger.info("=== Starting check ===")

    rows = fetch_if_changed()

    if rows is None:
        logger.info("=== No changes (304 Not Modified), skipping ===\n")
        return

    if not rows:
        logger.warning("=== Fetch returned no rows, skipping ===\n")
        return

    new_entries = upsert_internships(rows)
    total       = count_internships()

    if new_entries:
        logger.info("🆕  %d new internship(s) found!", len(new_entries))
        for e in new_entries:
            logger.info("  + [%s] %s @ %s", e["company"], e["role"], e["location"])
        if app:
            from bot import broadcast_new
            await broadcast_new(app, new_entries)
    else:
        logger.info("File changed but no new internships (edits/removals only).")

    logger.info("DB now contains %d internships total.", total)
    logger.info("=== Check complete ===\n")


async def periodic_checker(app=None):
    """Runs run_check every CHECK_INTERVAL_SECONDS forever."""
    while True:
        await asyncio.sleep(CHECK_INTERVAL_SECONDS)
        await run_check(app)


async def main():
    parser = argparse.ArgumentParser(description="Internship tracker worker")
    parser.add_argument("--once", action="store_true", help="Single check, no bot")
    args = parser.parse_args()

    init_db()

    if args.once:
        await run_check()
        return

    from bot import build_app
    app = build_app()

    # Run first check immediately on startup
    await run_check(app)

    logger.info(
        "Scheduler ready — checking every %d minute(s). Starting bot…",
        CHECK_INTERVAL_SECONDS // 60,
    )

    async with app:
        await app.start()
        await app.updater.start_polling(drop_pending_updates=True)

        try:
            await periodic_checker(app)   # runs forever, yields to event loop between sleeps
        except (KeyboardInterrupt, asyncio.CancelledError):
            logger.info("Shutting down…")
        finally:
            await app.updater.stop()
            await app.stop()


if __name__ == "__main__":
    asyncio.run(main())
"""
worker.py – 5-minute scheduler integrated with the Telegram bot.

Uses ETag-based conditional requests so the table is only parsed when
the GitHub file actually changes — safe to run every 5 minutes.

Run:
    python worker.py          # starts bot + scheduler together
    python worker.py --once   # single check then exit (no bot, good for cron)
"""

import argparse
import asyncio
import logging

import schedule

from db import init_db, upsert_internships, count_internships
from scraper import fetch_if_changed

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

CHECK_INTERVAL_MINUTES = 5


async def run_check(app=None):
    logger.info("=== Starting check ===")

    rows = fetch_if_changed()

    if rows is None:
        # 304 Not Modified — nothing to do
        logger.info("=== No changes, skipping DB update ===\n")
        return

    if not rows:
        # Network error or empty parse
        logger.warning("=== Fetch returned no rows, skipping DB update ===\n")
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


def run_check_sync(app=None):
    """Sync wrapper so the `schedule` library can call the async function."""
    loop = asyncio.get_event_loop()
    loop.run_until_complete(run_check(app))


async def main():
    parser = argparse.ArgumentParser(description="Internship tracker worker")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single check and exit (no bot polling)",
    )
    args = parser.parse_args()

    init_db()

    if args.once:
        await run_check()
        return

    from bot import build_app
    app = build_app()

    # Always do one check immediately on startup
    await run_check(app)

    # Schedule subsequent checks every 5 minutes
    schedule.every(CHECK_INTERVAL_MINUTES).minutes.do(run_check_sync, app=app)
    logger.info(
        "Scheduler ready — checking every %d minute(s). Starting bot…",
        CHECK_INTERVAL_MINUTES,
    )

    async with app:
        await app.start()
        await app.updater.start_polling(drop_pending_updates=True)

        try:
            while True:
                schedule.run_pending()
                await asyncio.sleep(15)   # tight enough not to miss a 5-min slot
        except (KeyboardInterrupt, asyncio.CancelledError):
            logger.info("Shutting down…")
        finally:
            await app.updater.stop()
            await app.stop()


if __name__ == "__main__":
    asyncio.run(main())
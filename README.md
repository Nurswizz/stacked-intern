# Internship Tracker + Telegram Bot

Scrapes the [SimplifyJobs Summer 2026 Internships](https://github.com/SimplifyJobs/Summer2026-Internships) list every hour, stores new entries in SQLite, and broadcasts alerts to subscribed Telegram users.

## Setup

```bash
pip install -r requirements.txt
```

Create a `.env` file (or export the variable directly):

```bash
export TELEGRAM_BOT_TOKEN=your_token_here
```

> Get a token from [@BotFather](https://t.me/BotFather) on Telegram.

## Usage

```bash
# Start bot + hourly worker together
python worker.py

# Single scrape check only (no bot, good for cron)
python worker.py --once
```

## Bot Commands

| Command | Description |
|---------|-------------|
| `/start` | Subscribe to new listing alerts |
| `/stop` | Unsubscribe |
| `/list` | Show 10 most recent internships |
| `/search <keyword>` | Search by role or company name |
| `/filter <keyword>` | Only receive alerts matching a keyword |
| `/filter off` | Remove keyword filter |
| `/status` | Show your subscription settings |

## Files

| File | Purpose |
|------|---------|
| `worker.py` | Entry point — runs bot + hourly scheduler |
| `bot.py` | Telegram bot handlers + broadcast logic |
| `scraper.py` | Fetches & parses the GitHub README table |
| `db.py` | SQLite helpers — internships + subscribers |
| `internships.db` | Auto-created SQLite database |
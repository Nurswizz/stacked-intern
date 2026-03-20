"""
bot.py – Telegram bot for internship notifications with inline buttons.
"""

import logging
import os

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from dotenv import load_dotenv

load_dotenv()

from db import (
    init_db,
    subscribe_user,
    unsubscribe_user,
    set_user_filter,
    get_subscribers,
    get_recent,
    search_internships,
    count_internships,
    get_user,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]

# free-text input states stored in user_data
WAITING_SEARCH = 1
WAITING_FILTER = 2


# ── keyboards ─────────────────────────────────────────────────────────────────

def main_menu_keyboard(subscribed: bool) -> InlineKeyboardMarkup:
    sub_btn = (
        InlineKeyboardButton("🔕 Unsubscribe", callback_data="action:stop")
        if subscribed else
        InlineKeyboardButton("🔔 Subscribe",   callback_data="action:start")
    )
    return InlineKeyboardMarkup([
        [sub_btn],
        [
            InlineKeyboardButton("📋 Recent listings", callback_data="action:list"),
            InlineKeyboardButton("🔍 Search",          callback_data="action:search"),
        ],
        [
            InlineKeyboardButton("🔑 Set filter",   callback_data="action:filter"),
            InlineKeyboardButton("❌ Clear filter",  callback_data="action:filter_off"),
        ],
        [InlineKeyboardButton("📊 My status", callback_data="action:status")],
    ])


def back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("« Back to menu", callback_data="action:menu")]
    ])


# ── formatting ────────────────────────────────────────────────────────────────

def _fmt(entry: dict, index: int | None = None) -> str:
    prefix   = f"{index}. " if index is not None else "• "
    company  = entry["company"]       or "?"
    role     = entry["role"]          or "?"
    location = entry["location"]      or "?"
    apply    = entry["apply_link"]    or ""
    simplify = entry["simplify_link"] or ""

    links = []
    if apply:
        links.append(f"[Apply]({apply})")
    if simplify:
        links.append(f"[Simplify]({simplify})")
    link_str = "  ·  ".join(links)

    return (
        f"{prefix}*{company}* — {role}\n"
        f"📍 {location}\n"
        + (f"{link_str}\n" if link_str else "")
    )


def _fmt_new_alert(entries: list[dict]) -> str:
    header = f"🆕 *{len(entries)} new internship{'s' if len(entries) > 1 else ''}!*\n\n"
    body   = "\n".join(_fmt(e, i + 1) for i, e in enumerate(entries))
    return header + body


def _welcome_text(name: str, subscribed: bool, total: int) -> str:
    status = "🟢 Subscribed" if subscribed else "🔴 Not subscribed"
    return (
        f"👋 Hey *{name}*!\n\n"
        f"Status: {status}\n"
        f"📦 Listings in DB: *{total}*\n\n"
        "What would you like to do?"
    )


# ── /start & /menu ────────────────────────────────────────────────────────────

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid  = update.effective_user.id
    name = update.effective_user.first_name or "there"
    subscribe_user(uid)
    user = get_user(uid)
    await update.message.reply_text(
        _welcome_text(name, bool(user and user["active"]), count_internships()),
        parse_mode="Markdown",
        reply_markup=main_menu_keyboard(subscribed=True),
    )


async def cmd_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid  = update.effective_user.id
    name = update.effective_user.first_name or "there"
    user = get_user(uid)
    subscribed = bool(user and user["active"])
    await update.message.reply_text(
        _welcome_text(name, subscribed, count_internships()),
        parse_mode="Markdown",
        reply_markup=main_menu_keyboard(subscribed=subscribed),
    )


# ── callback router ───────────────────────────────────────────────────────────

async def on_button(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query  = update.callback_query
    await query.answer()
    action = query.data.split(":", 1)[1]
    uid    = query.from_user.id
    name   = query.from_user.first_name or "there"

    if action == "start":
        subscribe_user(uid)
        await query.edit_message_text(
            _welcome_text(name, True, count_internships()),
            parse_mode="Markdown",
            reply_markup=main_menu_keyboard(subscribed=True),
        )

    elif action == "stop":
        unsubscribe_user(uid)
        await query.edit_message_text(
            "🔕 Unsubscribed. You won't receive any more alerts.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔔 Re-subscribe", callback_data="action:start")
            ]]),
        )

    elif action == "list":
        rows = get_recent(limit=10)
        if not rows:
            text = "No internships in the database yet."
        else:
            text = "📋 *Last 10 internships:*\n\n" + "\n".join(
                _fmt(r, i + 1) for i, r in enumerate(rows)
            )
        await query.edit_message_text(
            text, parse_mode="Markdown",
            disable_web_page_preview=True,
            reply_markup=back_keyboard(),
        )

    elif action == "search":
        ctx.user_data["state"] = WAITING_SEARCH
        await query.edit_message_text(
            "🔍 Send me a keyword to search (role or company name):",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("« Cancel", callback_data="action:menu")
            ]]),
        )

    elif action == "filter":
        user = get_user(uid)
        current = user["keyword_filter"] if user else None
        current_str = f"\n\nCurrent filter: *{current}*" if current else ""
        ctx.user_data["state"] = WAITING_FILTER
        await query.edit_message_text(
            f"🔑 Send a keyword to filter alerts (role or company).{current_str}",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("« Cancel", callback_data="action:menu")
            ]]),
        )

    elif action == "filter_off":
        set_user_filter(uid, None)
        await query.edit_message_text(
            "✅ Filter cleared. You'll receive all new listings.",
            reply_markup=back_keyboard(),
        )

    elif action == "status":
        user = get_user(uid)
        if not user:
            text = "You're not subscribed. Press Subscribe to start."
        else:
            sub  = "🟢 Subscribed" if user["active"] else "🔴 Not subscribed"
            kw   = user["keyword_filter"]
            filt = f"*{kw}*" if kw else "none (all listings)"
            text = f"{sub}\n🔑 Filter: {filt}\n📦 DB total: *{count_internships()}*"
        await query.edit_message_text(
            text, parse_mode="Markdown",
            reply_markup=back_keyboard(),
        )

    elif action == "menu":
        ctx.user_data.pop("state", None)
        user = get_user(uid)
        subscribed = bool(user and user["active"])
        await query.edit_message_text(
            _welcome_text(name, subscribed, count_internships()),
            parse_mode="Markdown",
            reply_markup=main_menu_keyboard(subscribed=subscribed),
        )


# ── free-text handler (receives search/filter keywords) ──────────────────────

async def on_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    state = ctx.user_data.get("state")
    uid   = update.effective_user.id

    if state == WAITING_SEARCH:
        kw   = update.message.text.strip()
        rows = search_internships(kw, limit=10)
        text = (
            f"🔍 *Results for \"{kw}\":*\n\n" + "\n".join(_fmt(r, i + 1) for i, r in enumerate(rows))
            if rows else f"No results for *{kw}*."
        )
        ctx.user_data.pop("state", None)
        await update.message.reply_text(
            text, parse_mode="Markdown",
            disable_web_page_preview=True,
            reply_markup=back_keyboard(),
        )

    elif state == WAITING_FILTER:
        kw = update.message.text.strip()
        set_user_filter(uid, kw)
        ctx.user_data.pop("state", None)
        await update.message.reply_text(
            f"✅ Filter set to *{kw}*. You'll only receive matching alerts.",
            parse_mode="Markdown",
            reply_markup=back_keyboard(),
        )


# ── broadcast (called from worker) ───────────────────────────────────────────

async def broadcast_new(app: Application, new_entries: list[dict]):
    """Fan out new listings to all active subscribers respecting their filters."""
    subscribers = get_subscribers()
    for user in subscribers:
        kw = user["keyword_filter"]
        matches = (
            [e for e in new_entries
             if kw.lower() in (e["company"] or "").lower()
             or kw.lower() in (e["role"] or "").lower()]
            if kw else new_entries
        )
        if not matches:
            continue
        try:
            await app.bot.send_message(
                chat_id=user["chat_id"],
                text=_fmt_new_alert(matches),
                parse_mode="Markdown",
                disable_web_page_preview=True,
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("📋 Browse all", callback_data="action:list"),
                    InlineKeyboardButton("📊 Status",     callback_data="action:status"),
                ]]),
            )
        except Exception as exc:
            logger.warning("Failed to send to %s: %s", user["chat_id"], exc)


# ── app factory ───────────────────────────────────────────────────────────────

def build_app() -> Application:
    init_db()
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("menu",  cmd_menu))
    app.add_handler(CallbackQueryHandler(on_button, pattern=r"^action:"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    return app


if __name__ == "__main__":
    build_app().run_polling()
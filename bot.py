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
    list_internships,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

TOKEN    = os.environ["TELEGRAM_BOT_TOKEN"]
ADMIN_ID = int(os.environ.get("ADMIN_ID", 0))

WAITING_SEARCH = 1
WAITING_FILTER = 2

PAGE_SIZE = 10

MAINTENANCE = {"on": os.environ.get("MAINTENANCE_MODE", "0") == "1"}
MAINTENANCE_TEXT = (
    "🔧 *Technical works in progress.*\n\n"
    "The bot is temporarily unavailable. Please try again later."
)


def is_maintenance(uid: int) -> bool:
    return MAINTENANCE["on"] and uid != ADMIN_ID


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
            InlineKeyboardButton("📋 Recent listings", callback_data="action:list:0"),
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


def search_result_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("« Back to menu", callback_data="action:menu")],
    ])


def filter_result_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔑 Change filter", callback_data="action:filter")],
        [InlineKeyboardButton("❌ Clear filter",   callback_data="action:filter_off")],
        [InlineKeyboardButton("« Back to menu",   callback_data="action:menu")],
    ])


def pagination_keyboard(
    page: int,
    total: int,
    action_prefix: str,   # e.g. "list" or "search:python"
) -> InlineKeyboardMarkup:
    """Build prev/next pagination row + back button."""
    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(
            "« Prev", callback_data=f"action:{action_prefix}:{page - 1}"
        ))
    nav.append(InlineKeyboardButton(
        f"{page + 1}/{total_pages}", callback_data="action:noop"
    ))
    if (page + 1) * PAGE_SIZE < total:
        nav.append(InlineKeyboardButton(
            "Next »", callback_data=f"action:{action_prefix}:{page + 1}"
        ))
    return InlineKeyboardMarkup([
        nav,
        [InlineKeyboardButton("« Back to menu", callback_data="action:menu")],
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


def _page_text(rows: list[dict], page: int, total: int, title: str) -> str:
    start = page * PAGE_SIZE + 1
    header = f"{title} _(showing {start}–{min(start + PAGE_SIZE - 1, total)} of {total})_\n\n"
    body   = "\n".join(_fmt(r, start + i) for i, r in enumerate(rows))
    return header + body


# ── /maintenance (admin only) ─────────────────────────────────────────────────

async def cmd_maintenance(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid != ADMIN_ID:
        await update.message.reply_text("⛔ Admin only.")
        return

    arg = (ctx.args[0].lower() if ctx.args else "")
    if arg == "on":
        MAINTENANCE["on"] = True
        await update.message.reply_text("🔧 Maintenance mode ON.")
    elif arg == "off":
        MAINTENANCE["on"] = False
        await update.message.reply_text("✅ Maintenance mode OFF.")
    else:
        status = "ON 🔧" if MAINTENANCE["on"] else "OFF ✅"
        await update.message.reply_text(
            f"Maintenance is currently *{status}*\n\n"
            "Usage:\n`/maintenance on`\n`/maintenance off`",
            parse_mode="Markdown",
        )


# ── /start & /menu ────────────────────────────────────────────────────────────

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid  = update.effective_user.id
    name = update.effective_user.first_name or "there"
    if is_maintenance(uid):
        await update.message.reply_text(MAINTENANCE_TEXT, parse_mode="Markdown")
        return
    subscribe_user(uid)
    user = get_user(uid)
    ctx.user_data.pop("state", None)
    await update.message.reply_text(
        _welcome_text(name, bool(user and user["active"]), count_internships()),
        parse_mode="Markdown",
        reply_markup=main_menu_keyboard(subscribed=True),
    )


async def cmd_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid  = update.effective_user.id
    name = update.effective_user.first_name or "there"
    if is_maintenance(uid):
        await update.message.reply_text(MAINTENANCE_TEXT, parse_mode="Markdown")
        return
    user = get_user(uid)
    ctx.user_data.pop("state", None)
    await update.message.reply_text(
        _welcome_text(name, bool(user and user["active"]), count_internships()),
        parse_mode="Markdown",
        reply_markup=main_menu_keyboard(subscribed=bool(user and user["active"])),
    )


# ── helpers ───────────────────────────────────────────────────────────────────

async def _show_list_page(query, page: int):
    """Render a page of recent listings."""
    rows, total = list_internships(limit=PAGE_SIZE, offset=page * PAGE_SIZE)
    if not rows:
        await query.edit_message_text(
            "No internships in the database yet.",
            reply_markup=back_keyboard(),
        )
        return
    await query.edit_message_text(
        _page_text(rows, page, total, "📋 *Recent listings*"),
        parse_mode="Markdown",
        disable_web_page_preview=True,
        reply_markup=pagination_keyboard(page, total, "list"),
    )


async def _show_search_page(query, keyword: str, page: int):
    """Render a page of search results."""
    rows, total = list_internships(search=keyword, limit=PAGE_SIZE, offset=page * PAGE_SIZE)
    if not rows:
        await query.edit_message_text(
            f"No results for *{keyword}*.",
            parse_mode="Markdown",
            reply_markup=back_keyboard(),
        )
        return
    await query.edit_message_text(
        _page_text(rows, page, total, f"🔍 *Results for \"{keyword}\"*"),
        parse_mode="Markdown",
        disable_web_page_preview=True,
        reply_markup=pagination_keyboard(page, total, f"search:{keyword}"),
    )


# ── callback router ───────────────────────────────────────────────────────────

async def on_button(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query  = update.callback_query
    await query.answer()
    uid    = query.from_user.id
    name   = query.from_user.first_name or "there"

    if is_maintenance(uid):
        await query.edit_message_text(MAINTENANCE_TEXT, parse_mode="Markdown")
        return

    # callback_data format: "action:<action>[:<arg>][:<page>]"
    parts  = query.data.split(":", 2)
    action = parts[1]
    rest   = parts[2] if len(parts) > 2 else ""

    if action == "noop":
        return

    elif action == "start":
        subscribe_user(uid)
        ctx.user_data.pop("state", None)
        await query.edit_message_text(
            _welcome_text(name, True, count_internships()),
            parse_mode="Markdown",
            reply_markup=main_menu_keyboard(subscribed=True),
        )

    elif action == "stop":
        unsubscribe_user(uid)
        ctx.user_data.pop("state", None)
        await query.edit_message_text(
            "🔕 Unsubscribed. You won't receive any more alerts.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔔 Re-subscribe", callback_data="action:start")
            ]]),
        )

    elif action == "list":
        ctx.user_data.pop("state", None)
        page = int(rest) if rest.isdigit() else 0
        await _show_list_page(query, page)

    elif action == "search":
        # rest is either empty (initial prompt) or "keyword:page"
        if not rest:
            # Prompt user to type keyword
            ctx.user_data["state"] = WAITING_SEARCH
            await query.edit_message_text(
                "🔍 Send me a keyword to search (role or company name):",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("« Cancel", callback_data="action:menu")
                ]]),
            )
        else:
            # rest = "keyword:page" or just "keyword" (page 0)
            if ":" in rest:
                kw, pg = rest.rsplit(":", 1)
                page = int(pg) if pg.isdigit() else 0
            else:
                kw, page = rest, 0
            await _show_search_page(query, kw, page)

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
        ctx.user_data.pop("state", None)
        await query.edit_message_text(
            "✅ Filter cleared. You'll receive all new listings.",
            reply_markup=filter_result_keyboard(),
        )

    elif action == "status":
        ctx.user_data.pop("state", None)
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


# ── free-text handler ─────────────────────────────────────────────────────────

async def on_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid   = update.effective_user.id
    state = ctx.user_data.get("state")

    if is_maintenance(uid):
        await update.message.reply_text(MAINTENANCE_TEXT, parse_mode="Markdown")
        return

    if state == WAITING_SEARCH:
        kw = update.message.text.strip()
        rows, total = list_internships(search=kw, limit=PAGE_SIZE, offset=0)
        if not rows:
            text = f"No results for *{kw}*."
            await update.message.reply_text(
                text, parse_mode="Markdown",
                reply_markup=search_result_keyboard(),
            )
        else:
            await update.message.reply_text(
                _page_text(rows, 0, total, f"🔍 *Results for \"{kw}\"*"),
                parse_mode="Markdown",
                disable_web_page_preview=True,
                reply_markup=pagination_keyboard(0, total, f"search:{kw}"),
            )
        # Stay in search state for next query

    elif state == WAITING_FILTER:
        kw = update.message.text.strip()
        set_user_filter(uid, kw)
        ctx.user_data.pop("state", None)
        await update.message.reply_text(
            f"✅ Filter set to *{kw}*. You'll only receive matching alerts.",
            parse_mode="Markdown",
            reply_markup=filter_result_keyboard(),
        )

    else:
        await update.message.reply_text(
            "Use /menu to open the main menu.",
            reply_markup=back_keyboard(),
        )


# ── broadcast (called from worker) ───────────────────────────────────────────

async def broadcast_new(app: Application, new_entries: list[dict]):
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
                    InlineKeyboardButton("📋 Browse all", callback_data="action:list:0"),
                    InlineKeyboardButton("📊 Status",     callback_data="action:status"),
                ]]),
            )
        except Exception as exc:
            logger.warning("Failed to send to %s: %s", user["chat_id"], exc)


# ── app factory ───────────────────────────────────────────────────────────────

def build_app() -> Application:
    init_db()
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start",       cmd_start))
    app.add_handler(CommandHandler("menu",        cmd_menu))
    app.add_handler(CommandHandler("maintenance", cmd_maintenance))
    app.add_handler(CallbackQueryHandler(on_button, pattern=r"^action:"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    return app


if __name__ == "__main__":
    build_app().run_polling()
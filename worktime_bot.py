#!/usr/bin/env python3
"""
Work Duration Calculator Telegram Bot
Calculate working hours from clock-in, clock-out, and break time.

Setup:
  pip install python-telegram-bot

Run:
  BOT_TOKEN=<your_token> python work_duration_bot.py
  OR set BOT_TOKEN in the script below.
"""

import os
import re
import logging
from datetime import datetime, timedelta
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

# ── Config ────────────────────────────────────────────────────────────────────
BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN environment variable is not set.")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Conversation states
CLOCK_IN, CLOCK_OUT, BREAK_TIME = range(3)

# Accepted time formats
TIME_FORMATS = ["%H:%M", "%H.%M", "%I:%M %p", "%I:%M%p", "%I%p"]

CANCEL_KEYBOARD = ReplyKeyboardMarkup([["❌ Cancel"]], resize_keyboard=True)


# ── Helpers ───────────────────────────────────────────────────────────────────

def parse_time(text: str) -> datetime | None:
    """Try parsing a time string with multiple formats."""
    text = text.strip()
    for fmt in TIME_FORMATS:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def parse_break(text: str) -> int | None:
    """
    Parse break duration. Accepts:
      - Plain number: minutes  (e.g. "30")
      - "Xh Ym" or "Xh"       (e.g. "1h 15m", "1h")
      - "Xm"                  (e.g. "45m")
      - "0" or "no" / "none"  (no break)
    Returns total minutes or None on failure.
    """
    text = text.strip().lower()
    if text in ("0", "no", "none", "-"):
        return 0

    # e.g. "1h 30m", "1h", "30m"
    hm = re.fullmatch(r"(?:(\d+)h\s*)?(?:(\d+)m)?", text)
    if hm and (hm.group(1) or hm.group(2)):
        h = int(hm.group(1) or 0)
        m = int(hm.group(2) or 0)
        return h * 60 + m

    # plain integer → minutes
    if text.isdigit():
        return int(text)

    return None


def format_duration(total_minutes: float) -> str:
    """Return a human-friendly duration string."""
    total_minutes = int(total_minutes)
    h, m = divmod(abs(total_minutes), 60)
    sign = "-" if total_minutes < 0 else ""
    if h and m:
        return f"{sign}{h}h {m}m"
    if h:
        return f"{sign}{h}h"
    return f"{sign}{m}m"


def decimal_hours(minutes: float) -> str:
    """Return minutes as decimal hours, e.g. 8h 15m → 8.25 h."""
    return f"{minutes / 60:.2f} h"


def build_summary(clock_in: datetime, clock_out: datetime, break_min: int) -> str:
    """Compose the result message."""
    today = datetime.now().strftime("%A, %d %B %Y")

    raw_minutes = (clock_out - clock_in).total_seconds() / 60
    work_minutes = raw_minutes - break_min

    # Overtime vs under (vs 8-hour standard)
    standard = 8 * 60
    diff = work_minutes - standard
    diff_label = (
        f"🔺 +{format_duration(diff)} overtime"
        if diff > 0
        else f"🔻 {format_duration(diff)} under 8 h"
        if diff < 0
        else "✅ Exactly 8 h"
    )

    return (
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🕐  *Work Duration Summary*\n"
        f"📅  _{today}_\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"❇️  Clock-in  :  `{clock_in.strftime('%H:%M')}`\n"
        f"⛔  Clock-out :  `{clock_out.strftime('%H:%M')}`\n"
        f"☕  Break     :  `{format_duration(break_min)}`\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"⏱  Total shift  :  *{format_duration(raw_minutes)}*  `({decimal_hours(raw_minutes)})`\n"
        f"💼  Work time    :  *{format_duration(work_minutes)}*  `({decimal_hours(work_minutes)})`\n"
        f"{diff_label}\n"
        "━━━━━━━━━━━━━━━━━━━━"
    )


# ── Handlers ──────────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "👋 *Work Duration Calculator*\n\n"
        "I'll help you calculate how long you worked.\n\n"
        "Enter your *clock-in* time (e.g. `09:00` or `9am`):",
        parse_mode="Markdown",
        reply_markup=CANCEL_KEYBOARD,
    )
    return CLOCK_IN


async def get_clock_in(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if text == "❌ Cancel":
        return await cancel(update, context)

    t = parse_time(text)
    if t is None:
        await update.message.reply_text(
            "⚠️ Couldn't read that time. Try formats like `09:00`, `9.00`, or `9am`.",
            parse_mode="Markdown",
        )
        return CLOCK_IN

    context.user_data["clock_in"] = t
    await update.message.reply_text(
        f"✅ Clock-in: *{t.strftime('%H:%M')}*\n\nNow enter your *clock-out* time:",
        parse_mode="Markdown",
        reply_markup=CANCEL_KEYBOARD,
    )
    return CLOCK_OUT


async def get_clock_out(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if text == "❌ Cancel":
        return await cancel(update, context)

    t = parse_time(text)
    if t is None:
        await update.message.reply_text(
            "⚠️ Couldn't read that time. Try `17:30`, `5.30pm`, etc.",
            parse_mode="Markdown",
        )
        return CLOCK_OUT

    clock_in: datetime = context.user_data["clock_in"]

    # Handle overnight shift
    if t <= clock_in:
        t += timedelta(days=1)

    context.user_data["clock_out"] = t
    duration_so_far = format_duration((t - clock_in).total_seconds() / 60)

    break_keyboard = ReplyKeyboardMarkup(
        [["0", "15m", "30m", "45m", "1h", "1h 30m"], ["❌ Cancel"]],
        resize_keyboard=True,
    )
    await update.message.reply_text(
        f"✅ Clock-out: *{t.strftime('%H:%M')}*  _(shift: {duration_so_far})_\n\n"
        "How long was your *break*?\nEnter minutes (`30`), or use shorthand (`1h 15m`). "
        "Tap a quick option or type `0` for no break.",
        parse_mode="Markdown",
        reply_markup=break_keyboard,
    )
    return BREAK_TIME


async def get_break(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if text == "❌ Cancel":
        return await cancel(update, context)

    break_min = parse_break(text)
    if break_min is None:
        await update.message.reply_text(
            "⚠️ Couldn't parse that. Try `30`, `45m`, `1h`, `1h 30m`, or `0` for no break.",
            parse_mode="Markdown",
        )
        return BREAK_TIME

    clock_in: datetime = context.user_data["clock_in"]
    clock_out: datetime = context.user_data["clock_out"]

    summary = build_summary(clock_in, clock_out, break_min)

    again_keyboard = ReplyKeyboardMarkup(
        [["🔄 Calculate again"], ["❌ Done"]],
        resize_keyboard=True,
    )
    await update.message.reply_text(
        summary,
        parse_mode="Markdown",
        reply_markup=again_keyboard,
    )
    return ConversationHandler.END


async def again(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Restart calculation from /start handler."""
    return await start(update, context)


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "Cancelled. Type /start to try again.",
        reply_markup=ReplyKeyboardRemove(),
    )
    return ConversationHandler.END


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "*Work Duration Bot — Help*\n\n"
        "• /start — begin a new calculation\n"
        "• /help  — show this message\n\n"
        "*Accepted time formats*\n"
        "`09:00`  `9.00`  `9am`  `9:30pm`\n\n"
        "*Accepted break formats*\n"
        "`30` → 30 min  |  `1h` → 1 hour\n"
        "`1h 30m` → 90 min  |  `0` → no break\n\n"
        "Overnight shifts are handled automatically.",
        parse_mode="Markdown",
    )


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    app = Application.builder().token(BOT_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            MessageHandler(filters.Regex("^🔄 Calculate again$"), again),
        ],
        states={
            CLOCK_IN:   [MessageHandler(filters.TEXT & ~filters.COMMAND, get_clock_in)],
            CLOCK_OUT:  [MessageHandler(filters.TEXT & ~filters.COMMAND, get_clock_out)],
            BREAK_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_break)],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            MessageHandler(filters.Regex("^❌"), cancel),
        ],
    )

    app.add_handler(conv)
    app.add_handler(CommandHandler("help", help_cmd))

    logger.info("Bot is running…")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
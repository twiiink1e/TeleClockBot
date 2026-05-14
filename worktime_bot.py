"""
Telegram Attendance Bot
-----------------------
Commands:
  /in      - Clock in
  /out     - Clock out
  /break   - Start break
  /resume  - End break
  /status  - View current status

Install:
  pip install python-telegram-bot

Run:
  BOT_TOKEN=your_token_here python worktime_bot.py
"""

import os
import logging
from datetime import datetime, timezone
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes
from zoneinfo import ZoneInfo

logging.basicConfig(level=logging.INFO)

# In-memory store: { user_id: { ...session data } }
sessions: dict = {}

KEYBOARD = ReplyKeyboardMarkup(
    [["🟢 Clock In", "🔴 Clock Out"], ["☕ Break", "▶ Resume"], ["📋 Status"]],
    resize_keyboard=True,
)


def now() -> datetime:
    return datetime.now(ZoneInfo("Asia/Phnom_Penh"))


def fmt_time(dt: datetime) -> str:
    return dt.strftime("%H:%M")


def fmt_date(dt: datetime) -> str:
    return dt.strftime("%A, %d %b %Y")


def dur_str(seconds: float) -> str:
    seconds = int(seconds)
    h, r = divmod(seconds, 3600)
    m, s = divmod(r, 60)
    if h:
        return f"{h}h {m}m {s}s"
    if m:
        return f"{m}m {s}s"
    return f"{s}s"


def dur_dec(seconds: float) -> str:
    return f"{seconds / 3600:.2f} hrs"


def get_session(user_id: int) -> dict:
    if user_id not in sessions:
        sessions[user_id] = {
            "clocked_in": False,
            "clock_in_time": None,
            "clock_out_time": None,
            "on_break": False,
            "break_start": None,
            "total_break": 0.0,  # seconds
        }
    return sessions[user_id]


def net_seconds(s: dict) -> float:
    if not s["clock_in_time"]:
        return 0.0
    end = s["clock_out_time"] or now()
    gross = (end - s["clock_in_time"]).total_seconds()
    brk = s["total_break"]
    if s["on_break"] and s["break_start"]:
        brk += (now() - s["break_start"]).total_seconds()
    return max(0.0, gross - brk)


def status_text(s: dict) -> str:
    if not s["clock_in_time"]:
        return "Not clocked in."

    date_str = fmt_date(s["clock_in_time"])
    net = net_seconds(s)
    brk = s["total_break"]
    if s["on_break"] and s["break_start"]:
        brk += (now() - s["break_start"]).total_seconds()

    lines = [
        f"📅 {date_str}",
        f"🕐 Clock in:  {fmt_time(s['clock_in_time'])}",
    ]
    if s["clock_out_time"]:
        lines.append(f"🕐 Clock out: {fmt_time(s['clock_out_time'])}")
    if brk:
        lines.append(f"☕ Break:     {dur_str(brk)}")
    lines += [
        f"⏱ Net time:  {dur_str(net)}",
        f"🔢 Decimal:   {dur_dec(net)}",
    ]

    if s["on_break"]:
        lines.append("\n☕ Currently on break")
    elif s["clocked_in"]:
        lines.append("\n🟢 Currently working")
    else:
        lines.append("\n⚪ Clocked out")

    return "\n".join(lines)


# ── Handlers ──────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Welcome to *WorkClock Bot*!\n\n"
        "Use the buttons or commands below:\n"
        "/in — Clock in\n"
        "/out — Clock out\n"
        "/break — Start break\n"
        "/resume — End break\n"
        "/status — View summary",
        parse_mode="Markdown",
        reply_markup=KEYBOARD,
    )


async def cmd_in(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    s = get_session(uid)

    if s["clocked_in"]:
        await update.message.reply_text("⚠️ Already clocked in. Use /out first.")
        return

    s.update({
        "clocked_in": True,
        "clock_in_time": now(),
        "clock_out_time": None,
        "on_break": False,
        "break_start": None,
        "total_break": 0.0,
    })
    await update.message.reply_text(
        f"✅ Clocked in at *{fmt_time(s['clock_in_time'])}*\n"
        f"📅 {fmt_date(s['clock_in_time'])}",
        parse_mode="Markdown",
        reply_markup=KEYBOARD,
    )


async def cmd_out(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    s = get_session(uid)

    if not s["clocked_in"]:
        await update.message.reply_text("⚠️ Not clocked in yet. Use /in to start.")
        return

    if s["on_break"]:
        s["total_break"] += (now() - s["break_start"]).total_seconds()
        s["on_break"] = False
        s["break_start"] = None

    s["clocked_in"] = False
    s["clock_out_time"] = now()

    await update.message.reply_text(
        f"🔴 Clocked out at *{fmt_time(s['clock_out_time'])}*\n\n"
        f"{status_text(s)}",
        parse_mode="Markdown",
        reply_markup=KEYBOARD,
    )


async def cmd_break(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    s = get_session(uid)

    if not s["clocked_in"]:
        await update.message.reply_text("⚠️ Clock in first with /in.")
        return
    if s["on_break"]:
        await update.message.reply_text("⚠️ Already on break. Use /resume to end it.")
        return

    s["on_break"] = True
    s["break_start"] = now()
    await update.message.reply_text(
        f"☕ Break started at *{fmt_time(s['break_start'])}*",
        parse_mode="Markdown",
        reply_markup=KEYBOARD,
    )


async def cmd_resume(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    s = get_session(uid)

    if not s["on_break"]:
        await update.message.reply_text("⚠️ Not on a break right now.")
        return

    brk_dur = (now() - s["break_start"]).total_seconds()
    s["total_break"] += brk_dur
    s["on_break"] = False
    s["break_start"] = None
    await update.message.reply_text(
        f"▶️ Break ended. That was *{dur_str(brk_dur)}*. Back to work!",
        parse_mode="Markdown",
        reply_markup=KEYBOARD,
    )


async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    s = get_session(uid)
    await update.message.reply_text(
        status_text(s),
        reply_markup=KEYBOARD,
    )


async def handle_keyboard(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle the keyboard button presses (they send text, not commands)."""
    text = update.message.text
    if "Clock In" in text:
        await cmd_in(update, ctx)
    elif "Clock Out" in text:
        await cmd_out(update, ctx)
    elif "Break" in text:
        await cmd_break(update, ctx)
    elif "Resume" in text:
        await cmd_resume(update, ctx)
    elif "Status" in text:
        await cmd_status(update, ctx)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    token = os.environ.get("BOT_TOKEN")
    if not token:
        raise ValueError("Set BOT_TOKEN environment variable")

    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("in", cmd_in))
    app.add_handler(CommandHandler("out", cmd_out))
    app.add_handler(CommandHandler("break", cmd_break))
    app.add_handler(CommandHandler("resume", cmd_resume))
    app.add_handler(CommandHandler("status", cmd_status))

    from telegram.ext import MessageHandler, filters
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_keyboard))

    print("Bot running...")
    app.run_polling()


if __name__ == "__main__":
    main()
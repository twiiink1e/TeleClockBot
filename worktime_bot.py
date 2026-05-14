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
from datetime import datetime
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

DIVIDER = "─" * 24


def now() -> datetime:
    return datetime.now(ZoneInfo("Asia/Phnom_Penh"))


def fmt_time(dt: datetime) -> str:
    return dt.strftime("%I:%M %p")


def fmt_date(dt: datetime) -> str:
    return dt.strftime("%A, %d %b %Y")


def dur_str(seconds: float) -> str:
    seconds = int(seconds)
    h, r = divmod(seconds, 3600)
    m, s = divmod(r, 60)
    if h:
        return f"{h}h {m:02d}m {s:02d}s"
    if m:
        return f"{m}m {s:02d}s"
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
            "total_break": 0.0,
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
        return (
            "╔══════════════════════╗\n"
            "║    No Active Session     ║\n"
            "╚══════════════════════╝\n\n"
            "You haven't clocked in yet\\.\n"
            "Tap *🟢 Clock In* to start your day\\!"
        )

    net = net_seconds(s)
    brk = s["total_break"]
    if s["on_break"] and s["break_start"]:
        brk += (now() - s["break_start"]).total_seconds()

    # Status badge
    if s["on_break"]:
        badge = "☕  ON BREAK"
    elif s["clocked_in"]:
        badge = "🟢  WORKING"
    else:
        badge = "⚪  CLOCKED OUT"

    lines = [
        f"*{badge}*",
        f"`{DIVIDER}`",
        f"📅  {fmt_date(s['clock_in_time'])}",
        f"`{DIVIDER}`",
        f"🕐  *Clock In*    `{fmt_time(s['clock_in_time'])}`",
    ]

    if s["clock_out_time"]:
        lines.append(f"🕔  *Clock Out*   `{fmt_time(s['clock_out_time'])}`")

    if brk:
        lines.append(f"☕  *Break*       `{dur_str(brk)}`")

    lines += [
        f"`{DIVIDER}`",
        f"⏱  *Net Time*    `{dur_str(net)}`",
        f"🔢  *Decimal*     `{dur_dec(net)}`",
    ]

    return "\n".join(lines)


# ── Handlers ──────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    name = update.effective_user.first_name or "there"
    await update.message.reply_text(
        f"👋 *Hey {name}\\!* Welcome to *WorkClock Bot*\\.\n\n"
        f"`{DIVIDER}`\n"
        "Here's what I can do:\n\n"
        "🟢 `/in`  — Clock in\n"
        "🔴 `/out`  — Clock out\n"
        "☕ `/break`  — Start a break\n"
        "▶️ `/resume`  — End your break\n"
        "📋 `/status`  — View your summary\n\n"
        f"`{DIVIDER}`\n"
        "_Use the buttons below or type a command to get started\\._",
        parse_mode="MarkdownV2",
        reply_markup=KEYBOARD,
    )


async def cmd_in(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    s = get_session(uid)

    if s["clocked_in"]:
        await update.message.reply_text(
            "⚠️ *Already Clocked In*\n\n"
            "You're already on the clock\\.\n"
            "Use 🔴 `/out` when you're done\\.",
            parse_mode="MarkdownV2",
            reply_markup=KEYBOARD,
        )
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
        f"🟢 *Clocked In*\n\n"
        f"`{DIVIDER}`\n"
        f"🕐  `{fmt_time(s['clock_in_time'])}`\n"
        f"📅  {fmt_date(s['clock_in_time'])}\n"
        f"`{DIVIDER}`\n\n"
        "_Have a productive day\\! 💪_",
        parse_mode="MarkdownV2",
        reply_markup=KEYBOARD,
    )


async def cmd_out(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    s = get_session(uid)

    if not s["clocked_in"]:
        await update.message.reply_text(
            "⚠️ *Not Clocked In*\n\n"
            "No active session found\\.\n"
            "Use 🟢 `/in` to start your day\\.",
            parse_mode="MarkdownV2",
            reply_markup=KEYBOARD,
        )
        return

    if s["on_break"]:
        s["total_break"] += (now() - s["break_start"]).total_seconds()
        s["on_break"] = False
        s["break_start"] = None

    s["clocked_in"] = False
    s["clock_out_time"] = now()

    await update.message.reply_text(
        f"🔴 *Clocked Out* — Great work today\\!\n\n"
        f"{status_text(s)}",
        parse_mode="MarkdownV2",
        reply_markup=KEYBOARD,
    )


async def cmd_break(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    s = get_session(uid)

    if not s["clocked_in"]:
        await update.message.reply_text(
            "⚠️ *Not Clocked In*\n\n"
            "Clock in first with 🟢 `/in`\\.",
            parse_mode="MarkdownV2",
            reply_markup=KEYBOARD,
        )
        return

    if s["on_break"]:
        await update.message.reply_text(
            "⚠️ *Already On Break*\n\n"
            "Use ▶️ `/resume` to end your current break\\.",
            parse_mode="MarkdownV2",
            reply_markup=KEYBOARD,
        )
        return

    s["on_break"] = True
    s["break_start"] = now()
    await update.message.reply_text(
        f"☕ *Break Started*\n\n"
        f"`{DIVIDER}`\n"
        f"🕐  `{fmt_time(s['break_start'])}`\n"
        f"`{DIVIDER}`\n\n"
        "_Rest up\\! Use ▶️ `/resume` when you're back\\._",
        parse_mode="MarkdownV2",
        reply_markup=KEYBOARD,
    )


async def cmd_resume(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    s = get_session(uid)

    if not s["on_break"]:
        await update.message.reply_text(
            "⚠️ *Not On Break*\n\n"
            "You're not currently on a break\\.",
            parse_mode="MarkdownV2",
            reply_markup=KEYBOARD,
        )
        return

    brk_dur = (now() - s["break_start"]).total_seconds()
    s["total_break"] += brk_dur
    s["on_break"] = False
    s["break_start"] = None

    await update.message.reply_text(
        f"▶️ *Back to Work\\!*\n\n"
        f"`{DIVIDER}`\n"
        f"☕  Break lasted `{dur_str(brk_dur)}`\n"
        f"🕐  Resumed at  `{fmt_time(now())}`\n"
        f"`{DIVIDER}`\n\n"
        "_Welcome back — let's get it\\! 🚀_",
        parse_mode="MarkdownV2",
        reply_markup=KEYBOARD,
    )


async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    s = get_session(uid)
    await update.message.reply_text(
        status_text(s),
        parse_mode="MarkdownV2",
        reply_markup=KEYBOARD,
    )


async def handle_keyboard(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle keyboard button presses (they send text, not commands)."""
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
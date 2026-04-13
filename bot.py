# bot.py — ENCODER BOT  |  Main Bot Logic + Flask Web Server
# Deploy on Render free tier — Flask keeps the dyno alive,
# the bot runs in a background thread using long-polling.

import io
import os
import sys
import logging
import threading
from datetime import date, timedelta

import telebot
from telebot import types
from flask import Flask, jsonify

import config
import database as db
import encoder as enc

# ─── LOGGING ─────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("encoder_bot")

# ─── FLASK (Render keep-alive) ────────────────────────────────────────────────
app = Flask(__name__)

@app.route("/")
def index():
    return jsonify({"bot": config.BOT_NAME, "status": "running"})

@app.route("/health")
def health():
    return config.BOT_NAME + " is running", 200

@app.route("/stats")
def web_stats():
    stats = db.get_stats()
    return jsonify(stats)

# ─── TELEGRAM BOT ────────────────────────────────────────────────────────────
bot = telebot.TeleBot(config.BOT_TOKEN, parse_mode="Markdown")

# In-memory conversation state per user
# state[user_id] = {
#   "step":   "awaiting_code" | "awaiting_method" | "awaiting_output_format"
#   "code":   str
#   "method": str
# }
state: dict[int, dict] = {}


# ─── HELPERS ─────────────────────────────────────────────────────────────────

def is_admin(user_id: int) -> bool:
    return user_id in config.ADMIN_IDS


def clear_state(user_id: int):
    state.pop(user_id, None)


def ensure_registered(message: types.Message):
    user = message.from_user
    db.register_user(
        user.id,
        user.username,
        f"{user.first_name or ''} {user.last_name or ''}".strip(),
    )


def method_keyboard() -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup(row_width=3)
    kb.add(
        types.InlineKeyboardButton("🔐 Base64",   callback_data="method_base64"),
        types.InlineKeyboardButton("⚙️ Marshal",   callback_data="method_marshal"),
        types.InlineKeyboardButton("🔥 Ultra",     callback_data="method_ultra"),
    )
    kb.add(types.InlineKeyboardButton("❌ Cancel", callback_data="cancel"))
    return kb


def output_keyboard() -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("📝 Text",       callback_data="output_text"),
        types.InlineKeyboardButton("📄 File (.py)", callback_data="output_file"),
    )
    kb.add(types.InlineKeyboardButton("❌ Cancel", callback_data="cancel"))
    return kb


def main_menu_keyboard() -> types.ReplyKeyboardMarkup:
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add(
        types.KeyboardButton("🔐 Encode"),
        types.KeyboardButton("👑 Premium"),
        types.KeyboardButton("📊 My Stats"),
        types.KeyboardButton("ℹ️ Help"),
    )
    return kb


# ─── /start ──────────────────────────────────────────────────────────────────

@bot.message_handler(commands=["start"])
def cmd_start(message: types.Message):
    ensure_registered(message)
    bot.send_message(
        message.chat.id,
        config.WELCOME_MESSAGE,
        reply_markup=main_menu_keyboard(),
    )


# ─── /help ───────────────────────────────────────────────────────────────────

@bot.message_handler(commands=["help"])
def cmd_help(message: types.Message):
    ensure_registered(message)
    bot.send_message(message.chat.id, config.HELP_MESSAGE)


# ─── /cancel ─────────────────────────────────────────────────────────────────

@bot.message_handler(commands=["cancel"])
def cmd_cancel(message: types.Message):
    clear_state(message.from_user.id)
    bot.send_message(
        message.chat.id,
        "✅ Operation cancelled.",
        reply_markup=main_menu_keyboard(),
    )


# ─── /encode  (or keyboard shortcut) ─────────────────────────────────────────

@bot.message_handler(commands=["encode"])
@bot.message_handler(func=lambda m: m.text == "🔐 Encode")
def cmd_encode(message: types.Message):
    ensure_registered(message)
    uid = message.from_user.id
    allowed, remaining = db.can_encode(uid)
    if not allowed:
        bot.send_message(
            message.chat.id,
            f"❌ *Daily limit reached!*\n\n"
            f"Free users get *{config.FREE_DAILY_LIMIT} encodes/day*.\n"
            f"Upgrade to premium for unlimited encodes:\n/premium",
        )
        return
    state[uid] = {"step": "awaiting_code"}
    hint = "♾️ Unlimited (Premium)" if remaining == -1 else f"{remaining} left today"
    bot.send_message(
        message.chat.id,
        f"📤 *Send your Python code or upload a `.py` file.*\n\n"
        f"📊 Encodes remaining: `{hint}`",
    )


# ─── /premium ────────────────────────────────────────────────────────────────

@bot.message_handler(commands=["premium"])
@bot.message_handler(func=lambda m: m.text == "👑 Premium")
def cmd_premium(message: types.Message):
    ensure_registered(message)
    uid = message.from_user.id
    if db.is_premium(uid):
        user = db.get_user(uid)
        expiry = user.get("premium_until", "Lifetime")
        bot.send_message(
            message.chat.id,
            f"👑 *You already have Premium!*\n\nExpires: `{expiry}`",
        )
        return
    bot.send_message(message.chat.id, config.PAYMENT_INSTRUCTIONS)


# ─── /pay <TrxID> ────────────────────────────────────────────────────────────

@bot.message_handler(commands=["pay"])
def cmd_pay(message: types.Message):
    ensure_registered(message)
    uid = message.from_user.id
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        bot.send_message(
            message.chat.id,
            "⚠️ Usage: `/pay <TransactionID>`\n\nExample: `/pay 8JK23ABC9X`",
        )
        return

    txid = parts[1].strip().upper()
    ok = db.submit_payment(uid, txid)
    if not ok:
        bot.send_message(
            message.chat.id,
            "❌ *This Transaction ID already exists.*\n\n"
            "If you submitted it before, please wait for admin verification.",
        )
        return

    bot.send_message(
        message.chat.id,
        f"✅ *Payment submitted!*\n\n"
        f"TrxID: `{txid}`\n\n"
        f"⏳ Admin will verify shortly. You'll receive a notification.",
    )

    # Notify all admins
    user = db.get_user(uid)
    uname = f"@{user['username']}" if user.get("username") else user.get("full_name", str(uid))
    for admin_id in config.ADMIN_IDS:
        try:
            bot.send_message(
                admin_id,
                f"💳 *New Payment Request*\n\n"
                f"User: {uname} (`{uid}`)\n"
                f"TrxID: `{txid}`\n\n"
                f"To verify:\n`/verifypay {txid} {uid}`",
            )
        except Exception:
            pass


# ─── /stats ──────────────────────────────────────────────────────────────────

@bot.message_handler(commands=["stats"])
@bot.message_handler(func=lambda m: m.text == "📊 My Stats")
def cmd_stats(message: types.Message):
    ensure_registered(message)
    uid = message.from_user.id
    s = db.get_user_stats(uid)
    premium_str = "👑 Premium" if s["is_premium"] else "🆓 Free"
    remaining = "♾️ Unlimited" if s["today_remaining"] == -1 else str(s["today_remaining"])
    expiry = s["premium_until"] or "—"

    method_lines = "\n".join(
        f"  • {r['method'].title()}: {r['c']}" for r in s["method_breakdown"]
    ) or "  None yet"

    bot.send_message(
        message.chat.id,
        f"📊 *Your Statistics*\n\n"
        f"Plan: {premium_str}\n"
        f"Premium Until: `{expiry}`\n\n"
        f"Total Encodes: `{s['total_encodes']}`\n"
        f"Today Used: `{s['today_used']}`\n"
        f"Remaining Today: `{remaining}`\n\n"
        f"*By Method:*\n{method_lines}",
    )


# ─── ADMIN: /adminstats ───────────────────────────────────────────────────────

@bot.message_handler(commands=["adminstats"])
def cmd_adminstats(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    s = db.get_stats()
    method_lines = "\n".join(
        f"  • {r['method'].title()}: {r['c']}" for r in s["method_breakdown"]
    ) or "  None yet"

    bot.send_message(
        message.chat.id,
        f"📊 *System Statistics*\n\n"
        f"👥 Total Users: `{s['total_users']}`\n"
        f"👑 Premium: `{s['premium_count']}`\n"
        f"🆓 Free: `{s['free_count']}`\n\n"
        f"⚙️ Total Encodes: `{s['total_encodes']}`\n"
        f"📅 Today Encodes: `{s['today_encodes']}`\n\n"
        f"💳 Pending Payments: `{s['pending_payments']}`\n\n"
        f"*Encoding Methods:*\n{method_lines}",
    )


# ─── ADMIN: /addpremium ───────────────────────────────────────────────────────

@bot.message_handler(commands=["addpremium"])
def cmd_addpremium(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    parts = message.text.split()
    if len(parts) < 2:
        bot.send_message(message.chat.id, "Usage: `/addpremium <user_id>`")
        return
    try:
        target = int(parts[1])
    except ValueError:
        bot.send_message(message.chat.id, "❌ Invalid user ID.")
        return

    expiry = str(date.today() + timedelta(days=config.PREMIUM_DURATION_DAYS))
    db.set_premium(target, until_date=expiry, grant=True)

    bot.send_message(
        message.chat.id,
        f"✅ User `{target}` upgraded to *Premium* until `{expiry}`.",
    )
    try:
        bot.send_message(
            target,
            f"🎉 *Congratulations!*\n\n"
            f"Your account has been upgraded to *Premium* until `{expiry}`.\n\n"
            f"Enjoy unlimited encodes! 🔥",
        )
    except Exception:
        pass


# ─── ADMIN: /removepremium ────────────────────────────────────────────────────

@bot.message_handler(commands=["removepremium"])
def cmd_removepremium(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    parts = message.text.split()
    if len(parts) < 2:
        bot.send_message(message.chat.id, "Usage: `/removepremium <user_id>`")
        return
    try:
        target = int(parts[1])
    except ValueError:
        bot.send_message(message.chat.id, "❌ Invalid user ID.")
        return

    db.set_premium(target, grant=False)
    bot.send_message(message.chat.id, f"✅ Premium removed from user `{target}`.")
    try:
        bot.send_message(
            target,
            "⚠️ Your *Premium* access has been revoked.\n\nContact admin if this is a mistake.",
        )
    except Exception:
        pass


# ─── ADMIN: /pending ─────────────────────────────────────────────────────────

@bot.message_handler(commands=["pending"])
def cmd_pending(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    rows = db.get_pending_payments()
    if not rows:
        bot.send_message(message.chat.id, "✅ No pending payments.")
        return

    text = "💳 *Pending Payments:*\n\n"
    for r in rows:
        uname = f"@{r['username']}" if r.get("username") else r.get("full_name", "—")
        text += (
            f"• `{r['txid']}` — {uname} (`{r['user_id']}`)\n"
            f"  Submitted: {r['submitted_at']}\n"
            f"  Verify: `/verifypay {r['txid']} {r['user_id']}`\n\n"
        )
    bot.send_message(message.chat.id, text)


# ─── ADMIN: /verifypay ────────────────────────────────────────────────────────

@bot.message_handler(commands=["verifypay"])
def cmd_verifypay(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    parts = message.text.split()
    if len(parts) < 3:
        bot.send_message(message.chat.id, "Usage: `/verifypay <TrxID> <user_id>`")
        return

    txid = parts[1].upper()
    try:
        target = int(parts[2])
    except ValueError:
        bot.send_message(message.chat.id, "❌ Invalid user ID.")
        return

    row = db.verify_payment(txid, message.from_user.id)
    if not row:
        bot.send_message(message.chat.id, f"❌ TrxID `{txid}` not found or already verified.")
        return

    expiry = str(date.today() + timedelta(days=config.PREMIUM_DURATION_DAYS))
    db.set_premium(target, until_date=expiry, grant=True)

    bot.send_message(
        message.chat.id,
        f"✅ Payment `{txid}` verified!\nUser `{target}` granted premium until `{expiry}`.",
    )
    try:
        bot.send_message(
            target,
            f"🎉 *Payment Verified!*\n\n"
            f"TrxID: `{txid}`\n"
            f"Your *Premium* is active until `{expiry}`.\n\n"
            f"Enjoy unlimited encodes! 🔥",
        )
    except Exception:
        pass


# ─── ADMIN: /broadcast ────────────────────────────────────────────────────────

@bot.message_handler(commands=["broadcast"])
def cmd_broadcast(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        bot.send_message(message.chat.id, "Usage: `/broadcast <message>`")
        return

    text = parts[1]
    user_ids = db.get_all_user_ids()
    sent = 0
    failed = 0

    bot.send_message(message.chat.id, f"📢 Broadcasting to {len(user_ids)} users…")
    for uid in user_ids:
        try:
            bot.send_message(uid, f"📢 *Broadcast from Admin:*\n\n{text}")
            sent += 1
        except Exception:
            failed += 1

    bot.send_message(
        message.chat.id,
        f"✅ Broadcast complete.\n\nSent: `{sent}` | Failed: `{failed}`",
    )


# ─── FILE UPLOAD HANDLER ──────────────────────────────────────────────────────

@bot.message_handler(content_types=["document"])
def handle_document(message: types.Message):
    ensure_registered(message)
    uid = message.from_user.id
    doc = message.document

    if not doc.file_name.endswith(".py"):
        bot.send_message(
            message.chat.id,
            "⚠️ Please upload a *Python file* (`.py`). Other file types are not supported.",
        )
        return

    allowed, remaining = db.can_encode(uid)
    if not allowed:
        bot.send_message(
            message.chat.id,
            f"❌ *Daily limit reached!*\n\nUpgrade to Premium for unlimited encodes: /premium",
        )
        return

    try:
        file_info = bot.get_file(doc.file_id)
        downloaded = bot.download_file(file_info.file_path)
        code = downloaded.decode("utf-8")
    except UnicodeDecodeError:
        bot.send_message(message.chat.id, "❌ Could not read file — please ensure it's UTF-8 encoded.")
        return
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Failed to download file: {e}")
        return

    if len(code.strip()) == 0:
        bot.send_message(message.chat.id, "❌ The uploaded file is empty.")
        return

    hint = "♾️ Unlimited" if remaining == -1 else f"{remaining} left today"
    state[uid] = {"step": "awaiting_method", "code": code}
    bot.send_message(
        message.chat.id,
        f"✅ File received: `{doc.file_name}` ({len(code)} chars)\n"
        f"📊 Remaining: `{hint}`\n\n"
        f"🔧 *Choose encoding method:*",
        reply_markup=method_keyboard(),
    )


# ─── TEXT MESSAGE HANDLER ─────────────────────────────────────────────────────

@bot.message_handler(func=lambda m: m.text and not m.text.startswith("/"))
def handle_text(message: types.Message):
    ensure_registered(message)
    uid = message.from_user.id

    # Keyboard shortcuts → delegate to proper handlers
    if message.text in ("👑 Premium", "📊 My Stats", "ℹ️ Help", "🔐 Encode"):
        return  # already handled by separate decorators

    current = state.get(uid, {})

    if current.get("step") == "awaiting_code":
        code = message.text.strip()
        if len(code) < 5:
            bot.send_message(message.chat.id, "⚠️ Code is too short. Please send valid Python code.")
            return

        allowed, remaining = db.can_encode(uid)
        if not allowed:
            clear_state(uid)
            bot.send_message(
                message.chat.id,
                "❌ *Daily limit reached!*\n\nUpgrade: /premium",
            )
            return

        hint = "♾️ Unlimited" if remaining == -1 else f"{remaining} left today"
        state[uid] = {"step": "awaiting_method", "code": code}
        bot.send_message(
            message.chat.id,
            f"✅ Code received ({len(code)} chars)\n"
            f"📊 Remaining: `{hint}`\n\n"
            f"🔧 *Choose encoding method:*",
            reply_markup=method_keyboard(),
        )
        return

    # Default: treat as code input
    allowed, remaining = db.can_encode(uid)
    if not allowed:
        bot.send_message(
            message.chat.id,
            "❌ *Daily limit reached!*\n\nUpgrade: /premium",
        )
        return

    code = message.text.strip()
    if len(code) < 5:
        bot.send_message(
            message.chat.id,
            "🤔 Not sure what to do with that.\n\nSend Python code or type /encode to start.",
            reply_markup=main_menu_keyboard(),
        )
        return

    hint = "♾️ Unlimited" if remaining == -1 else f"{remaining} left today"
    state[uid] = {"step": "awaiting_method", "code": code}
    bot.send_message(
        message.chat.id,
        f"✅ Code received ({len(code)} chars)\n"
        f"📊 Remaining: `{hint}`\n\n"
        f"🔧 *Choose encoding method:*",
        reply_markup=method_keyboard(),
    )


# ─── INLINE BUTTON CALLBACKS ──────────────────────────────────────────────────

@bot.callback_query_handler(func=lambda c: True)
def handle_callback(call: types.CallbackQuery):
    uid = call.from_user.id
    data = call.data

    # ── Cancel ──────────────────────────────────────────────────────────────
    if data == "cancel":
        clear_state(uid)
        bot.answer_callback_query(call.id, "Cancelled")
        bot.edit_message_text(
            "✅ Operation cancelled.",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
        )
        return

    # ── Method selection ─────────────────────────────────────────────────────
    if data.startswith("method_"):
        method = data.replace("method_", "")
        current = state.get(uid, {})
        if current.get("step") != "awaiting_method":
            bot.answer_callback_query(call.id, "⚠️ Please send code first.")
            return

        state[uid]["method"] = method
        state[uid]["step"] = "awaiting_output_format"

        label = enc.get_method_label(method)
        bot.answer_callback_query(call.id, f"Selected: {label}")
        bot.edit_message_text(
            f"✅ Method: *{label}*\n\n📤 *How do you want the output?*",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=output_keyboard(),
            parse_mode="Markdown",
        )
        return

    # ── Output format ────────────────────────────────────────────────────────
    if data.startswith("output_"):
        fmt = data.replace("output_", "")  # "text" or "file"
        current = state.get(uid, {})
        if current.get("step") != "awaiting_output_format":
            bot.answer_callback_query(call.id, "⚠️ Session expired. Please start again.")
            return

        code   = current.get("code", "")
        method = current.get("method", "base64")

        bot.answer_callback_query(call.id, "⚙️ Encoding…")
        bot.edit_message_text(
            "⏳ *Encoding your code…*",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            parse_mode="Markdown",
        )

        success, result = enc.encode(code, method)
        if not success:
            clear_state(uid)
            bot.send_message(
                call.message.chat.id,
                f"❌ *Encoding failed!*\n\n`{result}`",
                reply_markup=main_menu_keyboard(),
            )
            return

        # Record usage
        db.increment_usage(uid, method)
        clear_state(uid)

        label = enc.get_method_label(method)
        s = db.get_user_stats(uid)
        remaining_str = "♾️ Unlimited" if s["today_remaining"] == -1 else str(s["today_remaining"])

        if fmt == "text":
            # Telegram message limit is 4096 chars; split if needed
            header_msg = f"✅ *Encoded with {label}*\n📊 Remaining today: `{remaining_str}`\n\n"
            max_code_len = 4096 - len(header_msg) - 10
            if len(result) <= max_code_len:
                bot.send_message(
                    call.message.chat.id,
                    header_msg + f"```python\n{result}\n```",
                    reply_markup=main_menu_keyboard(),
                )
            else:
                bot.send_message(call.message.chat.id, header_msg + "_(code too large, sending as file)_")
                _send_as_file(call.message.chat.id, result, method, remaining_str, label)

        else:  # file
            _send_as_file(call.message.chat.id, result, method, remaining_str, label)

        return


def _send_as_file(chat_id: int, result: str, method: str, remaining_str: str, label: str):
    timestamp = __import__("datetime").datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"encoded_{method}_{timestamp}.py"
    file_bytes = io.BytesIO(result.encode("utf-8"))
    file_bytes.name = filename
    bot.send_document(
        chat_id,
        file_bytes,
        caption=(
            f"✅ *Encoded with {label}*\n"
            f"📄 File: `{filename}`\n"
            f"📊 Remaining today: `{remaining_str}`"
        ),
        parse_mode="Markdown",
    )


# ─── KEYBOARD SHORTCUTS (Reply Keyboard) ─────────────────────────────────────

@bot.message_handler(func=lambda m: m.text == "ℹ️ Help")
def kb_help(message: types.Message):
    cmd_help(message)


# ─── BOT POLLING THREAD ───────────────────────────────────────────────────────

def run_bot():
    logger.info("Starting Telegram bot polling…")
    while True:
        try:
            bot.polling(non_stop=True, interval=1, timeout=60)
        except Exception as e:
            logger.error(f"Bot polling crashed: {e}. Restarting in 5s…")
            __import__("time").sleep(5)


# ─── ENTRY POINT ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logger.info(f"=== {config.BOT_NAME} starting ===")

    # Initialise database
    db.init_db()

    # Start the Telegram bot in a background daemon thread
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    logger.info("Bot thread started.")

    # Start Flask (blocking) — Render needs an HTTP server
    logger.info(f"Starting Flask on {config.HOST}:{config.PORT}")
    app.run(host=config.HOST, port=config.PORT, debug=False, use_reloader=False)

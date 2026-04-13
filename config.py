# config.py — ENCODER BOT Configuration

import os

# ─── BOT CREDENTIALS ─────────────────────────────────────────────────────────
BOT_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")

# ─── ADMIN CONFIGURATION ─────────────────────────────────────────────────────
# Add your Telegram user IDs here (get via @userinfobot)
ADMIN_IDS = [
    int(x) for x in os.environ.get("ADMIN_IDS", "123456789").split(",")
    if x.strip().isdigit()
]

# ─── PREMIUM PRICING ─────────────────────────────────────────────────────────
PREMIUM_PRICE_BDT = 99  # Price in BDT (Bangladeshi Taka)
PREMIUM_DURATION_DAYS = 30

# ─── PAYMENT METHODS ─────────────────────────────────────────────────────────
BKASH_NUMBER = os.environ.get("BKASH_NUMBER", "01XXXXXXXXX")
NAGAD_NUMBER = os.environ.get("NAGAD_NUMBER", "01XXXXXXXXX")
PAYMENT_INSTRUCTIONS = f"""
💳 *PREMIUM UPGRADE — {PREMIUM_PRICE_BDT} BDT / 30 Days*

━━━━━━━━━━━━━━━━━━━━━
💚 *bKash Payment:*
   Number: `{BKASH_NUMBER}`
   Type: Personal / Send Money

🟠 *Nagad Payment:*
   Number: `{NAGAD_NUMBER}`
   Type: Personal / Send Money
━━━━━━━━━━━━━━━━━━━━━

📋 *Steps:*
1. Send *{PREMIUM_PRICE_BDT} BDT* to one of the numbers above
2. Copy your *Transaction ID (TrxID)*
3. Send it here using:
   `/pay <TrxID>`

*Example:* `/pay 8JK23ABC9X`

⚠️ Admin will verify and activate within a few minutes.
"""

# ─── FREE TIER LIMITS ────────────────────────────────────────────────────────
FREE_DAILY_LIMIT = 3

# ─── DATABASE ────────────────────────────────────────────────────────────────
DATABASE_PATH = os.environ.get("DATABASE_PATH", "encoder_bot.db")

# ─── WEB SERVER ──────────────────────────────────────────────────────────────
PORT = int(os.environ.get("PORT", 8080))
HOST = "0.0.0.0"

# ─── BOT METADATA ────────────────────────────────────────────────────────────
BOT_NAME = "ENCODER BOT"
DEVELOPER = "Md. Mainul Islam"
GITHUB = "https://github.com/M41NUL"
EMAIL = "githubmainul@gmail.com"

# ─── WELCOME MESSAGE ─────────────────────────────────────────────────────────
WELCOME_MESSAGE = """
🔐 *Welcome to ENCODER BOT!*

_The ultimate Python code protection tool._

━━━━━━━━━━━━━━━━━━━━━
⚙️ *Available Encoding Methods:*

🔐 *Base64* — Fast, lightweight encoding
⚙️ *Marshal* — Python bytecode encoding  
🔥 *Ultra* — Base64 + zlib + marshal (max protection)

━━━━━━━━━━━━━━━━━━━━━
📤 *How to Use:*
1. Send a `.py` file or paste Python code
2. Choose your encoding method
3. Choose output format (text or file)
4. Receive your protected code!

━━━━━━━━━━━━━━━━━━━━━
🆓 *Free Plan:* 3 encodes/day
👑 *Premium Plan:* Unlimited encodes

Type /help for all commands.
"""

HELP_MESSAGE = """
📖 *ENCODER BOT — Command Reference*

━━━━━━━━━━━━━━━━━━━━━
👤 *User Commands:*
/start — Welcome screen
/help — This help message
/encode — Start encoding (or just send code/file)
/premium — Upgrade to premium
/pay <TrxID> — Submit payment transaction ID
/stats — Your usage statistics
/cancel — Cancel current operation

━━━━━━━━━━━━━━━━━━━━━
👑 *Admin Commands:*
/addpremium <user_id> — Grant premium
/removepremium <user_id> — Revoke premium
/broadcast <message> — Message all users
/adminstats — Full system statistics
/pending — View pending payments
/verifypay <TrxID> <user_id> — Verify payment

━━━━━━━━━━━━━━━━━━━━━
💡 *Tip:* Just send a `.py` file or paste code directly!
"""

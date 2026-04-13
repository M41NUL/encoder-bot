# database.py — ENCODER BOT Database Layer (SQLite)

import sqlite3
import logging
from datetime import date, datetime
from contextlib import contextmanager
from config import DATABASE_PATH, FREE_DAILY_LIMIT

logger = logging.getLogger(__name__)


# ─── CONNECTION MANAGER ──────────────────────────────────────────────────────

@contextmanager
def get_db():
    conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ─── SCHEMA INITIALISATION ───────────────────────────────────────────────────

def init_db():
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                user_id       INTEGER PRIMARY KEY,
                username      TEXT,
                full_name     TEXT,
                is_premium    INTEGER DEFAULT 0,
                premium_until TEXT,
                joined_at     TEXT DEFAULT (datetime('now')),
                last_seen     TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS usage (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id       INTEGER NOT NULL,
                method        TEXT NOT NULL,
                encoded_at    TEXT DEFAULT (datetime('now')),
                FOREIGN KEY(user_id) REFERENCES users(user_id)
            );

            CREATE TABLE IF NOT EXISTS daily_usage (
                user_id       INTEGER NOT NULL,
                usage_date    TEXT NOT NULL,
                count         INTEGER DEFAULT 0,
                PRIMARY KEY (user_id, usage_date),
                FOREIGN KEY(user_id) REFERENCES users(user_id)
            );

            CREATE TABLE IF NOT EXISTS payments (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id       INTEGER NOT NULL,
                txid          TEXT UNIQUE NOT NULL,
                status        TEXT DEFAULT 'pending',
                submitted_at  TEXT DEFAULT (datetime('now')),
                verified_at   TEXT,
                verified_by   INTEGER,
                FOREIGN KEY(user_id) REFERENCES users(user_id)
            );

            CREATE TABLE IF NOT EXISTS broadcasts (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id      INTEGER NOT NULL,
                message       TEXT NOT NULL,
                sent_at       TEXT DEFAULT (datetime('now')),
                recipients    INTEGER DEFAULT 0
            );
        """)
    logger.info("Database initialised.")


# ─── USER MANAGEMENT ─────────────────────────────────────────────────────────

def register_user(user_id: int, username: str, full_name: str):
    with get_db() as conn:
        conn.execute("""
            INSERT INTO users (user_id, username, full_name)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username  = excluded.username,
                full_name = excluded.full_name,
                last_seen = datetime('now')
        """, (user_id, username or "", full_name or ""))


def get_user(user_id: int) -> dict | None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()
        return dict(row) if row else None


def get_all_users() -> list[dict]:
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM users").fetchall()
        return [dict(r) for r in rows]


def get_all_user_ids() -> list[int]:
    with get_db() as conn:
        rows = conn.execute("SELECT user_id FROM users").fetchall()
        return [r["user_id"] for r in rows]


# ─── PREMIUM MANAGEMENT ──────────────────────────────────────────────────────

def set_premium(user_id: int, until_date: str | None = None, grant: bool = True):
    with get_db() as conn:
        conn.execute("""
            UPDATE users SET is_premium = ?, premium_until = ?
            WHERE user_id = ?
        """, (1 if grant else 0, until_date, user_id))


def is_premium(user_id: int) -> bool:
    user = get_user(user_id)
    if not user or not user["is_premium"]:
        return False
    if user["premium_until"]:
        expiry = datetime.fromisoformat(user["premium_until"]).date()
        if expiry < date.today():
            # expired — auto-revoke
            set_premium(user_id, grant=False)
            return False
    return True


def get_premium_users() -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM users WHERE is_premium = 1"
        ).fetchall()
        return [dict(r) for r in rows]


# ─── USAGE TRACKING ──────────────────────────────────────────────────────────

def get_daily_usage(user_id: int) -> int:
    today = str(date.today())
    with get_db() as conn:
        row = conn.execute("""
            SELECT count FROM daily_usage
            WHERE user_id = ? AND usage_date = ?
        """, (user_id, today)).fetchone()
        return row["count"] if row else 0


def increment_usage(user_id: int, method: str):
    today = str(date.today())
    with get_db() as conn:
        conn.execute("""
            INSERT INTO daily_usage (user_id, usage_date, count)
            VALUES (?, ?, 1)
            ON CONFLICT(user_id, usage_date) DO UPDATE SET
                count = count + 1
        """, (user_id, today))
        conn.execute("""
            INSERT INTO usage (user_id, method) VALUES (?, ?)
        """, (user_id, method))


def can_encode(user_id: int) -> tuple[bool, int]:
    """Returns (allowed, remaining). Premium users always get True."""
    if is_premium(user_id):
        return True, -1  # -1 = unlimited
    used = get_daily_usage(user_id)
    remaining = max(0, FREE_DAILY_LIMIT - used)
    return remaining > 0, remaining


# ─── PAYMENT SYSTEM ──────────────────────────────────────────────────────────

def submit_payment(user_id: int, txid: str) -> bool:
    """Returns False if TrxID already exists."""
    try:
        with get_db() as conn:
            conn.execute("""
                INSERT INTO payments (user_id, txid) VALUES (?, ?)
            """, (user_id, txid.upper()))
        return True
    except sqlite3.IntegrityError:
        return False  # duplicate TrxID


def get_pending_payments() -> list[dict]:
    with get_db() as conn:
        rows = conn.execute("""
            SELECT p.*, u.username, u.full_name
            FROM payments p
            JOIN users u ON p.user_id = u.user_id
            WHERE p.status = 'pending'
            ORDER BY p.submitted_at ASC
        """).fetchall()
        return [dict(r) for r in rows]


def verify_payment(txid: str, admin_id: int) -> dict | None:
    """Marks a payment verified and returns the payment row, or None if not found."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM payments WHERE txid = ? AND status = 'pending'",
            (txid.upper(),)
        ).fetchone()
        if not row:
            return None
        conn.execute("""
            UPDATE payments
            SET status = 'verified', verified_at = datetime('now'), verified_by = ?
            WHERE txid = ?
        """, (admin_id, txid.upper()))
        return dict(row)


def get_payment_by_txid(txid: str) -> dict | None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM payments WHERE txid = ?", (txid.upper(),)
        ).fetchone()
        return dict(row) if row else None


# ─── STATISTICS ──────────────────────────────────────────────────────────────

def get_stats() -> dict:
    today = str(date.today())
    with get_db() as conn:
        total_users = conn.execute(
            "SELECT COUNT(*) as c FROM users"
        ).fetchone()["c"]

        premium_count = conn.execute(
            "SELECT COUNT(*) as c FROM users WHERE is_premium = 1"
        ).fetchone()["c"]

        total_encodes = conn.execute(
            "SELECT COUNT(*) as c FROM usage"
        ).fetchone()["c"]

        today_encodes = conn.execute(
            "SELECT COALESCE(SUM(count), 0) as c FROM daily_usage WHERE usage_date = ?",
            (today,)
        ).fetchone()["c"]

        method_breakdown = conn.execute("""
            SELECT method, COUNT(*) as c FROM usage
            GROUP BY method ORDER BY c DESC
        """).fetchall()

        pending_payments = conn.execute(
            "SELECT COUNT(*) as c FROM payments WHERE status = 'pending'"
        ).fetchone()["c"]

        return {
            "total_users": total_users,
            "premium_count": premium_count,
            "free_count": total_users - premium_count,
            "total_encodes": total_encodes,
            "today_encodes": today_encodes,
            "method_breakdown": [dict(r) for r in method_breakdown],
            "pending_payments": pending_payments,
        }


def get_user_stats(user_id: int) -> dict:
    today = str(date.today())
    with get_db() as conn:
        total = conn.execute(
            "SELECT COUNT(*) as c FROM usage WHERE user_id = ?", (user_id,)
        ).fetchone()["c"]

        today_used = conn.execute("""
            SELECT COALESCE(count, 0) as c FROM daily_usage
            WHERE user_id = ? AND usage_date = ?
        """, (user_id, today)).fetchone()
        today_used = today_used["c"] if today_used else 0

        methods = conn.execute("""
            SELECT method, COUNT(*) as c FROM usage
            WHERE user_id = ? GROUP BY method ORDER BY c DESC
        """, (user_id,)).fetchall()

    premium = is_premium(user_id)
    user = get_user(user_id)

    return {
        "total_encodes": total,
        "today_used": today_used,
        "today_remaining": -1 if premium else max(0, FREE_DAILY_LIMIT - today_used),
        "is_premium": premium,
        "premium_until": user["premium_until"] if user else None,
        "method_breakdown": [dict(r) for r in methods],
    }

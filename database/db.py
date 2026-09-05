import os
import sqlite3
from datetime import date, timedelta

from werkzeug.security import generate_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
DB_PATH = os.path.join(PROJECT_ROOT, "spendly.db")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def get_user_by_email(email):
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM users WHERE email = ?",
        (email,),
    ).fetchone()
    conn.close()
    return row


def get_user_by_id(user_id):
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM users WHERE id = ?",
        (user_id,),
    ).fetchone()
    conn.close()
    return row


def get_expense_stats(user_id):
    conn = get_db()
    totals_row = conn.execute(
        "SELECT COALESCE(SUM(amount), 0) AS total_spent, "
        "COUNT(*) AS transaction_count "
        "FROM expenses WHERE user_id = ?",
        (user_id,),
    ).fetchone()
    top_row = conn.execute(
        "SELECT category, SUM(amount) AS category_total "
        "FROM expenses WHERE user_id = ? "
        "GROUP BY category "
        "ORDER BY category_total DESC "
        "LIMIT 1",
        (user_id,),
    ).fetchone()
    conn.close()
    return {
        "total_spent": totals_row["total_spent"],
        "transaction_count": totals_row["transaction_count"],
        "top_category": top_row["category"] if top_row else None,
    }


def get_recent_expenses(user_id, limit=10):
    conn = get_db()
    rows = conn.execute(
        "SELECT date, description, category, amount "
        "FROM expenses WHERE user_id = ? "
        "ORDER BY date DESC, id DESC "
        "LIMIT ?",
        (user_id, limit),
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_category_totals(user_id):
    conn = get_db()
    rows = conn.execute(
        "SELECT category, SUM(amount) AS total "
        "FROM expenses WHERE user_id = ? "
        "GROUP BY category "
        "ORDER BY total DESC",
        (user_id,),
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def init_db():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            name          TEXT NOT NULL,
            email         TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at    TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS expenses (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL,
            amount      REAL NOT NULL,
            category    TEXT NOT NULL,
            date        TEXT NOT NULL,
            description TEXT,
            created_at  TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    """)
    conn.commit()
    conn.close()


def seed_db():
    conn = get_db()
    existing = conn.execute("SELECT COUNT(*) AS count FROM users").fetchone()
    if existing["count"] > 0:
        conn.close()
        return

    cursor = conn.execute(
        "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
        ("Demo User", "demo@spendly.com", generate_password_hash("demo123")),
    )
    user_id = cursor.lastrowid

    today = date.today()
    first_of_month = today.replace(day=1)

    def day(offset):
        d = first_of_month + timedelta(days=offset)
        return min(d, today).isoformat()

    expenses = [
        ("Food", 12.50, "Grocery run at Trader Joe's", 1),
        ("Transport", 45.00, "Monthly metro pass", 3),
        ("Bills", 89.99, "Electricity bill", 6),
        ("Health", 25.00, "Pharmacy — allergy medication", 9),
        ("Entertainment", 15.99, "Movie ticket", 12),
        ("Shopping", 62.30, "New running shoes", 15),
        ("Other", 20.00, "Birthday gift for a friend", 18),
        ("Food", 34.75, "Dinner with friends", 21),
    ]
    for category, amount, description, offset in expenses:
        conn.execute(
            "INSERT INTO expenses (user_id, amount, category, date, description) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, amount, category, day(offset), description),
        )

    conn.commit()
    conn.close()


if __name__ == "__main__":
    init_db()
    seed_db()
    print(f"Database initialized at {DB_PATH}")

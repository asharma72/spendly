# Step 1 — Database Setup Implementation Plan

## Context

Spendly's `database/db.py` is currently just a comment scaffold again (`get_db()`/`init_db()`/`seed_db()` unimplemented) — this repo is a step-by-step learning project, and a prior implementation of this file was deliberately reverted so the exercise could be redone. `.claude/specs/01-database-setup.md` specifies the data-layer foundation that every future step (auth, profile, expense CRUD) depends on. This plan implements that spec exactly, resolving its one ambiguity (DB filename) using existing repo evidence.

**Current-state flag:** `app.py` on disk still has the import (`from database.db import get_db, init_db, seed_db`) and the `with app.app_context(): init_db(); seed_db()` startup block from the earlier attempt, but `database/db.py` no longer defines those functions — so `app.py` will currently raise `ImportError` if run as-is. The plan below re-implements `database/db.py` to match what `app.py` already expects, which resolves this without needing to touch `app.py` again (its existing wiring already matches the target below).

## Decisions

- **DB filename: `spendly.db`** (superseded 2026-09-04: originally planned as `expense_tracker.db` since `.gitignore` already listed that name, but the spec explicitly allows either name, and the user asked to switch to `spendly.db` to match the app's branding. `.gitignore` was updated accordingly.)
- **`created_at` uses a SQL-level default** (`DEFAULT (datetime('now'))`, UTC) rather than a Python-side timestamp, matching the spec's literal schema wording. Fine for a teaching project.
- **Seed dates are computed relative to `date.today()`** at seed time (not hardcoded), so the seed data never goes stale. Anchored to day-of-month offsets `1, 3, 6, 9, 12, 15, 18, 21`, each clamped to `min(offset_date, today)` so no expense is ever dated in the future.

## Files to change

### `database/db.py` — full implementation

```python
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
```

Notes:
- `PRAGMA foreign_keys = ON` is set per-connection (SQLite doesn't persist it), so every `get_db()` call re-issues it — satisfies "enable on every connection."
- Duplicate-prevention check is table-wide (`COUNT(*) FROM users`), matching the spec's literal "already contains data" wording; the `UNIQUE` constraint on `email` is the backstop.
- All 7 required categories appear at least once across the 8 rows (Food appears twice).

### `app.py` — already matches target, no change needed

`app.py` on disk already contains:
```python
from flask import Flask, render_template

from database.db import get_db, init_db, seed_db

app = Flask(__name__)
```
and, right before `if __name__ == "__main__":`:
```python
with app.app_context():
    init_db()
    seed_db()


if __name__ == "__main__":
    app.run(debug=True, port=5001)
```
This is exactly what the spec calls for ("Import `get_db`, `init_db`, `seed_db`"; "Call `init_db()` and `seed_db()` inside `app.app_context()` on startup"). Once `database/db.py` defines these three functions again, `app.py` will import and run without further edits.

No other files change. No new dependencies (`sqlite3` stdlib, `werkzeug.security` already installed).

## Verification

1. Delete any existing `expense_tracker.db` in the project root.
2. Run `python app.py` — should start cleanly with no traceback; `expense_tracker.db` should now exist in the project root.
3. Inspect via a quick script:
   ```
   python -c "
   import sqlite3
   conn = sqlite3.connect('expense_tracker.db'); conn.row_factory = sqlite3.Row
   print(conn.execute('SELECT name FROM sqlite_master WHERE type=\"table\"').fetchall())
   print(conn.execute('SELECT id, name, email FROM users').fetchall())
   for r in conn.execute('SELECT category, amount, date, description FROM expenses ORDER BY date'):
       print(dict(r))
   "
   ```
   Confirm 2 tables, 1 demo user (hashed password, not plaintext), 8 expenses across all 7 categories, dates in `YYYY-MM-DD` within the current month and not in the future.
4. Re-run `python app.py` (or call `seed_db()` again) — user/expense counts must stay at 1 and 8 (no duplicates).
5. Confirm UNIQUE constraint: inserting a second user with `demo@spendly.com` must raise `sqlite3.IntegrityError`.
6. Confirm FK enforcement: inserting an expense with a nonexistent `user_id` must raise `sqlite3.IntegrityError` (if it silently succeeds, `PRAGMA foreign_keys = ON` isn't taking effect — recheck `get_db()`).
7. Hit existing routes (`/`, `/register`, `/login`, `/terms`, `/privacy`) to confirm no regression — Step 1 doesn't touch route behavior.

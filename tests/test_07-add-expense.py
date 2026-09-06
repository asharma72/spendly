"""
Tests for spec 07 — Add Expense.

Spec under test: .claude/specs/07-add-expense.md

Scope (per spec):
- GET /expenses/add renders the add-expense form for a logged-in user,
  pre-filled with today's date; unauthenticated access redirects to
  /login.
- POST /expenses/add validates form input (amount, category, date,
  description) and, on success, inserts a new row into `expenses` for
  the current session user and redirects to /profile.
- On validation failure, the form is re-rendered with an `error`
  message and the submitted values repopulated (register/login
  pattern) — no row is inserted.
- `amount` must be validated server-side as a positive number (reject
  missing/zero/negative/non-numeric).
- `category` must be validated against the fixed list (Food,
  Transport, Bills, Health, Entertainment, Shopping, Other) — anything
  else is rejected.
- `date` must be a loosely-validated YYYY-MM-DD string; per the spec,
  an invalid/missing date must never crash the app (no 500) — it may
  either fall back to today's date or be rejected with an error, as
  long as behavior is internally consistent. These tests accept either
  documented outcome and assert consistency (redirect => row inserted
  with today's date; re-render => no row inserted).
- `description` is optional — omitted or empty is fine.
- The nav shows an "Add Expense" link (via url_for) when logged in.

These tests interact with the app exclusively through the Flask test
client (black-box, HTTP-level), with direct sqlite reads (via
`database.db.get_db`) used only to assert DB side effects of a POST —
never to call `add_expense` or any route/business logic directly.

DB isolation strategy: `database/db.py` stores its sqlite path in a
module-level `DB_PATH` global (no Flask `app.config['DATABASE']` hook
exists in this codebase), and `app.py` runs `init_db()` / `seed_db()`
as top-level side effects at import time. To get a fresh, isolated
database per test we:
  1. monkeypatch `database.db.DB_PATH` to a unique temp file, and
     monkeypatch `database.db.seed_db` to a no-op (so the demo/seed
     data never pollutes these tests' expectations), BEFORE
     importing/reloading `app`;
  2. `importlib.reload(app)` so its module-level `init_db()` /
     `seed_db()` calls (and its `from database.db import ...` bindings)
     re-run against the freshly patched DB_PATH.
"""

import importlib
import os
import sys
from datetime import date

import pytest
from flask import url_for

# Ensure the project root (parent of tests/) is importable as `app` /
# `database.db` regardless of how `pytest` is invoked or what the
# current working directory is (there is no conftest.py / pyproject.toml
# / pytest.ini in this repo establishing that on sys.path otherwise).
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


# ------------------------------------------------------------------ #
# Spec-derived constants                                              #
# ------------------------------------------------------------------ #
# Fixed category list, per the spec text (not read from app.py).
CATEGORIES = [
    "Food", "Transport", "Bills", "Health",
    "Entertainment", "Shopping", "Other",
]


def _valid_form(**overrides):
    """A baseline valid add-expense form submission; callers override
    individual fields to build validation-failure scenarios."""
    data = {
        "amount": "42.50",
        "category": "Food",
        "date": "2026-05-01",
        "description": "Lunch with team",
    }
    data.update(overrides)
    return data


def _expense_rows_for_user(db_module, user_id):
    conn = db_module.get_db()
    rows = conn.execute(
        "SELECT id, amount, category, date, description "
        "FROM expenses WHERE user_id = ? ORDER BY id",
        (user_id,),
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def _all_expense_count(db_module):
    conn = db_module.get_db()
    row = conn.execute("SELECT COUNT(*) AS count FROM expenses").fetchone()
    conn.close()
    return row["count"]


def _currency(amount):
    return f"₹{amount:.2f}".encode("utf-8")


# ------------------------------------------------------------------ #
# Fixtures                                                             #
# ------------------------------------------------------------------ #

@pytest.fixture
def db_module(tmp_path, monkeypatch):
    """The database.db module, patched to use an isolated temp sqlite
    file and a no-op seed_db (so demo/seed data never mixes with these
    tests' expectations)."""
    import database.db as _db_module

    db_path = str(tmp_path / "test_spendly.db")
    monkeypatch.setattr(_db_module, "DB_PATH", db_path)
    monkeypatch.setattr(_db_module, "seed_db", lambda: None)
    return _db_module


@pytest.fixture
def app(db_module):
    """Reload app.py against the patched database.db so its
    module-level init_db()/seed_db() side effects run against the
    isolated temp DB, and so app.py's `from database.db import ...`
    names are rebound to the patched module."""
    import app as app_module

    importlib.reload(app_module)
    app_module.app.config.update({
        "TESTING": True,
        "SECRET_KEY": "test-secret",
    })
    yield app_module.app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def urls(app):
    with app.test_request_context():
        return {
            "register": url_for("register"),
            "login": url_for("login"),
            "profile": url_for("profile"),
            "add_expense": url_for("add_expense"),
        }


@pytest.fixture
def auth_client(app, client, urls, db_module):
    """A logged-in test client with no pre-existing expenses.
    Registration also logs the user in (app.py sets session['user_id']
    during /register), so no separate /login call is required."""
    email = "addexpense@example.com"
    client.post(
        urls["register"],
        data={
            "name": "Add Expense Tester",
            "email": email,
            "password": "testpass123",
            "confirm_password": "testpass123",
        },
    )
    user_row = db_module.get_user_by_email(email)
    assert user_row is not None, "registration fixture failed to create a user"
    return client, user_row["id"]


# ------------------------------------------------------------------ #
# Auth guard                                                           #
# ------------------------------------------------------------------ #

class TestAuthGuard:
    def test_get_add_expense_without_session_redirects_to_login(self, client, urls):
        response = client.get(urls["add_expense"])
        assert response.status_code == 302, "Unauthenticated GET /expenses/add should redirect"
        assert urls["login"] in response.headers["Location"], (
            "Unauthenticated GET /expenses/add should redirect to /login"
        )

    def test_post_add_expense_without_session_redirects_to_login_and_does_not_insert(
        self, client, urls, db_module
    ):
        response = client.post(urls["add_expense"], data=_valid_form())
        assert response.status_code == 302, "Unauthenticated POST /expenses/add should redirect"
        assert urls["login"] in response.headers["Location"], (
            "Unauthenticated POST /expenses/add should redirect to /login"
        )
        assert _all_expense_count(db_module) == 0, (
            "An unauthenticated POST must never create an expense row"
        )


# ------------------------------------------------------------------ #
# GET /expenses/add — form rendering                                   #
# ------------------------------------------------------------------ #

class TestGetForm:
    def test_get_form_while_logged_in_returns_200_prefilled_with_today(self, auth_client, urls):
        client, _ = auth_client
        response = client.get(urls["add_expense"])

        assert response.status_code == 200
        today_str = date.today().isoformat()
        assert today_str.encode() in response.data, (
            "Expected the date field to be pre-filled with today's date"
        )

    def test_get_form_lists_the_fixed_category_options(self, auth_client, urls):
        client, _ = auth_client
        response = client.get(urls["add_expense"])

        assert response.status_code == 200
        for category in CATEGORIES:
            assert category.encode() in response.data, (
                f"Expected fixed category {category!r} to appear in the form"
            )

    def test_get_form_posts_to_add_expense_url(self, auth_client, urls):
        client, _ = auth_client
        response = client.get(urls["add_expense"])

        assert response.status_code == 200
        action = f'action="{urls["add_expense"]}"'.encode()
        assert action in response.data, (
            "Expected the form action to use url_for('add_expense'), not a hardcoded URL"
        )


# ------------------------------------------------------------------ #
# Happy path: valid submit                                             #
# ------------------------------------------------------------------ #

class TestHappyPath:
    def test_valid_submit_redirects_to_profile(self, auth_client, urls):
        client, _ = auth_client
        response = client.post(urls["add_expense"], data=_valid_form())

        assert response.status_code == 302, "A valid submit should redirect, not re-render"
        assert urls["profile"] in response.headers["Location"], (
            "A valid submit should redirect to /profile"
        )

    def test_valid_submit_persists_expense_with_correct_values(
        self, auth_client, urls, db_module
    ):
        client, user_id = auth_client
        client.post(urls["add_expense"], data=_valid_form())

        rows = _expense_rows_for_user(db_module, user_id)
        assert len(rows) == 1, "Expected exactly one expense row to be created"
        row = rows[0]
        assert row["amount"] == pytest.approx(42.50)
        assert row["category"] == "Food"
        assert row["date"] == "2026-05-01"
        assert row["description"] == "Lunch with team"

    def test_valid_submit_reflected_in_profile_stats_and_history(self, auth_client, urls):
        client, _ = auth_client
        client.post(urls["add_expense"], data=_valid_form())

        response = client.get(urls["profile"])
        assert response.status_code == 200
        assert b"Lunch with team" in response.data, (
            "Expected the new expense to appear in the transaction history"
        )
        assert _currency(42.50) in response.data, (
            "Expected the new expense's amount to be reflected in profile stats"
        )
        assert b"Food" in response.data, (
            "Expected the new expense's category to appear in the category breakdown"
        )


# ------------------------------------------------------------------ #
# Validation: amount                                                    #
# ------------------------------------------------------------------ #

class TestAmountValidation:
    @pytest.mark.parametrize(
        "amount_raw",
        ["", "0", "-5", "-0.01", "abc"],
        ids=["missing", "zero", "negative", "negative_decimal", "non_numeric"],
    )
    def test_invalid_amount_rerenders_form_without_inserting(
        self, auth_client, urls, db_module, amount_raw
    ):
        client, user_id = auth_client
        data = _valid_form(amount=amount_raw)
        response = client.post(urls["add_expense"], data=data)

        assert response.status_code == 200, (
            f"Invalid amount {amount_raw!r} should re-render the form, not redirect"
        )
        assert b"error" in response.data.lower(), (
            "Expected an error message to be shown for an invalid amount"
        )
        assert _expense_rows_for_user(db_module, user_id) == [], (
            "An invalid amount must not insert a row"
        )
        assert data["description"].encode() in response.data, (
            "Expected submitted values (e.g. description) to be repopulated on error"
        )


# ------------------------------------------------------------------ #
# Validation: category                                                  #
# ------------------------------------------------------------------ #

class TestCategoryValidation:
    @pytest.mark.parametrize(
        "category",
        ["Groceries", "", "Miscellaneous", "Bills; DROP TABLE users;--"],
        ids=["not_in_list", "missing", "another_unlisted_value", "sql_injection_attempt"],
    )
    def test_invalid_category_rerenders_form_without_inserting(
        self, auth_client, urls, db_module, category
    ):
        client, user_id = auth_client
        data = _valid_form(category=category)
        response = client.post(urls["add_expense"], data=data)

        assert response.status_code == 200, (
            f"Category {category!r} outside the fixed list should re-render the form"
        )
        assert b"error" in response.data.lower(), (
            "Expected an error message to be shown for an invalid category"
        )
        assert _expense_rows_for_user(db_module, user_id) == [], (
            "A category outside the fixed list must not insert a row"
        )

        # Safety check: a SQL-injection-style category value must be
        # rejected as "not a valid category", not executed as SQL —
        # the users table (and this user) must still exist.
        user_row = db_module.get_user_by_id(user_id)
        assert user_row is not None, (
            "Users table must be intact after a SQL-injection-style category value "
            "(parameterized queries only)"
        )


# ------------------------------------------------------------------ #
# Date handling                                                        #
# ------------------------------------------------------------------ #

class TestDateHandling:
    """Per spec, an invalid/missing date must never crash the app.
    The spec allows either of two consistent behaviors: fall back to
    today's date and still insert, or reject with an error and insert
    nothing. These tests accept either outcome but verify internal
    consistency (no 500, and the DB state matches the chosen path)."""

    def test_missing_date_does_not_crash(self, auth_client, urls, db_module):
        client, user_id = auth_client
        data = _valid_form(date="")
        response = client.post(urls["add_expense"], data=data)

        assert response.status_code != 500, "A missing date must not cause a server error"
        assert response.status_code in (200, 302), (
            f"Unexpected status code {response.status_code} for a missing date"
        )

        rows = _expense_rows_for_user(db_module, user_id)
        if response.status_code == 302:
            assert len(rows) == 1, "A redirect implies the expense was inserted"
            assert rows[0]["date"] == date.today().isoformat(), (
                "If a missing date is accepted, it must fall back to today's date"
            )
        else:
            assert rows == [], (
                "If a missing date is rejected, no row should have been inserted"
            )

    def test_invalid_date_string_does_not_crash(self, auth_client, urls, db_module):
        client, user_id = auth_client
        data = _valid_form(date="not-a-real-date")
        response = client.post(urls["add_expense"], data=data)

        assert response.status_code != 500, "An invalid date must not cause a server error"
        assert response.status_code in (200, 302), (
            f"Unexpected status code {response.status_code} for an invalid date"
        )

        rows = _expense_rows_for_user(db_module, user_id)
        if response.status_code == 302:
            assert len(rows) == 1, "A redirect implies the expense was inserted"
            assert rows[0]["date"] == date.today().isoformat(), (
                "If an invalid date is accepted, it must fall back to today's date"
            )
        else:
            assert rows == [], (
                "If an invalid date is rejected, no row should have been inserted"
            )


# ------------------------------------------------------------------ #
# Optional description                                                  #
# ------------------------------------------------------------------ #

class TestOptionalDescription:
    def test_submit_without_description_field_succeeds(self, auth_client, urls, db_module):
        client, user_id = auth_client
        data = _valid_form()
        del data["description"]

        response = client.post(urls["add_expense"], data=data)

        assert response.status_code == 302, "Omitting description should still succeed"
        assert urls["profile"] in response.headers["Location"]
        rows = _expense_rows_for_user(db_module, user_id)
        assert len(rows) == 1
        assert rows[0]["amount"] == pytest.approx(42.50)
        assert rows[0]["category"] == "Food"

    def test_submit_with_empty_description_succeeds(self, auth_client, urls, db_module):
        client, user_id = auth_client
        data = _valid_form(description="")

        response = client.post(urls["add_expense"], data=data)

        assert response.status_code == 302, "An empty description should still succeed"
        assert urls["profile"] in response.headers["Location"]
        rows = _expense_rows_for_user(db_module, user_id)
        assert len(rows) == 1


# ------------------------------------------------------------------ #
# Nav link (Definition of Done)                                        #
# ------------------------------------------------------------------ #

class TestNavLink:
    def test_nav_shows_add_expense_link_when_logged_in(self, auth_client, urls):
        client, _ = auth_client
        response = client.get(urls["profile"])

        assert response.status_code == 200
        href = f'href="{urls["add_expense"]}"'.encode()
        assert href in response.data, (
            "Expected the nav to include an Add Expense link built with url_for()"
        )

"""
Tests for spec 08 — Edit Expense.

Spec under test: .claude/specs/08-edit-expense.md

Scope (per spec):
- GET /expenses/<id>/edit renders an edit form pre-filled with the
  expense's current amount, category, date, and description, for a
  logged-in user who owns that expense. Unauthenticated access
  redirects to /login.
- Ownership is enforced in the SQL lookup itself (`WHERE id = ? AND
  user_id = ?`): a nonexistent id, or an id belonging to a different
  user, must abort(404) rather than leak whether the id exists or
  render someone else's data. Same guard applies to POST.
- POST /expenses/<id>/edit validates form input (amount, category,
  date, description) the same way add_expense does, and on success
  UPDATEs the matching row (never inserts a new one) and redirects to
  /profile.
- On validation failure, the form is re-rendered with an `error`
  message and the *submitted* (not original) values repopulated — same
  UX pattern as add_expense/register/login — and the underlying row is
  left untouched.
- `amount` must be validated server-side as a positive number (reject
  missing/zero/negative/non-numeric).
- `category` must be validated against the fixed list (Food,
  Transport, Bills, Health, Entertainment, Shopping, Other) — anything
  else is rejected.
- `date` must be a loosely-validated YYYY-MM-DD string. Unlike
  add_expense (where the spec allows either fallback-to-today or
  reject), this spec is explicit: an invalid/missing date falls back
  to today's date rather than blocking the submission or crashing.
- `description` is optional — omitted or empty is fine, and clears any
  previous description.
- The profile page's "Recent transactions" table shows an "Edit" link
  per row (built with url_for) pointing at that row's edit page.

These tests interact with the app exclusively through the Flask test
client (black-box, HTTP-level). Direct sqlite reads (via
`database.db.get_db`) are used only to assert DB side effects of a
GET/POST — never to call `edit_expense` or any route/business logic
directly. `database.db.create_expense` (an existing, spec-documented
DB helper, not the code under test) is used only to *seed* an expense
to edit in test setup — this mirrors how add_expense's own tests seed
via the public HTTP route, but here a direct DB helper call is used so
each test can start from a precisely known row (id, amount, category,
date, description) without depending on add_expense's behavior.

DB isolation strategy: identical to test_07-add-expense.py. `database/
db.py` stores its sqlite path in a module-level `DB_PATH` global, and
`app.py` runs `init_db()` / `seed_db()` as top-level side effects at
import time. To get a fresh, isolated database per test we:
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
# current working directory is.
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


# ------------------------------------------------------------------ #
# Spec-derived constants                                              #
# ------------------------------------------------------------------ #
CATEGORIES = [
    "Food", "Transport", "Bills", "Health",
    "Entertainment", "Shopping", "Other",
]


def _valid_edit_form(**overrides):
    """A baseline valid edit-expense form submission; callers override
    individual fields to build validation-failure scenarios."""
    data = {
        "amount": "150.25",
        "category": "Transport",
        "date": "2026-06-10",
        "description": "Updated to transport",
    }
    data.update(overrides)
    return data


def _get_expense_row(db_module, expense_id):
    conn = db_module.get_db()
    row = conn.execute(
        "SELECT id, user_id, amount, category, date, description "
        "FROM expenses WHERE id = ?",
        (expense_id,),
    ).fetchone()
    conn.close()
    return dict(row) if row is not None else None


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


def _seed_expense(
    db_module,
    user_id,
    amount=99.99,
    category="Bills",
    expense_date="2026-03-15",
    description="Original description",
):
    """Seed one expense row for `user_id` via the existing create_expense
    DB helper (not the code under test) and return its known fields."""
    expense_id = db_module.create_expense(
        user_id, amount, category, expense_date, description
    )
    return {
        "id": expense_id,
        "amount": amount,
        "category": category,
        "date": expense_date,
        "description": description,
    }


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
def urls(app):
    with app.test_request_context():
        return {
            "register": url_for("register"),
            "login": url_for("login"),
            "profile": url_for("profile"),
            "add_expense": url_for("add_expense"),
        }


@pytest.fixture
def edit_url(app):
    """Callable: expense id -> its url_for('edit_expense', id=id) URL.
    Kept as a callable (rather than a precomputed dict) since the id is
    only known once an expense has been seeded/created within a test."""
    def _build(expense_id):
        with app.test_request_context():
            return url_for("edit_expense", id=expense_id)
    return _build


def _register_and_login(client, urls, db_module, email, name="Edit Expense Tester"):
    """Register+login a fresh user on the given test client and return
    their user id. Registration also logs the user in (app.py sets
    session['user_id'] during /register)."""
    client.post(
        urls["register"],
        data={
            "name": name,
            "email": email,
            "password": "testpass123",
            "confirm_password": "testpass123",
        },
    )
    user_row = db_module.get_user_by_email(email)
    assert user_row is not None, "registration fixture failed to create a user"
    return user_row["id"]


@pytest.fixture
def auth_client(app, urls, db_module):
    """A logged-in test client with no pre-existing expenses."""
    client = app.test_client()
    user_id = _register_and_login(
        client, urls, db_module, "editexpense@example.com"
    )
    return client, user_id


@pytest.fixture
def other_auth_client(app, urls, db_module):
    """A second, independent logged-in test client/user — used to
    verify ownership enforcement. A distinct app.test_client()
    instance carries its own cookie jar/session."""
    client = app.test_client()
    user_id = _register_and_login(
        client, urls, db_module, "otheruser@example.com", name="Other User"
    )
    return client, user_id


def _currency(amount):
    return f"₹{amount:.2f}".encode("utf-8")


# ------------------------------------------------------------------ #
# Auth guard                                                           #
# ------------------------------------------------------------------ #

class TestAuthGuard:
    def test_get_edit_without_session_redirects_to_login(
        self, app, urls, edit_url, auth_client, db_module
    ):
        client, user_id = auth_client
        expense = _seed_expense(db_module, user_id)

        # A fresh, unauthenticated client.
        anon_client = app.test_client()
        response = anon_client.get(edit_url(expense["id"]))

        assert response.status_code == 302, "Unauthenticated GET /expenses/<id>/edit should redirect"
        assert urls["login"] in response.headers["Location"], (
            "Unauthenticated GET /expenses/<id>/edit should redirect to /login"
        )

    def test_post_edit_without_session_redirects_to_login_and_does_not_update(
        self, app, urls, edit_url, auth_client, db_module
    ):
        client, user_id = auth_client
        expense = _seed_expense(db_module, user_id)

        anon_client = app.test_client()
        response = anon_client.post(
            edit_url(expense["id"]), data=_valid_edit_form()
        )

        assert response.status_code == 302, "Unauthenticated POST /expenses/<id>/edit should redirect"
        assert urls["login"] in response.headers["Location"], (
            "Unauthenticated POST /expenses/<id>/edit should redirect to /login"
        )

        row = _get_expense_row(db_module, expense["id"])
        assert row["amount"] == pytest.approx(expense["amount"]), (
            "An unauthenticated POST must never modify an expense row"
        )
        assert row["category"] == expense["category"]


# ------------------------------------------------------------------ #
# Ownership guard                                                       #
# ------------------------------------------------------------------ #

class TestOwnershipGuard:
    def test_get_nonexistent_expense_returns_404(self, auth_client, edit_url):
        client, _ = auth_client
        response = client.get(edit_url(999999))
        assert response.status_code == 404, (
            "GET on a nonexistent expense id should 404, not crash or render an empty form"
        )

    def test_post_nonexistent_expense_returns_404(self, auth_client, edit_url):
        client, _ = auth_client
        response = client.post(edit_url(999999), data=_valid_edit_form())
        assert response.status_code == 404

    def test_get_another_users_expense_returns_404(
        self, auth_client, other_auth_client, edit_url, db_module
    ):
        client, user_id = auth_client
        other_client, other_user_id = other_auth_client

        owned_by_other = _seed_expense(db_module, other_user_id, description="Not yours")

        response = client.get(edit_url(owned_by_other["id"]))
        assert response.status_code == 404, (
            "GET on another user's expense id must 404, not leak that user's data"
        )
        assert b"Not yours" not in response.data

    def test_post_another_users_expense_returns_404_and_does_not_modify_it(
        self, auth_client, other_auth_client, edit_url, db_module
    ):
        client, user_id = auth_client
        other_client, other_user_id = other_auth_client

        owned_by_other = _seed_expense(db_module, other_user_id)

        response = client.post(
            edit_url(owned_by_other["id"]), data=_valid_edit_form()
        )
        assert response.status_code == 404, (
            "POST on another user's expense id must 404 rather than update it"
        )

        row = _get_expense_row(db_module, owned_by_other["id"])
        assert row["amount"] == pytest.approx(owned_by_other["amount"]), (
            "A crafted cross-user POST must never modify another user's row"
        )
        assert row["category"] == owned_by_other["category"]
        assert row["date"] == owned_by_other["date"]
        assert row["description"] == owned_by_other["description"]
        assert row["user_id"] == other_user_id, "Ownership of the row must not change"


# ------------------------------------------------------------------ #
# GET /expenses/<id>/edit — form rendering                            #
# ------------------------------------------------------------------ #

class TestGetForm:
    def test_get_form_for_own_expense_returns_200_prefilled(
        self, auth_client, edit_url, db_module
    ):
        client, user_id = auth_client
        expense = _seed_expense(
            db_module,
            user_id,
            amount=99.99,
            category="Bills",
            expense_date="2026-03-15",
            description="Original description",
        )

        response = client.get(edit_url(expense["id"]))

        assert response.status_code == 200
        assert b"99.99" in response.data, "Expected the current amount to pre-fill the form"
        assert b"Bills" in response.data, "Expected the current category to pre-fill the form"
        assert b"2026-03-15" in response.data, "Expected the current date to pre-fill the form"
        assert b"Original description" in response.data, (
            "Expected the current description to pre-fill the form"
        )

    def test_get_form_posts_to_edit_expense_url_for_this_id(
        self, auth_client, edit_url, db_module
    ):
        client, user_id = auth_client
        expense = _seed_expense(db_module, user_id)

        response = client.get(edit_url(expense["id"]))

        assert response.status_code == 200
        action = f'action="{edit_url(expense["id"])}"'.encode()
        assert action in response.data, (
            "Expected the form action to use url_for('edit_expense', id=expense.id), "
            "not a hardcoded URL"
        )

    def test_get_form_lists_the_fixed_category_options(
        self, auth_client, edit_url, db_module
    ):
        client, user_id = auth_client
        expense = _seed_expense(db_module, user_id)

        response = client.get(edit_url(expense["id"]))

        assert response.status_code == 200
        for category in CATEGORIES:
            assert category.encode() in response.data, (
                f"Expected fixed category {category!r} to appear in the form"
            )


# ------------------------------------------------------------------ #
# Happy path: valid submit                                             #
# ------------------------------------------------------------------ #

class TestHappyPath:
    def test_valid_submit_redirects_to_profile(self, auth_client, urls, edit_url, db_module):
        client, user_id = auth_client
        expense = _seed_expense(db_module, user_id)

        response = client.post(edit_url(expense["id"]), data=_valid_edit_form())

        assert response.status_code == 302, "A valid submit should redirect, not re-render"
        assert urls["profile"] in response.headers["Location"], (
            "A valid submit should redirect to /profile"
        )

    def test_valid_submit_updates_the_row_in_place(self, auth_client, edit_url, db_module):
        client, user_id = auth_client
        expense = _seed_expense(db_module, user_id)

        client.post(edit_url(expense["id"]), data=_valid_edit_form())

        row = _get_expense_row(db_module, expense["id"])
        assert row is not None, "The row must still exist after an update (not deleted)"
        assert row["id"] == expense["id"], "Editing must update the existing row, not create a new one"
        assert row["amount"] == pytest.approx(150.25)
        assert row["category"] == "Transport"
        assert row["date"] == "2026-06-10"
        assert row["description"] == "Updated to transport"

    def test_valid_submit_does_not_create_a_new_row(self, auth_client, edit_url, db_module):
        client, user_id = auth_client
        expense = _seed_expense(db_module, user_id)

        before_count = len(_expense_rows_for_user(db_module, user_id))
        client.post(edit_url(expense["id"]), data=_valid_edit_form())
        after_count = len(_expense_rows_for_user(db_module, user_id))

        assert before_count == 1
        assert after_count == 1, "Editing an expense must UPDATE, never INSERT a new row"

    def test_editing_one_expense_does_not_affect_another(
        self, auth_client, edit_url, db_module
    ):
        client, user_id = auth_client
        target = _seed_expense(
            db_module, user_id, amount=10.00, category="Food",
            expense_date="2026-01-01", description="Target expense",
        )
        untouched = _seed_expense(
            db_module, user_id, amount=20.00, category="Health",
            expense_date="2026-01-02", description="Untouched expense",
        )

        client.post(edit_url(target["id"]), data=_valid_edit_form())

        untouched_row = _get_expense_row(db_module, untouched["id"])
        assert untouched_row["amount"] == pytest.approx(20.00)
        assert untouched_row["category"] == "Health"
        assert untouched_row["date"] == "2026-01-02"
        assert untouched_row["description"] == "Untouched expense"

    def test_valid_submit_reflected_in_profile_transactions(
        self, auth_client, urls, edit_url, db_module
    ):
        client, user_id = auth_client
        expense = _seed_expense(
            db_module, user_id, amount=10.00, category="Food",
            expense_date="2026-01-01", description="Old description",
        )

        client.post(edit_url(expense["id"]), data=_valid_edit_form(
            description="New description after edit"
        ))

        response = client.get(urls["profile"])
        assert response.status_code == 200
        assert b"New description after edit" in response.data, (
            "Expected the updated description to appear in the transaction history"
        )
        assert b"Old description" not in response.data, (
            "The stale, pre-edit description must no longer be shown"
        )
        assert _currency(150.25) in response.data, (
            "Expected the updated amount to be reflected in profile stats"
        )

    def test_valid_submit_moves_category_totals(
        self, auth_client, urls, edit_url, db_module
    ):
        client, user_id = auth_client
        # Only expense for this user: originally Food, moved to Transport.
        expense = _seed_expense(
            db_module, user_id, amount=50.00, category="Food",
            expense_date="2026-01-01", description="Category move test",
        )

        client.post(edit_url(expense["id"]), data=_valid_edit_form(
            amount="50.00", category="Transport", description="Category move test"
        ))

        response = client.get(urls["profile"])
        assert response.status_code == 200
        assert b"Transport" in response.data, (
            "Expected the new category to appear in the category breakdown"
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
    def test_invalid_amount_rerenders_form_without_updating(
        self, auth_client, edit_url, db_module, amount_raw
    ):
        client, user_id = auth_client
        expense = _seed_expense(db_module, user_id)
        data = _valid_edit_form(amount=amount_raw)

        response = client.post(edit_url(expense["id"]), data=data)

        assert response.status_code == 200, (
            f"Invalid amount {amount_raw!r} should re-render the form, not redirect"
        )
        assert b"error" in response.data.lower(), (
            "Expected an error message to be shown for an invalid amount"
        )

        row = _get_expense_row(db_module, expense["id"])
        assert row["amount"] == pytest.approx(expense["amount"]), (
            "An invalid amount must not modify the row's amount"
        )
        assert row["category"] == expense["category"]
        assert row["date"] == expense["date"]
        assert row["description"] == expense["description"]

        assert data["description"].encode() in response.data, (
            "Expected submitted (not original) values to be repopulated on error"
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
    def test_invalid_category_rerenders_form_without_updating(
        self, auth_client, edit_url, db_module, category
    ):
        client, user_id = auth_client
        expense = _seed_expense(db_module, user_id)
        data = _valid_edit_form(category=category)

        response = client.post(edit_url(expense["id"]), data=data)

        assert response.status_code == 200, (
            f"Category {category!r} outside the fixed list should re-render the form"
        )
        assert b"error" in response.data.lower(), (
            "Expected an error message to be shown for an invalid category"
        )

        row = _get_expense_row(db_module, expense["id"])
        assert row["category"] == expense["category"], (
            "A category outside the fixed list must not modify the row"
        )
        assert row["amount"] == pytest.approx(expense["amount"])

        # Safety check: a SQL-injection-style category value must be
        # rejected as "not a valid category", not executed as SQL —
        # the users table (and this user, and the expense) must still
        # exist afterward.
        user_row = db_module.get_user_by_id(user_id)
        assert user_row is not None, (
            "Users table must be intact after a SQL-injection-style category value "
            "(parameterized queries only)"
        )
        assert _get_expense_row(db_module, expense["id"]) is not None, (
            "Expenses table must be intact after a SQL-injection-style category value"
        )


# ------------------------------------------------------------------ #
# Date handling                                                        #
# ------------------------------------------------------------------ #

class TestDateHandling:
    """Per spec (unlike add_expense's either/or), edit_expense's date
    handling is definitive: an invalid/missing date falls back to
    today's date rather than blocking the submission, and must never
    crash the app."""

    def test_missing_date_falls_back_to_today_and_still_updates(
        self, auth_client, urls, edit_url, db_module
    ):
        client, user_id = auth_client
        expense = _seed_expense(db_module, user_id)
        data = _valid_edit_form(date="")

        response = client.post(edit_url(expense["id"]), data=data)

        assert response.status_code == 302, (
            "A missing date must not block the submission — it should fall back to today"
        )
        assert urls["profile"] in response.headers["Location"]

        row = _get_expense_row(db_module, expense["id"])
        assert row["date"] == date.today().isoformat(), (
            "A missing date must fall back to today's date"
        )
        # Other validated fields from the same submission still apply.
        assert row["amount"] == pytest.approx(150.25)
        assert row["category"] == "Transport"

    def test_invalid_date_string_falls_back_to_today_and_does_not_crash(
        self, auth_client, urls, edit_url, db_module
    ):
        client, user_id = auth_client
        expense = _seed_expense(db_module, user_id)
        data = _valid_edit_form(date="not-a-real-date")

        response = client.post(edit_url(expense["id"]), data=data)

        assert response.status_code != 500, "An invalid date must not cause a server error"
        assert response.status_code == 302, (
            "An invalid date must fall back to today rather than reject the submission"
        )

        row = _get_expense_row(db_module, expense["id"])
        assert row["date"] == date.today().isoformat(), (
            "An invalid date string must fall back to today's date"
        )


# ------------------------------------------------------------------ #
# Optional description                                                  #
# ------------------------------------------------------------------ #

class TestOptionalDescription:
    def test_submit_without_description_field_succeeds_and_clears_it(
        self, auth_client, urls, edit_url, db_module
    ):
        client, user_id = auth_client
        expense = _seed_expense(db_module, user_id, description="Will be cleared")
        data = _valid_edit_form()
        del data["description"]

        response = client.post(edit_url(expense["id"]), data=data)

        assert response.status_code == 302, "Omitting description should still succeed"
        assert urls["profile"] in response.headers["Location"]

        row = _get_expense_row(db_module, expense["id"])
        assert not row["description"], (
            "Omitting description should clear/empty it, not error out"
        )
        assert row["amount"] == pytest.approx(150.25)
        assert row["category"] == "Transport"

    def test_submit_with_empty_description_succeeds_and_clears_it(
        self, auth_client, urls, edit_url, db_module
    ):
        client, user_id = auth_client
        expense = _seed_expense(db_module, user_id, description="Will be cleared")
        data = _valid_edit_form(description="")

        response = client.post(edit_url(expense["id"]), data=data)

        assert response.status_code == 302, "An empty description should still succeed"
        assert urls["profile"] in response.headers["Location"]

        row = _get_expense_row(db_module, expense["id"])
        assert not row["description"]


# ------------------------------------------------------------------ #
# Profile "Edit" link (Definition of Done)                             #
# ------------------------------------------------------------------ #

class TestProfileEditLink:
    def test_profile_transaction_row_has_edit_link_to_correct_expense(
        self, auth_client, urls, edit_url, db_module
    ):
        client, user_id = auth_client
        expense = _seed_expense(db_module, user_id, description="Linked expense")

        response = client.get(urls["profile"])

        assert response.status_code == 200
        href = f'href="{edit_url(expense["id"])}"'.encode()
        assert href in response.data, (
            "Expected an Edit link built with url_for('edit_expense', id=tx.id) "
            "for this transaction row"
        )

    def test_profile_shows_one_edit_link_per_transaction(
        self, auth_client, urls, edit_url, db_module
    ):
        client, user_id = auth_client
        first = _seed_expense(
            db_module, user_id, amount=5.00, category="Food",
            expense_date="2026-01-01", description="First",
        )
        second = _seed_expense(
            db_module, user_id, amount=6.00, category="Health",
            expense_date="2026-01-02", description="Second",
        )

        response = client.get(urls["profile"])

        assert response.status_code == 200
        assert f'href="{edit_url(first["id"])}"'.encode() in response.data
        assert f'href="{edit_url(second["id"])}"'.encode() in response.data

"""
Tests for spec 06 — Date Filter for Profile Page.

Spec under test: .claude/specs/06-date-filter-for-profile-page.md

Scope (per spec):
- GET /profile accepts optional `start_date` / `end_date` query args
  (YYYY-MM-DD) and scopes stats, transaction history, and category
  breakdown to that inclusive range.
- No query args -> unfiltered (all-time), unchanged from before.
- Only one of start_date/end_date set -> single-bound filter.
- Malformed/unparseable date strings are ignored (per-field), not a 500.
- start_date after end_date -> treated as no filter at all (never a
  silent zero-row result).
- Auth guard on /profile is unchanged (redirect to /login).

These tests interact with the app exclusively through the Flask test
client (black-box, HTTP-level) and a small amount of direct sqlite
seeding to set up known rows with fixed, deterministic dates. They do
not call `build_profile_summary` / `build_transaction_history` /
`build_category_breakdown` or any `database/db.py` helper directly.

DB isolation strategy: `database/db.py` stores its sqlite path in a
module-level `DB_PATH` global (no Flask `app.config['DATABASE']` hook
exists in this codebase), and `app.py` runs `init_db()` / `seed_db()`
as top-level side effects at import time. To get a fresh, isolated
database per test we:
  1. monkeypatch `database.db.DB_PATH` to a unique temp file, and
     monkeypatch `database.db.seed_db` to a no-op (so the demo/seed
     data with "today"-relative dates never pollutes our fixed-date
     fixtures), BEFORE importing/reloading `app`;
  2. `importlib.reload(app)` so its module-level `init_db()` /
     `seed_db()` calls (and its `from database.db import ...` bindings)
     re-run against the freshly patched DB_PATH.
"""

import importlib
import os
import sys

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
# Fixed, deterministic seed data                                      #
# ------------------------------------------------------------------ #
# (date, category, amount, description)
EXPENSES = [
    ("2026-01-05", "Food", 20.00, "Jan grocery"),
    ("2026-02-10", "Transport", 40.00, "Feb metro"),
    ("2026-02-20", "Food", 15.00, "Feb dinner"),
    ("2026-03-01", "Bills", 100.00, "March electricity"),
    ("2026-04-15", "Entertainment", 30.00, "April movie"),
]
ALL_TOTAL = sum(amount for _, _, amount, _ in EXPENSES)  # 205.00
ALL_DESCRIPTIONS = [desc for _, _, _, desc in EXPENSES]


def _insert_expense(db_module, user_id, date_str, category, amount, description):
    conn = db_module.get_db()
    conn.execute(
        "INSERT INTO expenses (user_id, amount, category, date, description) "
        "VALUES (?, ?, ?, ?, ?)",
        (user_id, amount, category, date_str, description),
    )
    conn.commit()
    conn.close()


def _currency(amount):
    return f"₹{amount:.2f}".encode("utf-8")


# ------------------------------------------------------------------ #
# Fixtures                                                             #
# ------------------------------------------------------------------ #

@pytest.fixture
def db_module(tmp_path, monkeypatch):
    """The database.db module, patched to use an isolated temp sqlite
    file and a no-op seed_db (so fixed-date test fixtures aren't mixed
    with the "today"-relative demo seed data)."""
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
        }


@pytest.fixture
def seeded_client(app, client, urls, db_module):
    """A logged-in test client whose user owns the fixed EXPENSES
    dataset above. Registration also logs the user in (app.py sets
    session['user_id'] during /register), so no separate /login call
    is required."""
    email = "filtertest@example.com"
    client.post(
        urls["register"],
        data={
            "name": "Filter Test",
            "email": email,
            "password": "testpass123",
            "confirm_password": "testpass123",
        },
    )
    user_row = db_module.get_user_by_email(email)
    assert user_row is not None, "registration fixture failed to create a user"
    user_id = user_row["id"]

    for date_str, category, amount, description in EXPENSES:
        _insert_expense(db_module, user_id, date_str, category, amount, description)

    return client, user_id


# ------------------------------------------------------------------ #
# Auth guard                                                           #
# ------------------------------------------------------------------ #

class TestAuthGuard:
    def test_profile_without_session_redirects_to_login(self, client, urls):
        response = client.get(urls["profile"])
        assert response.status_code == 302, "Unauthenticated /profile should redirect"
        assert urls["login"] in response.headers["Location"], (
            "Unauthenticated /profile should redirect to /login"
        )

    def test_profile_with_date_params_without_session_redirects_to_login(self, client, urls):
        response = client.get(
            urls["profile"],
            query_string={"start_date": "2026-01-01", "end_date": "2026-03-31"},
        )
        assert response.status_code == 302, (
            "Unauthenticated /profile with date filters should still redirect"
        )
        assert urls["login"] in response.headers["Location"]


# ------------------------------------------------------------------ #
# No filter -> unfiltered (all-time), unchanged from before            #
# ------------------------------------------------------------------ #

class TestNoFilter:
    def test_no_query_args_returns_all_expenses(self, seeded_client, urls):
        client, _ = seeded_client
        response = client.get(urls["profile"])

        assert response.status_code == 200
        for description in ALL_DESCRIPTIONS:
            assert description.encode() in response.data, (
                f"Expected unfiltered profile page to include {description!r}"
            )
        assert _currency(ALL_TOTAL) in response.data, (
            "Expected unfiltered total_spent to be the sum of all seeded expenses"
        )


# ------------------------------------------------------------------ #
# Happy path: inclusive start_date/end_date range                      #
# ------------------------------------------------------------------ #

class TestDateRangeFilterHappyPath:
    def test_range_scopes_transactions_and_stats(self, seeded_client, urls):
        client, _ = seeded_client
        response = client.get(
            urls["profile"],
            query_string={"start_date": "2026-02-01", "end_date": "2026-02-28"},
        )

        assert response.status_code == 200

        # In-range rows must appear.
        assert b"Feb metro" in response.data
        assert b"Feb dinner" in response.data

        # Out-of-range rows must not appear.
        assert b"Jan grocery" not in response.data
        assert b"March electricity" not in response.data
        assert b"April movie" not in response.data

        # Stats scoped to just the in-range rows (40.00 + 15.00).
        assert _currency(55.00) in response.data

    def test_range_scopes_category_breakdown(self, seeded_client, urls):
        client, _ = seeded_client
        response = client.get(
            urls["profile"],
            query_string={"start_date": "2026-02-01", "end_date": "2026-02-28"},
        )

        assert response.status_code == 200
        # Categories present within the range.
        assert b"Transport" in response.data
        assert b"Food" in response.data
        # Categories that only have expenses outside the range should
        # not show up in the (now-scoped) breakdown.
        assert b"Bills" not in response.data
        assert b"Entertainment" not in response.data

    def test_boundary_dates_are_inclusive(self, seeded_client, urls):
        """start_date == end_date == an expense's own date must include
        that expense (inclusive range), per spec."""
        client, _ = seeded_client
        response = client.get(
            urls["profile"],
            query_string={"start_date": "2026-02-10", "end_date": "2026-02-10"},
        )

        assert response.status_code == 200
        assert b"Feb metro" in response.data, "Exact boundary date should be included"
        for description in ("Jan grocery", "Feb dinner", "March electricity", "April movie"):
            assert description.encode() not in response.data
        assert _currency(40.00) in response.data


# ------------------------------------------------------------------ #
# Single-bound filters                                                 #
# ------------------------------------------------------------------ #

class TestSingleBoundFilter:
    def test_only_start_date_set(self, seeded_client, urls):
        client, _ = seeded_client
        response = client.get(
            urls["profile"],
            query_string={"start_date": "2026-03-01"},
        )

        assert response.status_code == 200
        assert b"March electricity" in response.data
        assert b"April movie" in response.data
        assert b"Jan grocery" not in response.data
        assert b"Feb metro" not in response.data
        assert b"Feb dinner" not in response.data
        assert _currency(130.00) in response.data  # 100.00 + 30.00

    def test_only_end_date_set(self, seeded_client, urls):
        client, _ = seeded_client
        response = client.get(
            urls["profile"],
            query_string={"end_date": "2026-02-10"},
        )

        assert response.status_code == 200
        assert b"Jan grocery" in response.data
        assert b"Feb metro" in response.data
        assert b"Feb dinner" not in response.data
        assert b"March electricity" not in response.data
        assert b"April movie" not in response.data
        assert _currency(60.00) in response.data  # 20.00 + 40.00


# ------------------------------------------------------------------ #
# start_date after end_date -> treated as no filter at all             #
# ------------------------------------------------------------------ #

class TestStartAfterEndDate:
    def test_start_after_end_behaves_as_unfiltered(self, seeded_client, urls):
        client, _ = seeded_client
        response = client.get(
            urls["profile"],
            query_string={"start_date": "2026-04-15", "end_date": "2026-01-05"},
        )

        assert response.status_code == 200, "start > end must not crash the page"
        for description in ALL_DESCRIPTIONS:
            assert description.encode() in response.data, (
                "start_date after end_date must be treated as no filter, "
                f"but {description!r} was missing"
            )
        assert _currency(ALL_TOTAL) in response.data, (
            "start_date after end_date must not silently return zero/partial rows"
        )


# ------------------------------------------------------------------ #
# Malformed / invalid date strings                                     #
# ------------------------------------------------------------------ #

class TestMalformedDates:
    @pytest.mark.parametrize("start_date", ["not-a-date", "2026-02-30", "02/10/2026", ""])
    def test_malformed_start_date_alone_falls_back_to_unfiltered(
        self, seeded_client, urls, start_date
    ):
        client, _ = seeded_client
        response = client.get(
            urls["profile"],
            query_string={"start_date": start_date},
        )

        assert response.status_code == 200, (
            f"Malformed start_date={start_date!r} must not cause a 500"
        )
        for description in ALL_DESCRIPTIONS:
            assert description.encode() in response.data
        assert _currency(ALL_TOTAL) in response.data

    def test_malformed_end_date_alone_falls_back_to_unfiltered(self, seeded_client, urls):
        client, _ = seeded_client
        response = client.get(
            urls["profile"],
            query_string={"end_date": "not-a-date"},
        )

        assert response.status_code == 200
        for description in ALL_DESCRIPTIONS:
            assert description.encode() in response.data
        assert _currency(ALL_TOTAL) in response.data

    def test_malformed_start_date_with_valid_end_date_uses_end_only(self, seeded_client, urls):
        """Per spec, invalid dates are validated/ignored per field, not
        as an all-or-nothing pair -- a malformed start_date alongside a
        valid end_date should degrade to a single-bound (end_date-only)
        filter rather than wiping out the valid end_date too."""
        client, _ = seeded_client
        response = client.get(
            urls["profile"],
            query_string={"start_date": "not-a-date", "end_date": "2026-02-28"},
        )

        assert response.status_code == 200
        assert b"Jan grocery" in response.data
        assert b"Feb metro" in response.data
        assert b"Feb dinner" in response.data
        assert b"March electricity" not in response.data
        assert b"April movie" not in response.data
        assert _currency(75.00) in response.data  # 20 + 40 + 15

    def test_valid_start_date_with_malformed_end_date_uses_start_only(self, seeded_client, urls):
        client, _ = seeded_client
        response = client.get(
            urls["profile"],
            query_string={"start_date": "2026-02-01", "end_date": "not-a-date"},
        )

        assert response.status_code == 200
        assert b"Jan grocery" not in response.data
        assert b"Feb metro" in response.data
        assert b"Feb dinner" in response.data
        assert b"March electricity" in response.data
        assert b"April movie" in response.data
        assert _currency(185.00) in response.data  # 40 + 15 + 100 + 30

    def test_both_dates_malformed_falls_back_to_unfiltered(self, seeded_client, urls):
        client, _ = seeded_client
        response = client.get(
            urls["profile"],
            query_string={"start_date": "banana", "end_date": "2026-13-40"},
        )

        assert response.status_code == 200
        for description in ALL_DESCRIPTIONS:
            assert description.encode() in response.data
        assert _currency(ALL_TOTAL) in response.data


# ------------------------------------------------------------------ #
# Form repopulation / Clear link (Definition of Done)                  #
# ------------------------------------------------------------------ #

class TestFormRepopulation:
    def test_submitted_dates_are_repopulated_in_the_page(self, seeded_client, urls):
        client, _ = seeded_client
        response = client.get(
            urls["profile"],
            query_string={"start_date": "2026-02-01", "end_date": "2026-02-28"},
        )

        assert response.status_code == 200
        assert b'name="start_date"' in response.data
        assert b'name="end_date"' in response.data
        assert b"2026-02-01" in response.data
        assert b"2026-02-28" in response.data

    def test_clear_link_points_to_bare_profile_url(self, app, seeded_client, urls):
        client, _ = seeded_client
        response = client.get(
            urls["profile"],
            query_string={"start_date": "2026-02-01", "end_date": "2026-02-28"},
        )

        assert response.status_code == 200
        bare_href = f'href="{urls["profile"]}"'.encode()
        assert bare_href in response.data, (
            "Expected a link back to the bare (unfiltered) /profile URL"
        )

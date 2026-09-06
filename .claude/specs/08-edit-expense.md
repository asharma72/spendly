# Spec: Edit Expense

## Overview
Users can add expenses (Step 7) but have no way to correct a mistake —
wrong amount, wrong category, wrong date — without deleting and
re-adding the row (and delete isn't implemented yet either).
`/expenses/<id>/edit` is currently a stub that returns a plain string.
This feature implements the edit flow end to end: a pre-filled form
for an existing expense, a POST handler that validates and updates it
via `database/db.py`, and an "Edit" link from the profile page's
transaction table so the route is actually reachable without typing a
URL. Ownership must be enforced — a user can only edit their own
expenses.

## Depends on
- `01-database-setup.md` — `expenses` table (`user_id`, `amount`,
  `category`, `date`, `description`) must exist.
- `03-login-and-logout.md` — session-based auth (`session["user_id"]`)
  must be in place to determine the current user and check ownership.
- `07-add-expense.md` — provides the form UX pattern
  (`static/css/expenses.css`, `EXPENSE_CATEGORIES`, the validation
  style in `app.py`) this feature reuses, and is the only way an
  expense row currently gets created to edit.

## Routes
- `GET /expenses/<int:id>/edit` — renders the edit form pre-filled
  with the expense's current amount, category, date, and description.
  Access: any authenticated user (`session.get("user_id")` guard,
  redirect to `login` if absent), **and** the expense must belong to
  the current user — if `id` doesn't exist or belongs to a different
  user, `abort(404)` rather than leaking whether the id exists.
- `POST /expenses/<int:id>/edit` — validates form input and updates
  the matching row in `expenses`, then redirects to `/profile`. On
  validation failure, re-renders the form with an `error` message and
  the submitted values (same pattern as `add_expense`). Same auth +
  ownership guard as `GET`.

## Database changes
No changes to `schema.sql` / `init_db()` — the existing `expenses`
table already has every column this feature needs. This feature adds
a `SELECT ... WHERE id = ? AND user_id = ?` and an `UPDATE`, not a
schema change.

## Frontend components
No React — server-rendered Jinja template with vanilla JS, per project
conventions.
- **Create:** `templates/expenses_edit.html` — extends `base.html`,
  structurally identical to `templates/expenses_add.html` (same
  `form-group` markup, same `auth-card`/`auth-error` pattern) but:
  - Title reads "Edit expense".
  - Fields are pre-filled from the existing expense, not from a failed
    submission's re-posted values.
  - Form `action` is `{{ url_for('edit_expense', id=expense.id) }}`.
  - Submit button reads "Save changes".
  - Reuses `static/css/expenses.css` — no new CSS file.
- **Modify:** `templates/profile.html` — the "Recent transactions"
  table (around line 68-88) has no way to reach an expense's `id`
  today. Add an "Actions" column with an "Edit" link
  (`url_for('edit_expense', id=tx.id)`) per row. Do **not** add a
  Delete link/column yet — `/expenses/<id>/delete` is still a Step 9
  stub, and `CLAUDE.md` says not to implement a stub route ahead of
  its step; wiring a link to it here would point at unfinished
  behavior.

No JS needed — a plain form POST is sufficient.

## Files to change
- `app.py` — replace the `edit_expense` stub with `GET`/`POST` logic:
  auth + ownership guard, form parsing/validation on `POST` (mirroring
  `add_expense`), update via a new `database/db.py` helper, redirect
  to `profile` on success.
- `templates/profile.html` — add the "Actions" column / Edit link to
  the transaction table, and add `id` to the transaction dicts it
  loops over (see next bullet).
- `app.py` — `build_transaction_history()` currently returns `date`,
  `description`, `category`, `amount` per row (no `id`); add `id` so
  `profile.html` can link to `edit_expense`.

## Files to create
- `templates/expenses_edit.html`

`database/db.py` is **modified**, not created (see below).

## New dependencies
No new dependencies.

## Rules for implementation
- No ORM — raw `sqlite3` via `database/db.py`'s existing `get_db()`
  (already runs `PRAGMA foreign_keys = ON` — do not touch that).
- Parameterized queries only (`?` placeholders) — never f-strings or
  `.format()` into SQL for the new `SELECT`/`UPDATE`.
- All DB logic stays in `database/db.py` — add new functions there
  (e.g. `get_expense_by_id(expense_id, user_id)` and
  `update_expense(expense_id, user_id, amount, category, date,
  description)`) rather than inlining SQL in the `app.py` route,
  matching every existing route.
- **Ownership check belongs in the SQL, not just the route**: both the
  lookup and the update should filter on `WHERE id = ? AND user_id =
  ?`, not `WHERE id = ?` followed by an app-level comparison — this
  way a crafted `UPDATE` can never touch another user's row even if a
  guard above it were missed.
- If `get_expense_by_id` returns nothing (wrong id, or id belongs to
  another user), call `abort(404)` — per `CLAUDE.md`, use `abort()`
  for HTTP errors, never `return "error string"`.
- `amount` must be validated server-side as a positive number before
  update (reject `0`, negative, non-numeric) — same rule as
  `add_expense`, do not trust HTML `min`/`step` alone.
- `category` must be validated against `EXPENSE_CATEGORIES`
  server-side (reject anything else), same as `add_expense`.
- `date` must be a valid `YYYY-MM-DD` string; reuse the same loose
  `datetime.strptime` validation style already used for
  `_parse_date_range` / `add_expense` — invalid/missing date falls
  back to today rather than crashing, matching `add_expense`'s
  existing behavior for consistency.
- `description` is optional — empty string or `None` is fine.
- On validation failure, re-render `expenses_edit.html` with an
  `error` string and the submitted (not the original) values
  repopulated — same UX pattern as `add_expense`/`register`/`login`.
- `templates/expenses_edit.html` extends `base.html` and uses
  `url_for()` for its form action and any links — never a hardcoded
  `/expenses/<id>/edit`.
- No inline `<style>` tags — reuse `static/css/expenses.css`; add new
  rules there only if the edit form needs something the add form's
  styles don't already cover.
- No new pip packages.

## Definition of done
- [ ] `python app.py` runs on port 5001 with no errors.
- [ ] Visiting `/expenses/<id>/edit` while logged out redirects to
      `/login`.
- [ ] Visiting `/expenses/<id>/edit` for an expense that belongs to
      another user (or a nonexistent id) returns a 404, not a crash
      or someone else's data.
- [ ] Visiting `/expenses/<id>/edit` for your own expense shows the
      form pre-filled with its current amount, category, date, and
      description.
- [ ] Submitting valid changes redirects to `/profile` and the
      updated values are reflected in the transaction history and in
      the stats/category breakdown (e.g. changing category moves the
      totals).
- [ ] Submitting with a missing/zero/negative/non-numeric `amount`
      re-renders the form with an error and does not modify the row.
- [ ] Submitting with a category outside the fixed list re-renders the
      form with an error and does not modify the row.
- [ ] Submitting with an invalid `date` string does not crash — same
      fallback/error behavior as `add_expense`, kept consistent.
- [ ] Submitting with no `description` succeeds (it's optional).
- [ ] The "Recent transactions" table on `/profile` shows an "Edit"
      link per row that goes to the correct expense's edit page.
- [ ] No SQL in the new lookup/update path is built via string
      interpolation, and both queries filter by `user_id` as well as
      `id`.
- [ ] No inline `<style>` in `expenses_edit.html`.

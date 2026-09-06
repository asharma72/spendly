# Spec: Add Expense

## Overview
Users can currently register, log in, and view their spending on the
profile page, but there is no way to actually record a new expense —
`/expenses/add` is still a stub that returns a plain string. This
feature implements the "add expense" flow end to end: a form page
where a logged-in user enters an amount, category, date, and optional
description, and a POST handler that validates and persists it via
`database/db.py`. This is the first write path for `expenses` since
`seed_db()`, and it unblocks edit (Step 8) and delete (Step 9), which
both need a working expense record to act on.

## Depends on
- `01-database-setup.md` — `expenses` table (`user_id`, `amount`,
  `category`, `date`, `description`) must exist.
- `03-login-and-logout.md` — session-based auth (`session["user_id"]`)
  must be in place to attribute the new expense to a user.

## Routes
- `GET /expenses/add` — renders the add-expense form, pre-filled with
  today's date. Access: any authenticated user
  (`session.get("user_id")` guard, redirect to `login` if absent —
  same pattern as `/profile`).
- `POST /expenses/add` — validates form input and inserts a new row
  into `expenses` for the current user, then redirects to `/profile`.
  On validation failure, re-renders the form with an `error` message
  and the submitted values (same pattern as `register`/`login`).
  Access: any authenticated user, same guard as above.

## Database changes
No changes to `schema.sql` / `init_db()` — the `expenses` table
created in `database/db.py::init_db()` already has every column this
feature needs (`user_id`, `amount`, `category`, `date`, `description`).
This feature only adds an `INSERT`, not a schema change.

## Frontend components
No React — server-rendered Jinja template with vanilla JS, per project
conventions.
- **Create:** `templates/expenses_add.html` — extends `base.html`.
  Form fields: `amount` (number input, step `0.01`, min `0.01`),
  `category` (`<select>` with the fixed category list already used
  elsewhere in the app: Food, Transport, Bills, Health, Entertainment,
  Shopping, Other), `date` (`<input type="date">`, defaults to today),
  `description` (optional text input). Submits `POST` to
  `{{ url_for('add_expense') }}`. Show `error` above the form when
  present, matching the `register.html` error-banner pattern.
- **Create:** `static/css/expenses.css` — styles for the add-expense
  form card (and reusable by the Step 8 edit form, which will need an
  effectively identical layout).
- **Modify:** `templates/base.html` — nav currently links to
  `analytics` for logged-in users; add an "Add Expense" link
  (`url_for('add_expense')`) next to it so the feature is reachable
  from anywhere, not just by typing the URL.

No JS needed — a plain form POST is sufficient.

## Files to change
- `app.py` — replace the `add_expense` stub with `GET`/`POST` logic:
  auth guard, form parsing/validation on `POST`, insert via a new
  `database/db.py` helper, redirect to `profile` on success.
- `templates/base.html` — add the "Add Expense" nav link.

## Files to create
- `templates/expenses_add.html`
- `static/css/expenses.css`

`database/db.py` is **modified**, not created (see below).

## New dependencies
No new dependencies.

## Rules for implementation
- No ORM — raw `sqlite3` via `database/db.py`'s existing `get_db()`
  (already runs `PRAGMA foreign_keys = ON` — do not touch that).
- Parameterized queries only (`?` placeholders) — never f-strings or
  `.format()` into SQL for the new `INSERT`.
- All DB logic stays in `database/db.py` — add a new function there
  (e.g. `create_expense(user_id, amount, category, date, description)`)
  rather than inlining `INSERT` SQL in the `app.py` route, matching
  every existing route (`register`, `get_expense_stats`, etc.).
- Auth stays as-is: guard both `GET` and `POST` on
  `/expenses/add` with `session.get("user_id")`, redirecting to
  `login` — do not introduce a new auth mechanism.
- `amount` must be validated server-side as a positive number before
  insert (reject `0`, negative, non-numeric) — do not trust the HTML
  `min`/`step` attributes alone, since a POST can bypass the form.
- `category` must be validated against the fixed known list server-side
  (reject anything else) rather than accepting arbitrary text, so
  category totals on `/profile` stay meaningful.
- `date` must be a valid `YYYY-MM-DD` string (reuse the same loose
  `datetime.strptime` validation style already used in `app.py`'s
  `_parse_date_range`) — invalid/missing date falls back to today
  rather than crashing.
- `description` is optional — empty string or `None` is fine, no
  minimum length.
- On validation failure, re-render `expenses_add.html` with an
  `error` string and the submitted values repopulated (same UX
  pattern as `register`/`login`) — never a bare `return "error string"`.
- `templates/expenses_add.html` extends `base.html` and uses
  `url_for()` for its form action and any links — never a hardcoded
  `/expenses/add`.
- New styles go in `static/css/expenses.css`, not inline `<style>`
  tags in the template.
- No new pip packages.

## Definition of done
- [ ] `python app.py` runs on port 5001 with no errors.
- [ ] Visiting `/expenses/add` while logged out redirects to `/login`.
- [ ] Visiting `/expenses/add` while logged in shows the form with
      today's date pre-filled.
- [ ] Submitting a valid expense (positive amount, valid category,
      valid date) redirects to `/profile` and the new expense appears
      in the transaction history and is reflected in the stats/category
      breakdown.
- [ ] Submitting with a missing/zero/negative/non-numeric `amount`
      re-renders the form with an error and does not insert a row.
- [ ] Submitting with a category outside the fixed list re-renders the
      form with an error and does not insert a row.
- [ ] Submitting with an invalid `date` string does not crash — falls
      back to today's date or shows a clear error (per whichever
      behavior is implemented — pick one and keep it consistent, no
      500).
- [ ] Submitting with no `description` succeeds (it's optional).
- [ ] The nav shows an "Add Expense" link when logged in, using
      `url_for()`.
- [ ] No SQL in the new insert path is built via string interpolation.
- [ ] No inline `<style>` in `expenses_add.html`; styles live in
      `static/css/expenses.css`.

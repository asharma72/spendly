# Spec: Date Filter for Profile Page

## Overview
The profile page currently shows all-time stats, transaction history, and
category breakdown with no way to narrow the view to a specific time
window. This feature adds a date-range filter (start date / end date) to
`/profile` so a user can see their spending stats, recent transactions,
and category breakdown for just that range. This is a natural next step
now that `/profile` is wired to live DB queries (spec 05) and gives
students practice threading query params from a Flask route down through
`database/db.py` into parameterized SQL.

## Depends on
- `04-profile-page.md` — profile page UI/layout (stats row, transaction
  table, category breakdown) must exist.
- `05-backend-routes-for-profile-page.md` — `/profile` must already be
  wired to live DB data via `build_profile_summary`,
  `build_transaction_history`, and `build_category_breakdown` in
  `app.py`, backed by `get_expense_stats`, `get_recent_expenses`, and
  `get_category_totals` in `database/db.py`.

## Routes
- `GET /profile` — modified, not new. Now also reads optional
  `start_date` and `end_date` query args (`YYYY-MM-DD`) and scopes
  stats/transactions/category breakdown to that range when present.
  Access: authenticated user only, existing `session.get("user_id")`
  guard (unchanged).

## Database changes
No changes to `database/db.py`'s table definitions — the `expenses.date`
column is already `TEXT NOT NULL` storing ISO `YYYY-MM-DD` strings, so
lexicographic comparison (`date >= ? AND date <= ?`) works without any
schema change or date parsing.

Function signature changes only (all in `database/db.py`), each new
param optional and defaulting to `None` so existing callers keep working:
- `get_expense_stats(user_id, start_date=None, end_date=None)`
- `get_recent_expenses(user_id, limit=10, start_date=None, end_date=None)`
- `get_category_totals(user_id, start_date=None, end_date=None)`

Each function builds its `WHERE` clause conditionally and always passes
values as parameterized `?` args — never string-interpolated into SQL.

## Frontend components
No React — this is a server-rendered Jinja template with vanilla JS,
per project conventions.
- **Modify:** `templates/profile.html` — add a filter form above the
  transaction/category sections: two `<input type="date">` fields
  (`start_date`, `end_date`) plus an "Apply" submit button, method
  `GET` to `{{ url_for('profile') }}`, values repopulated from the
  current query args so the filter persists on submit. Include a
  "Clear" link back to plain `{{ url_for('profile') }}`.
- **Modify:** `static/css/profile.css` — style the new filter form to
  match the existing card-based layout (no inline `<style>` tags).

No JS is required for this feature — a plain GET form re-render is
sufficient and keeps the change small; do not add auto-submit-on-change
JS unless explicitly asked in a later step.

## Files to change
- `app.py` — `profile()` route reads `request.args.get("start_date")`
  / `request.args.get("end_date")` and passes them through to
  `build_profile_summary`, `build_transaction_history`, and
  `build_category_breakdown`; those three helpers accept and forward
  the same optional params to their `database/db.py` calls; pass
  `start_date`/`end_date` back to the template so the form can
  repopulate.
- `database/db.py` — add optional `start_date`/`end_date` params to
  `get_expense_stats`, `get_recent_expenses`, `get_category_totals` as
  described above.
- `templates/profile.html` — add the filter form.
- `static/css/profile.css` — style it.

## Files to create
None.

## New dependencies
No new dependencies. The `date` column is plain ISO text, so no date
parsing library is needed — string comparison in SQL is sufficient.

## Rules for implementation
- No ORM — raw `sqlite3` via `database/db.py`'s existing `get_db()`
  (which already runs `PRAGMA foreign_keys = ON` on every connection —
  do not touch that).
- Parameterized queries only (`?` placeholders) — never f-strings or
  `.format()` into SQL, including for the new date-range clauses.
- All DB logic stays in `database/db.py` — do not inline SQL in
  `app.py` routes.
- Keep the existing deviation from spec 05: query helpers live in
  `database/db.py` and formatting/orchestration helpers
  (`build_profile_summary`, etc.) live in `app.py` — do not introduce
  a new `database/queries.py` module as part of this step.
- `templates/profile.html` continues to extend `base.html`; use
  `url_for('profile')` for the form action and the "Clear" link —
  never hardcode `/profile`.
- Auth stays as-is: the existing `session.get("user_id")` guard in the
  `/profile` route — do not introduce a new auth mechanism.
- Validate `start_date`/`end_date` loosely (e.g. ignore if not parseable
  as `YYYY-MM-DD`) rather than raising — a bad/missing date param
  should fall back to unfiltered (all-time) results, not a 500.
- If `start_date` is after `end_date`, treat it as no filter rather than
  erroring — this is a learning project, not a production form, so keep
  validation simple.
- Preserve the existing currency (₹) and percentage-rounding conventions
  in `build_category_breakdown` (largest category absorbs the rounding
  remainder) — the date filter changes *which* rows are aggregated, not
  how they're formatted.
- No new pip packages.

## Definition of done
- [ ] `python app.py` runs on port 5001 with no errors.
- [ ] Visiting `/profile` with no query args behaves exactly as before
      (all-time stats, transactions, category breakdown).
- [ ] Visiting `/profile?start_date=2026-01-01&end_date=2026-03-31`
      shows stats, transaction history, and category breakdown scoped
      only to expenses with `date` in that inclusive range.
- [ ] The filter form's inputs are pre-populated with the current
      `start_date`/`end_date` after submitting.
- [ ] The "Clear" link returns to unfiltered `/profile`.
- [ ] An invalid or partial date (e.g. only `start_date` set, or a
      malformed string) does not crash the page — it falls back to
      sensible behavior (unfiltered or single-bound filter).
- [ ] `start_date` after `end_date` does not crash the page and does
      not silently return zero rows in a confusing way (treated as no
      filter).
- [ ] No SQL is built via string interpolation — confirm all new
      `WHERE` clauses in `database/db.py` use `?` placeholders.
- [ ] No inline `<style>` added to `profile.html`; new styles live in
      `static/css/profile.css`.
- [ ] No hardcoded `/profile` URLs — template uses `url_for('profile')`.

# Spec: Delete Expense

## Overview
Users can add (Step 7) and edit (Step 8) expenses but have no way to
remove one entirely — a duplicate entry or a mistake typed into the
wrong month currently has to stay in the ledger forever.
`/expenses/<id>/delete` is currently a stub that returns a plain
string. This feature implements the delete flow: a "Delete" action
next to "Edit" in the profile page's transaction table, a route that
removes the matching row via `database/db.py`, and a redirect back to
`/profile` with an updated summary. Ownership must be enforced — a
user can only delete their own expenses.

## Depends on
- `01-database-setup.md` — `expenses` table must exist.
- `03-login-and-logout.md` — session-based auth (`session["user_id"]`)
  must be in place to determine the current user and check ownership.
- `08-edit-expense.md` — provides the "Actions" column in
  `templates/profile.html`'s transaction table (`Edit` link) that this
  feature adds a `Delete` link next to, and the
  `get_expense_by_id(id, user_id)` ownership-lookup pattern this
  feature reuses.

## Routes
- `GET /expenses/<int:id>/delete` — deletes the expense (matching
  `CLAUDE.md`'s documented stub signature — GET, not POST). Access:
  any authenticated user (`session.get("user_id")` guard, redirect to
  `login` if absent), **and** the expense must belong to the current
  user — look it up with the existing `get_expense_by_id(id,
  user_id)` first; if it returns `None` (wrong id, or belongs to
  another user), `abort(404)` rather than leaking whether the id
  exists. On success, delete the row and redirect to
  `/profile?deleted=1`.

## Database changes
No changes to `schema.sql` / `init_db()` — deleting a row needs no new
columns. This feature adds one new query to `database/db.py`.

## Frontend components
No React — server-rendered Jinja template with vanilla JS, per project
conventions.
- **Modify:** `templates/profile.html` — the "Actions" column (added
  in Step 8, line ~86-88) currently has only an `Edit` link. Add a
  `Delete` link right after it, pointing at
  `{{ url_for('delete_expense', id=tx.id) }}`, with a
  `data-confirm-delete` attribute (or similar hook) for `main.js` to
  bind a confirmation prompt to — no inline `onclick` attribute, to
  keep behavior in `static/js/main.js` per the vanilla-JS convention
  already used for `.filter-pill` and the "added" alert.
- **Modify:** `static/js/main.js` —
  - Add a listener (e.g. `initDeleteConfirm()`, called from the
    existing `DOMContentLoaded` handler) that intercepts clicks on
    `[data-confirm-delete]` links and calls `confirm("Delete this
    expense?")`, calling `event.preventDefault()` if the user cancels.
  - Add `initExpenseDeletedAlert()`, mirroring the existing
    `initExpenseAddedAlert()`: if `?deleted=1` is present, `alert()` a
    confirmation and strip the param via
    `window.history.replaceState`, same pattern already used for
    `added=1`.

## Files to change
- `app.py` — replace the `delete_expense` stub with real logic: auth
  guard, ownership lookup via `get_expense_by_id`, `abort(404)` if
  missing/not owned, delete via a new `database/db.py` helper,
  redirect to `/profile?deleted=1`.
- `database/db.py` — add `delete_expense(expense_id, user_id)`.
- `templates/profile.html` — add the `Delete` link to the Actions
  column.
- `static/js/main.js` — add `initDeleteConfirm()` and
  `initExpenseDeletedAlert()`, and call both from the
  `DOMContentLoaded` handler alongside the existing `init*` calls.

## Files to create
None — every file involved already exists.

## New dependencies
No new dependencies.

## Rules for implementation
- No ORM — raw `sqlite3` via `database/db.py`'s existing `get_db()`
  (already runs `PRAGMA foreign_keys = ON` — do not touch that).
- Parameterized queries only (`?` placeholders) — never f-strings or
  `.format()` into SQL for the new `DELETE`.
- All DB logic stays in `database/db.py` — add
  `delete_expense(expense_id, user_id)` there rather than inlining SQL
  in the `app.py` route, matching every existing route.
- **Ownership check belongs in the SQL, not just the route**: the
  `DELETE` itself should filter on `WHERE id = ? AND user_id = ?`, not
  `WHERE id = ?` — this way a crafted request can never remove another
  user's row even if the guard above it were missed. In addition,
  call `get_expense_by_id(id, user_id)` first (already exists from
  Step 8) so a missing/foreign id can `abort(404)` before attempting
  the delete, matching `edit_expense`'s existing pattern.
- If `get_expense_by_id` returns nothing, call `abort(404)` — per
  `CLAUDE.md`, use `abort()` for HTTP errors, never
  `return "error string"`.
- This route is destructive but reachable via a plain `GET` link (per
  `CLAUDE.md`'s documented stub — the table lists it as `GET`, not
  `POST`, and none of `register`/`login`/`edit_expense` use CSRF
  tokens either, so introducing one here alone would be inconsistent
  rather than more secure). Mitigate accidental clicks with the
  client-side `confirm()` dialog described above — this is a UX
  safeguard, not a security control, and should be called out as a
  known tradeoff in review rather than silently left unmentioned.
- `templates/profile.html`'s `Delete` link uses `url_for()` — never a
  hardcoded `/expenses/<id>/delete`.
- No inline `<style>` tags and no inline `onclick` — the confirm
  behavior lives in `static/js/main.js`.
- No new pip packages.

## Definition of done
- [ ] `python app.py` runs on port 5001 with no errors.
- [ ] Visiting `/expenses/<id>/delete` while logged out redirects to
      `/login` and does not delete anything.
- [ ] Visiting `/expenses/<id>/delete` for an expense that belongs to
      another user (or a nonexistent id) returns a 404 and does not
      delete anything.
- [ ] Visiting `/expenses/<id>/delete` for your own expense removes it
      and redirects to `/profile?deleted=1`; the deleted expense no
      longer appears in the transaction history, and the stats/
      category breakdown update accordingly (total spent drops,
      transaction count decreases).
- [ ] The "Recent transactions" table on `/profile` shows a `Delete`
      link per row next to `Edit`, pointing at the correct expense.
- [ ] Clicking `Delete` triggers a `confirm()` prompt; canceling it
      does not navigate or delete the row.
- [ ] After a successful delete, `/profile` shows a one-time "deleted"
      alert and the `?deleted=1` param is stripped from the URL
      (mirroring the existing `?added=1` behavior).
- [ ] No SQL in the new delete path is built via string interpolation,
      and the `DELETE` filters by `user_id` as well as `id`.
- [ ] No inline `<style>` or inline `onclick` introduced.

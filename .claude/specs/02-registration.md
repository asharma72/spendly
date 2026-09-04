# Spec: Registration

## Overview
This feature implements user registration for Spendly. Step 1 built the
data layer (`users` / `expenses` tables and `get_db()` / `init_db()` /
`seed_db()`). The `/register` route and `register.html` template already
exist as a GET-only stub — this step wires the form up to actually create
an account: validate the submitted data, hash the password, insert a new
row into `users`, start a session, and route the new user into the app.
Login (`/login`), which already has a matching template, is treated as a
separate, later step and is out of scope here.

## Depends on
- Step 1 — Database setup (`.claude/specs/01-database-setup.md`) must be
  complete: `users` table, `get_db()`, `init_db()`.

## Routes
- `POST /register` — validate form input, create the user, start a
  session, redirect to `/login` — public
- `GET /register` — existing route, unchanged (renders the form)

## Database changes
No database changes. The `users` table (id, name, email, password_hash,
created_at) from `database/db.py` already supports this feature as-is.

## Templates
- **Create:** none
- **Modify:** `templates/register.html` — adds a `confirm_password` field
  so the user re-types their password; it already posts to `/register`
  and renders `{{ error }}`.

## Files to change
- `app.py`
  - Add `app.secret_key` (from an environment variable, with a
    development fallback) so Flask sessions work.
  - Change `@app.route("/register")` to accept `methods=["GET", "POST"]`.
  - On `POST`: validate name/email/password/confirm_password, check that
    password and confirm_password match, check for a duplicate email,
    hash the password, insert the user, store `user_id` in the session,
    redirect to `/login`. On validation failure, re-render
    `register.html` with `error` set and the submitted values preserved.
- `database/db.py`
  - Add a small helper, e.g. `get_user_by_email(email)`, so the duplicate
    email check and any future login work reuse one parameterised query
    instead of each route writing its own.

## Files to create
None.

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs.
- Parameterised queries only — never build SQL with string formatting.
- Passwords hashed with werkzeug (`generate_password_hash` /
  `check_password_hash`).
- Use CSS variables — never hardcode hex values.
- All templates extend `base.html`.
- Validate on the server even though the form has HTML5 `required`
  attributes — treat client-side validation as UX only.
- Enforce the same minimum password length the placeholder text implies
  ("Min. 8 characters").
- Duplicate email must fail with a user-facing error, not a 500 (the
  `users.email` UNIQUE constraint is the backstop, not the primary check).

## Definition of done
- [ ] `GET /register` still renders the form with no errors.
- [ ] Submitting valid name/email/password (8+ chars) creates a new row
      in `users` with a hashed (not plaintext) password.
- [ ] After successful registration, the session contains the new
      `user_id` and the browser is redirected to `/login`.
- [ ] Submitting an already-registered email re-renders `register.html`
      with an error and does not insert a duplicate row.
- [ ] Submitting a password under 8 characters re-renders `register.html`
      with an error and does not insert a row.
- [ ] Submitting a password and confirm password that don't match
      re-renders `register.html` with an error and does not insert a row.
- [ ] Restarting the app (`python app.py`) does not error and does not
      duplicate or lose existing users.

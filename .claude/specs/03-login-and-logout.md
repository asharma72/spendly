# Spec: Login and Logout

## Overview
This feature implements user authentication for Spendly: signing in
and signing out. Step 1 built the data layer (`users` table, `get_db()`,
`get_user_by_email()`), and Step 2 (Registration) creates accounts and
redirects new users to `/login`. The `/login` route and `login.html`
template currently exist as a GET-only stub, and `/logout` is a
placeholder that returns plain text. This step wires `/login` up to
authenticate against the `users` table and start a session, and wires
`/logout` up to end that session — plus updates the shared nav in
`base.html` so a signed-in user can see they're logged in and actually
reach the logout action. It also guards `/login` and `/register` against
an already-signed-in user (redirecting them to `/` instead of
re-showing the auth forms). Protecting logged-in-only pages (e.g.
`/profile`, the expense routes) with a `login_required` guard is a
separate, later step and is out of scope here — this spec only
establishes and tears down the session itself.

## Depends on
- Step 1 — Database setup (`.claude/specs/01-database-setup.md`) must be
  complete: `users` table, `get_db()`.
- Step 2 — Registration (`.claude/specs/02-registration.md`) must be
  complete: `get_user_by_email()` in `database/db.py`, accounts with
  hashed passwords to log into.

## Routes
- `POST /login` — validate submitted email/password against the `users`
  table, start a session, redirect to `/` — public
- `GET /login` — existing route, unchanged (renders the form)
- `POST /logout` — clear the session, redirect to `/` — logged-in
  (changed from the existing placeholder `GET /logout`, since logging
  out changes state and should not be a plain link/GET request)

## Database changes
No database changes. `get_user_by_email(email)` in `database/db.py`
(added in Step 2) already supports the lookup this feature needs.

## Templates
- **Create:** none
- **Modify:**
  - `templates/login.html` — none needed; it already posts to
    `/login`, has `email`/`password` fields, and renders `{{ error }}`.
  - `templates/base.html` — nav becomes session-aware: when
    `session.user_id` is set, show a "Logout" control (a small form
    posting to `/logout`, styled as a link) instead of "Sign in" /
    "Get started".

## Files to change
- `app.py`
  - Change `@app.route("/login")` to accept `methods=["GET", "POST"]`.
  - On `POST /login`: read `email`/`password` from the form, look up
    the user with `get_user_by_email()`, verify the password with
    `check_password_hash`, and:
    - If no user is found, or the password doesn't match, re-render
      `login.html` with a single generic `error` (do not reveal
      whether the email exists) and the submitted email preserved.
    - If the credentials are valid, store `user_id` in the session and
      redirect to `/` (landing page). `/profile` still just returns
      placeholder text until Step 4, so login lands the user back on
      the landing page instead, where the nav now shows they're
      signed in.
  - Replace the `/logout` placeholder with `@app.route("/logout",
    methods=["POST"])` that calls `session.clear()` and redirects to
    `/` (landing page).
- `templates/base.html`
  - Wrap the existing "Sign in" / "Get started" nav links in
    `{% if not session.user_id %}...{% else %}...{% endif %}`; the
    `else` branch renders a logout form/button posting to
    `{{ url_for('logout') }}`.

## Files to create
None.

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs.
- Parameterised queries only.
- Passwords hashed with werkzeug (`check_password_hash` against the
  `password_hash` already stored by registration).
- Use CSS variables — never hardcode hex values.
- All templates extend `base.html`.
- Validate on the server even though the form has HTML5 `required`
  attributes — treat client-side validation as UX only.
- Use one generic error message ("Invalid email or password.") for both
  "email not found" and "wrong password" cases, so login can't be used
  to enumerate registered emails.
- Logout must be a `POST` (a form submission), never a plain `<a href>`
  link, since it changes state (clears the session).

## Definition of done
- [ ] `GET /login` still renders the form with no errors.
- [ ] Submitting the seeded demo account (`demo@spendly.com` /
      `demo123`) logs in successfully, sets `user_id` in the session,
      and redirects to `/`.
- [ ] Submitting an email that isn't registered re-renders `login.html`
      with the generic error and does not start a session.
- [ ] Submitting a registered email with the wrong password re-renders
      `login.html` with the same generic error and does not start a
      session.
- [ ] After logging in, the nav on every page shows a "Logout" control
      instead of "Sign in" / "Get started".
- [ ] Submitting the logout form clears the session, redirects to `/`,
      and the nav reverts to showing "Sign in" / "Get started".
- [ ] Restarting the app (`python app.py`) does not error and existing
      users can still log in and out.
- [ ] While logged in, visiting `/login` or `/register` redirects to
      `/` instead of showing the auth form.

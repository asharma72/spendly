# Plan: Implement Registration (Step 2)

## Context
`.claude/specs/02-registration.md` defines the registration feature: the
`/register` route and `register.html` template already exist as a
GET-only stub from the database-setup step, and this step wires the form
to actually create an account — validate input, hash the password with
werkzeug, insert into `users`, start a Flask session, and redirect into
the app. Login is explicitly out of scope (separate later step).

Repo facts that shape the plan (confirmed by reading the files directly):
- `app.py` currently imports only `Flask, render_template` and has no
  `os`, `sqlite3`, `session`, `redirect`, `url_for`, `request`, or
  `generate_password_hash` imports.
- `database/db.py` has `get_db()`, `init_db()`, `seed_db()` but no
  email-lookup helper.
- `templates/register.html` already POSTs to `/register` with
  `name`/`email`/`password` fields and already renders
  `{% if error %}<div class="auth-error">{{ error }}</div>{% endif %}`,
  but inputs have no `value=` attribute, so a failed submission currently
  wipes what the user typed.
- No `SECRET_KEY`/`session`/env-loading convention exists anywhere in the
  repo yet (no `.env`, no `python-dotenv` in `requirements.txt`) — this
  step introduces that convention for the first time.
- `requirements.txt`: `flask==3.1.3`, `werkzeug==3.1.6`. No new
  dependency is needed.

## Approach

### 1. `database/db.py` — add a lookup helper
Insert directly after `get_db()`:
```python
def get_user_by_email(email):
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM users WHERE email = ?",
        (email,),
    ).fetchone()
    conn.close()
    return row
```
Returns a `sqlite3.Row` or `None`. Caller is responsible for
lower-casing `email` first — keeps this a plain reusable lookup for the
later login step too.

### 2. `app.py` — imports and secret key
- Add `import os` and `import sqlite3` at the top.
- Change `from flask import Flask, render_template` to
  `from flask import Flask, render_template, request, redirect, url_for, session`.
- Add `from werkzeug.security import generate_password_hash`.
- Change `from database.db import get_db, init_db, seed_db` to also
  import `get_user_by_email`.
- Immediately after `app = Flask(__name__)`, add:
  ```python
  app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production")
  ```

### 3. `app.py` — replace the `/register` route
Replace the current 3-line stub with a `methods=["GET", "POST"]` view:
- **GET** → render `register.html` unchanged.
- **POST** → extract `name`/`email`/`password`/`confirm_password` from
  `request.form` (`name`/`email` via `.strip()`, `email` additionally
  `.lower()`; `password`/`confirm_password` left un-stripped since
  leading/trailing spaces could be intentional).
- Validate in this order (cheapest/most-blocking first):
  1. Any of the four empty after stripping → re-render with error
     `"Please fill in all fields."` (also catches whitespace-only name).
  2. `len(password) < 8` → re-render with error
     `"Password must be at least 8 characters."`
  3. `password != confirm_password` → re-render with error
     `"Passwords do not match."`
  4. `get_user_by_email(email)` returns a row → re-render with error
     `"An account with this email already exists."`
- On the insert, wrap in `try/except sqlite3.IntegrityError` as a
  backstop for a same-email race between the pre-check and the insert,
  showing the same duplicate-email error string — fulfills the spec's
  "UNIQUE constraint is a backstop, not the primary check."
- Every re-render passes `name=name, email=email` (never `password`) so
  the template can repopulate what the user typed.
- On success: `generate_password_hash(password)` → insert via the same
  `get_db()`/parameterised-query pattern used elsewhere → commit →
  `session["user_id"] = cursor.lastrowid` → `redirect(url_for("login"))`.
  (The session is set at registration time even though the user still
  lands on `/login` next — login itself, a later step, will pick up an
  existing session or otherwise handle a signed-up-but-not-signed-in
  user.)

### 4. `templates/register.html` — small UX fix + confirm password field
Add `value="{{ name or '' }}"` to the name input and
`value="{{ email or '' }}"` to the email input, so a failed submission
doesn't wipe what the user typed. Add a new `confirm_password` password
input (mirroring the existing `password` field, no `value=` — never
echo passwords back) between the password field and the submit button.
No other template or CSS changes — `.auth-error` styling already exists
and is unaffected.

### 5. No changes needed
- `database/db.py` schema (`init_db`) — unchanged, `users` table already
  supports this.
- `static/css/style.css` — no new classes needed.
- `static/js/main.js` — no client-side logic required for this step.
- `requirements.txt` — no new dependency.

## Verification
With the dev server running (`python app.py`, port 5001), from
`D:\expense-tracker`, using `curl.exe` (not the PowerShell alias):

1. `curl.exe -s -o NUL -w "%{http_code}" http://127.0.0.1:5001/register`
   → expect `200`.
2. POST a valid registration (`name`, a fresh email, an 8+ char
   password) → expect `302` to `/login` with a `Set-Cookie: session=...`
   header. Then confirm the row:
   `python -c "from database.db import get_user_by_email; u=get_user_by_email('<email>'); print(dict(u))"`
   → `password_hash` should start with `pbkdf2:` or `scrypt:`, never the
   plaintext password.
3. Re-submit the same email → expect the duplicate-email error string in
   the response body and the row count for that email still `1`.
4. Submit the same email in a different case (`FOO@Example.com`) →
   expect it to also be flagged as a duplicate (confirms lowercasing).
5. Submit a password under 8 characters → expect the length error and no
   row inserted.
6. Submit all-blank fields → expect the "fill in all fields" error.
7. Submit a password and confirm_password that don't match → expect the
   "Passwords do not match." error and no row inserted.
8. Stop and restart `python app.py` → no traceback on startup, and the
   test users from steps 2-4 are still present exactly once (confirms
   `init_db`/`seed_db` idempotency is unaffected).
9. Optionally clean up test rows:
   `python -c "from database.db import get_db; c=get_db(); c.execute(\"DELETE FROM users WHERE email LIKE 'test%'\"); c.commit()"`

## Files touched
- `D:\expense-tracker\app.py`
- `D:\expense-tracker\database\db.py`
- `D:\expense-tracker\templates\register.html`

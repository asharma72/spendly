# Implementation Plan: Login and Logout (Step 3)

## Context
Spendly's `/login` route currently only renders the login form (GET) with
no authentication logic, and `/logout` is a placeholder that returns the
plain-text string "Logout — coming in Step 3". Step 2 (Registration) is
complete: accounts exist in the `users` table with hashed passwords, and
new users are redirected to `/login` after signing up — but there is
currently no way to actually sign in or out. This plan implements the
approved spec at `.claude/specs/03-login-and-logout.md`: wire `/login` up
to authenticate against the `users` table and start a session, wire
`/logout` up to end that session, and make the shared nav in `base.html`
session-aware so a logged-in user can see they're signed in and reach the
logout control. No database changes and no changes to `login.html` are
needed — everything reuses existing functions (`get_db()`,
`get_user_by_email()`) and patterns already established by the
`register` route.

## Approach

### 1. `app.py` — import `check_password_hash`
Extend the existing import line:
```
from werkzeug.security import generate_password_hash
```
to also import `check_password_hash` on the same line. `get_user_by_email`
(from `database.db`) and `session` (from `flask`) are already imported.

### 2. `app.py` — implement `POST /login`
Change the route decorator to `methods=["GET", "POST"]`. Structure the
body to mirror `register`'s existing shape (GET check → extract fields →
validate → succeed):

- **GET**: unchanged — `return render_template("login.html")`.
- **Extract**: `email = request.form.get("email", "").strip().lower()`,
  `password = request.form.get("password", "")`. Lowercasing/stripping
  the email matches how `register` normalizes and stores it, so lookups
  line up.
- **Look up**: `user = get_user_by_email(email)` — no new db helper.
- **Single generic failure branch** (collapses "no such user" and "wrong
  password" into one case, per the anti-enumeration rule):
  ```
  if user is None or not check_password_hash(user["password_hash"], password):
      return render_template("login.html", error="Invalid email or password.", email=email)
  ```
  This is intentionally one branch, not several — unlike `register`,
  which has distinct messages per field problem.
- **Success**: `session["user_id"] = user["id"]`, then
  `return redirect(url_for("landing"))`. `/profile` is still just a
  placeholder ("coming in Step 4"), so login redirects to the landing
  page instead, where the nav reflects the signed-in state.

No `try/except` needed here — this route only performs a `SELECT` via
`get_user_by_email`, not an `INSERT`, so there's no race/constraint to
catch.

### 3. `app.py` — implement `POST /logout`
Replace the placeholder with a `POST`-only route:
```
@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("landing"))
```
Move this route out of the "Placeholder routes — students will implement
these" comment block (up next to `login`/`register`), since it's no
longer a stub and leaving it under that comment would be inaccurate. A
stray GET to `/logout` will now correctly 405 rather than silently
"working" — logout must only ever be triggered by a form POST.

### 4. `templates/base.html` — session-aware nav
In the `.nav-links` block, wrap the two existing links in a
`{% if not session.user_id %} ... {% else %} ... {% endif %}`, keeping
the `<div class="nav-links">` wrapper outside the conditional:
```
<div class="nav-links">
    {% if not session.user_id %}
    <a href="{{ url_for('login') }}">Sign in</a>
    <a href="{{ url_for('register') }}" class="nav-cta">Get started</a>
    {% else %}
    <form action="{{ url_for('logout') }}" method="POST" class="logout-form">
        <button type="submit" class="logout-link">Logout</button>
    </form>
    {% endif %}
</div>
```
The form must be `method="POST"` (never a GET link) per the spec's hard
rule. Since `base.html` is shared by every page, this single edit makes
the logout control appear anywhere once logged in.

### 5. `static/css/style.css` — style the logout control as a link
Add rules near the existing `.nav-links` / `.nav-cta` rules (~line 95):
- `.logout-form` — reset margin/padding, `display: inline-flex` (or
  `contents`) so it sits in the flex row like a bare `<a>`.
- `.logout-link` — strip default `<button>` chrome (`background: none;
  border: none; padding: 0; margin: 0;`), inherit the nav font, set
  `color: var(--ink-muted)`, `cursor: pointer`, and
  `transition: color 0.2s` to match `.nav-links a`.
- `.logout-link:hover` — `color: var(--ink)`, matching `.nav-links a:hover`.
- Do **not** reuse `.nav-cta`'s pill/button styling — the logout control
  should look like a plain nav link.
- Add `.logout-link` alongside the existing mobile rule around line 685
  (`.nav-links a:not(.nav-cta) { display: none; }`) so it hides on the
  same breakpoint as the other plain nav link.
- Only existing CSS variables (`--ink-muted`, `--ink`) are used — no
  hardcoded hex values.

## Implementation order
1. `app.py` import (trivial, no behavior change).
2. `app.py` `/login` POST logic — testable immediately via the existing,
   unmodified `login.html`.
3. `app.py` `/logout` — small, independent change.
4. `templates/base.html` nav conditional — now meaningful because
   `session.user_id` is actually set/cleared by steps 2-3.
5. `static/css/style.css` — cosmetic, applied last against the new markup.

## Files touched
- `app.py` — routes for `/login` (POST logic) and `/logout` (real
  implementation replacing the placeholder).
- `templates/base.html` — session-aware nav.
- `static/css/style.css` — `.logout-form` / `.logout-link` rules.

No changes to `database/db.py` or `templates/login.html`.

## Verification (manual, run the app)
1. `python app.py`, confirm no startup errors.
2. `GET /login` still renders the form with no errors.
3. Log in with the seeded demo account (`demo@spendly.com` / `demo123`):
   should redirect to `/` (landing page), and the nav on any page should now
   show "Logout" instead of "Sign in" / "Get started".
4. Try an unregistered email — should re-render `login.html` with
   "Invalid email or password." and no session set.
5. Try the demo email with a wrong password — should show the identical
   error message (confirms no enumeration difference).
6. Click "Logout" — should redirect to `/`, and the nav should revert to
   "Sign in" / "Get started".
7. Confirm a raw `GET /logout` now 405s instead of returning the old
   placeholder text.
8. Restart the app again — confirm no errors and the demo account still
   logs in/out correctly (regression check on `init_db()`/`seed_db()`).

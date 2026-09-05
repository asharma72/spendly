# Implementation Plan: Profile Page (Step 4)

## Context

`/profile` (`app.py:134-136`) is currently a placeholder returning a plain string. `.claude/specs/04-profile-page.md` (current version) asks for a fully designed, **hardcoded-data-only** profile page — user info card, summary stats, transaction history table, category breakdown — behind a login guard. Real DB wiring is explicitly deferred to Step 5; the goal here is just to get the UI/layout right so Step 5 can swap literals for query results.

The spec's own "Files to change" list only names `app.py`, but its Definition of done requires "the navbar shows the logged-in state (username + logout link)" — `base.html`'s logged-in nav branch (lines 25-28) currently renders *only* a bare logout button, no username. So `base.html` (and a 2-line CSS addition in `style.css`) is added to scope to close that gap.

A project skill (`.claude/skills/frontend-design/SKILL.md`) suggests a generic palette and Lucide icons as defaults "when no existing reference exists" — but Spendly already has a full, consistent design system (`style.css` `:root` tokens, `.auth-card`/`.mock-stat`/`.mock-bars-card` patterns) and zero icon-library usage anywhere. Per the skill's own guidance to prefer existing conventions, this plan uses **only the existing token palette and visual language, no icons, no new dependencies**.

## Approach

**Data (`app.py`):** the `/profile` view guards with `if not session.get("user_id"): return redirect(url_for("login"))` (mirrors the existing inverse check in `register`/`login`, app.py:23-24) then passes four hardcoded literals to the template — `user` (name/email/initials/member_since), `stats` (total_spent/transaction_count/top_category), `transactions` (list of 8, shaped like `seed_db()`'s seeded expenses, dates recast to August 2026 so nothing looks "future"), `categories` (list of 7, each with a pre-computed `percent` and a coarser `width_class` rounded to the nearest 10 for picking a CSS width class — no runtime `sum()`/`round()`, no inline `style="width:...\"`, keeping "no inline styles" and "no DB/computation logic" both satisfied literally).

A reusable `login_required` decorator was considered and rejected for now: only one route is protected this step (the other stubs are out of scope until Steps 7-9), so an inline check matches the spec's actual scope; revisit as a decorator once 2-3 routes need it.

**Nav username (`base.html` + `style.css`):** add `<span class="nav-username">Demo User</span>` before the logout form in the `{% else %}` branch, styled with `color: var(--ink-soft); font-weight: 500;`, and added to the existing 600px mobile-hide rule alongside `.logout-link`. This is hardcoded (not derived from session/DB) because showing the *real* signed-in name would require either a DB lookup by `session["user_id"]` (a query, explicitly deferred to Step 5) or writing a new session field in the already-complete login flow — both out of scope. Flagged here so it isn't forgotten when Step 5 wires up real data.

**Template (`templates/profile.html`, new):** extends `base.html`, uses `{% block head %}` to link a new `profile.css`, and renders the four sections purely from Jinja variables — no literal data or hex values anywhere in the template itself. Category badges/bars get their color from CSS classes (`badge-{{ category|lower }}`, `cat-bar-{{ category|lower }}`), never inline styles.

**Styles (`static/css/profile.css`, new):** matches the codebase's existing flat/bordered/no-shadow card language (`.auth-card`, `.mock-stat` precedent — border + `var(--radius-md)`, no box-shadow anywhere). Introduces exactly two new color pairs (`--cat-blue`/`--cat-blue-light`, `--cat-purple`/`--cat-purple-light`, reusing the existing `.mock-bar-travel`/`.mock-bar-bills` hex values `#4f7fd6`/`#7b6fd1` so the new page stays visually consistent with the landing page) for Transport/Entertainment; Food/Shopping/Bills reuse `--accent`/`--accent-2`/`--danger` (+ their existing `-light` variants, currently unused elsewhere); Health/Other reuse the neutral `--ink-muted`/`--border-soft`/`--ink-faint`. Introduces the codebase's first `.table` and `.badge` classes (neither exists yet). Responsive at 900px/600px matching the site's existing breakpoints (600px hides the table's description column rather than the whole table, so it stays usable on narrow screens with zero new JS).

## Files to change
- `app.py` — replace the `/profile` stub (currently lines 134-136, in the "Placeholder routes" block) with the real guarded view + hardcoded context, moved up next to the other implemented routes (after `privacy`).
- `templates/base.html` — add the `.nav-username` span to the logged-in nav branch (lines ~25-28).
- `static/css/style.css` — add `.nav-username` rule near `.logout-link` (~line 122), and add `.nav-username` to the mobile-hide selector at line 704.

## Files to create
- `templates/profile.html` — four sections (user card, stats row, transaction table, category breakdown), all data from template context.
- `static/css/profile.css` — new `:root` block with the two new category color pairs, plus `.profile-*`, `.table`, `.badge`, `.cat-*`, `.bar-w-0`..`.bar-w-100` classes, plus the responsive rules.

No new dependencies. No database changes. No changes to `main.js`, auth routes, or the other stub routes.

## Verification (manual — run the app, no test suite exists in this repo yet)
1. `python app.py` — no startup or template errors.
2. Logged out, visit `/profile` directly → redirected to `/login`.
3. Log in as `demo@spendly.com` / `demo123`, visit `/profile` → HTTP 200.
4. User card shows "Demo User" / "demo@spendly.com" / "Member since August 2026".
5. Stats row shows exactly 3 values (total spent, transaction count, top category).
6. Transaction table shows 8 rows with date/description/badge/right-aligned amount.
7. Category breakdown shows 7 rows with badge, proportional bar, total, percent.
8. Navbar on `/profile` and every other logged-in page shows "Demo User" next to "Logout".
9. View page source of `/profile` and confirm no `#`-hex values appear anywhere in the HTML.
10. Click Logout from `/profile` → redirected to `/`; re-visiting `/profile` redirects to `/login` again.
11. Resize below 900px and 600px — stats stack to one column, card centers, table's description column hides, no layout breakage.
12. Regression pass: `/`, `/login`, `/register`, `/terms`, `/privacy` logged out and logged in — nav still shows "Sign in"/"Get started" when logged out, "Demo User"/"Logout" when logged in, no visual break from the `style.css` change.

### Critical files
- `D:\expense-tracker\app.py`
- `D:\expense-tracker\templates\base.html`
- `D:\expense-tracker\templates\profile.html` (new)
- `D:\expense-tracker\static\css\profile.css` (new)
- `D:\expense-tracker\static\css\style.css`

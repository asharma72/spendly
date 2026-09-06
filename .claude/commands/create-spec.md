---
description: Create a spec file and feature branch for the next Legal Farm step
argument-hint: "Step number and feature name e.g. 6 conversation-search"
allowed-tools: Read, Write, Glob, Bash(git:*)
---

You are a senior developer spinning up a new feature for the
Legal Farm chatbot. Always follow the rules in CLAUDE.md.

User input: $ARGUMENTS

## Step 1 — Check working directory is clean
Run `git status` and check for uncommitted, unstaged, or
untracked files. If any exist, stop immediately and tell
the user to commit or stash changes before proceeding.
DO NOT CONTINUE until the working directory is clean.

## Step 2 — Parse the arguments
From $ARGUMENTS extract:

1. `step_number` — zero-padded to 2 digits: 6 → 06, 11 → 11

2. `feature_title` — human readable title in Title Case
   - Example: "Conversation Search" or "Password Reset"

3. `feature_slug` — git and file safe slug
   - Lowercase, kebab-case
   - Only a-z, 0-9 and -
   - Maximum 40 characters
   - Example: conversation-search, password-reset

4. `branch_name` — format: `feature/<feature_slug>`
   - Example: `feature/conversation-search`

If you cannot infer these from $ARGUMENTS, ask the user
to clarify before proceeding.

## Step 3 — Check branch name is not taken
Run `git branch` to list existing branches.
If `branch_name` is already taken, append a number:
`feature/conversation-search-01`, `feature/conversation-search-02` etc.

## Step 4 — Switch to main and pull latest
Run:
```
git checkout main
git pull origin main
```
If this repo has no remote configured yet or `main` doesn't
exist, skip the pull and note that in the summary rather than
failing.

## Step 5 — Create and switch to the feature branch
Run:
```
git checkout -b <branch_name>
```

## Step 6 — Research the codebase
Read these files before writing the spec:
- `CLAUDE.md` — architecture, conventions, gotchas
- `backend/app.py` — existing FastAPI routes and structure
- `backend/db.py` — existing DB access functions (raw psycopg2)
- `backend/schema.sql` — existing schema
- `backend/llm.py` — system prompt construction, role-based addenda
- `backend/safety.py` — disclaimer injection, high-risk detection
- `backend/auth.py` — auth/token/role-gating patterns
- `frontend/src/api.js` — existing API call conventions
- All files in `.claude/specs/` — avoid duplicating existing specs

Check `CLAUDE.md` and `.claude/specs/` to confirm the requested
feature isn't already specified or implemented. If it is, warn
the user and stop.

## Step 7 — Write the spec
Generate a spec document with this exact structure:

---
# Spec: <feature_title>

## Overview
One paragraph describing what this feature does and why
it's needed for Legal Farm at this stage.

## Depends on
Which previous specs/features this requires to be complete.

## Routes
Every new or modified FastAPI route needed:
- `METHOD /api/path` — description — access level
  (public / any authenticated user / internal-only via
  `auth.require_internal`)

If no new routes: state "No new routes".

## Database changes
Any new tables, columns, or constraints needed in `schema.sql`.
Always verify against the current `schema.sql` before writing
this — remember `db.init_schema()` re-runs this file, so changes
must be idempotent (`CREATE TABLE IF NOT EXISTS`, guarded
`ALTER TABLE`, etc.).
If none: state "No database changes".

## Frontend components
- **Create:** new React components/files under `frontend/src/`
- **Modify:** existing components and what changes
  (e.g. `ChatApp.jsx`, `AdminLogs.jsx`, `api.js`)

## Files to change
Every file that will be modified.

## Files to create
Every new file that will be created.

## New dependencies
Any new pip or npm packages. If none: state "No new dependencies".

## Rules for implementation
Specific constraints Claude must follow. Always include:
- No ORM — raw `psycopg2` via `db.get_conn()`, `RealDictCursor`
- Parameterised queries only, never string-interpolated SQL
- Passwords hashed with `bcrypt` directly (never `passlib`, which
  breaks against modern `bcrypt` releases — see CLAUDE.md gotchas)
- Auth via the existing signed-token pattern
  (`auth.create_token`/`auth.get_current_user`) — do not introduce
  a session table or swap auth mechanisms as part of an unrelated feature
- Role-gating: use `auth.require_internal` for any internal-only route;
  never gate by checking `role` ad hoc in route bodies
- Any new user-facing bot response must pass through
  `safety.apply_disclaimers` before being returned/saved — do not
  bypass this for new routes that return LLM output
- CORS origin in `backend/app.py` is hardcoded to the Vite dev
  server origin — flag if this feature needs an additional origin
- No automated test suite exists yet; if adding one, prefer the
  `TestClient` + monkeypatched `llm.get_response` pattern noted in
  CLAUDE.md over requiring a live DB/Anthropic key

## Definition of done
A specific testable checklist. Each item must be
something that can be verified by running the app locally
(Docker Postgres on port 5433, `uvicorn` backend, `npm run dev` frontend).
---

## Step 8 — Save the spec
Save to: `.claude/specs/<step_number>-<feature_slug>.md`

## Step 9 — Report to the user
Print a short summary in this exact format:
```
Branch:    <branch_name>
Spec file: .claude/specs/<step_number>-<feature_slug>.md
Title:     <feature_title>
```

Then tell the user:
"Review the spec at `.claude/specs/<step_number>-<feature_slug>.md`
then enter Plan Mode with Shift+Tab twice to begin implementation."

Do not print the full spec in chat unless explicitly asked.
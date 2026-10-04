# Spec: Registration

## Overview
Turn the existing static `/register` page into a working sign-up flow. A visitor submits name, email and password; the server validates the input, hashes the password with werkzeug, creates a row in `users`, shown with a success message and sends the visitor to the login page. This is the first step that writes user-supplied data to the database, and it is the prerequisite for login, sessions and every per-user feature that follows.

## Depends on
- Step 01 — Database setup (`users` table, `get_db()`, `init_db()`)

## Routes
- `GET /register` — render the registration form (already exists, unchanged) — public
- `POST /register` — validate the form, create the user, redirect to `/login` on success, re-render the form with an error on failure — public

## Database changes
No database changes. The existing `users` table (`id`, `name`, `email UNIQUE NOT NULL`, `password_hash`, `created_at`) is sufficient. Duplicate emails are rejected by the `UNIQUE` constraint on `email`.

## Templates
- **Create:** none
- **Modify:**
  - `templates/register.html` — keep submitted `name` and `email` in the inputs after a failed submit (never the password); keep the existing `{{ error }}` block; set the `action` with `url_for('register')` instead of the hardcoded path; add `minlength="8"` to the password input
  - `templates/login.html` — show a success message after registration (e.g. "Account created. Please sign in.") if a flash message is present

## Files to change
- `app.py` — accept `POST` on `/register`, add form handling, set `app.secret_key` (needed for flash messages), import `request`, `redirect`, `url_for`, `flash`, `sqlite3`, and `generate_password_hash`
- `templates/register.html`
- `templates/login.html`
- `templates/base.html` — only if a shared flash-message block is needed; otherwise leave it untouched

## Files to create
- `tests/test_registration.py` — pytest tests for the flow (pytest and pytest-flask are already in `requirements.txt`)

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs
- Parameterised queries only — never format user input into SQL
- Passwords hashed with werkzeug (`generate_password_hash`); never store or log the plaintext password
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- Read the secret key from an environment variable (e.g. `SECRET_KEY`) with a development fallback; do not commit a real secret
- Server-side validation (do not rely on HTML attributes alone):
  - `name`: required, trimmed, not empty
  - `email`: required, trimmed, lower-cased before storing, must contain `@` with text on both sides
  - `password`: required, at least 8 characters
- Handle duplicate emails by catching `sqlite3.IntegrityError` (rely on the `UNIQUE` constraint, not a check-then-insert race) and show "An account with this email already exists."
- Always close the connection (`try/finally`), matching the pattern in `database/db.py`
- Do not log the user in on registration; redirect to `/login` (sessions arrive in the login step)
- Return HTTP 400 when re-rendering the form with a validation error

## Definition of done
- [ ] `GET /register` renders the form with name, email and password fields
- [ ] Submitting valid details creates exactly one new row in `users` and redirects to `/login`
- [ ] The stored `password_hash` is a werkzeug hash and does not equal the submitted password
- [ ] `/login` shows the "Account created" message after a successful registration
- [ ] Submitting an email that already exists (in any letter case) shows the duplicate-email error and creates no row
- [ ] Submitting an empty name, an invalid email, or a password shorter than 8 characters shows a clear error and creates no row
- [ ] After a failed submit, the name and email stay filled in and the password field is empty
- [ ] The seeded demo user (`demo@spendly.com`) is unaffected
- [ ] `pytest tests/test_registration.py` passes
- [ ] App starts without errors and no hardcoded hex colours were added
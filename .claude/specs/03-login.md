# Spec: Login

## Overview
Turn the static `/login` page into a working sign-in flow and replace the `/logout` placeholder with a real implementation. A visitor submits email and password; the server looks up the user, verifies the password hash with werkzeug, and stores the user id in the Flask session. Logging out clears the session. This is the first step that introduces authenticated state, and it is the prerequisite for the profile page and every per-user expense feature that follows.

## Depends on
- Step 1 — Database setup (`users` table, `get_db()`, demo user `demo@spendly.com` / `demo123`)
- Step 2 — Registration (users can be created; registration redirects to `/login` with a flashed message). Note: the registration implementation currently lives on `feature/registration-impl` and is not yet merged to `main`. Merge it before implementing this step, since it also adds `app.secret_key` and flash-message support to `app.py`.

## Routes
- `GET /login` — render the sign-in form; redirect to `/profile` if already logged in — public
- `POST /login` — validate credentials, set `session["user_id"]` and `session["user_name"]`, redirect to `/profile`; on failure re-render the form with an error and HTTP 401 — public
- `GET /logout` — clear the session, flash "You have been signed out.", redirect to `/login` — logged-in (harmless if not logged in: just redirects)

## Database changes
No database changes. The existing `users` table (`id`, `name`, `email` UNIQUE, `password_hash`, `created_at`) already supports login.

## Templates
- **Create:** none
- **Modify:**
  - `templates/login.html` — keep the form posting to `/login`; re-fill the email field on error (`value="{{ email }}"`); show flashed messages (e.g. the "Account created" message from registration)
  - `templates/base.html` — when `session.user_id` is set, show the user's name, a link to Profile and a "Sign out" link to `url_for('logout')` instead of "Sign in" / "Get started"

## Files to change
- `app.py` — implement `login` (GET/POST) and `logout`; set `app.secret_key` from the `SECRET_KEY` env var if not already present; import `session`, `request`, `redirect`, `url_for`, `flash`, and `check_password_hash`
- `templates/login.html`
- `templates/base.html`
- `static/css/style.css` — styles for the flash message and the logged-in nav state, using existing CSS variables

## Files to create
- `tests/test_login.py` — pytest coverage for login and logout

## New dependencies
No new dependencies. Flask sessions and `werkzeug.security.check_password_hash` are already available.

## Rules for implementation
- No SQLAlchemy or ORMs
- Parameterised queries only
- Passwords hashed with werkzeug (verify with `check_password_hash`, never compare plaintext)
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- Normalise the email (strip, lowercase) before lookup
- Use one generic error for both unknown email and wrong password ("Invalid email or password.") so accounts cannot be enumerated
- Store only `user_id` and `user_name` in the session; never the password or hash
- Always close the DB connection (`try/finally`)
- Do not implement route protection for other pages in this step

## Definition of done
- [ ] Visiting `/login` shows the sign-in form
- [ ] Signing in as `demo@spendly.com` / `demo123` redirects to `/profile`
- [ ] Email matching is case-insensitive and ignores surrounding whitespace
- [ ] A wrong password shows "Invalid email or password." and keeps the email filled in
- [ ] An unknown email shows the same "Invalid email or password." message
- [ ] Failed login returns HTTP 401 and does not set a session
- [ ] After a successful registration, the flashed "Account created" message appears on `/login`, and the new user can sign in
- [ ] After login the navbar shows the user's name and a "Sign out" link instead of "Sign in" / "Get started"
- [ ] Visiting `/login` while signed in redirects to `/profile`
- [ ] Clicking "Sign out" clears the session, redirects to `/login` and shows a signed-out message; the navbar returns to its logged-out state
- [ ] `/logout` when not signed in simply redirects to `/login` without error
- [ ] `pytest tests/test_login.py` passes

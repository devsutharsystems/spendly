import calendar
import hmac
import math
import os
import secrets
import sqlite3
from datetime import date, datetime, timedelta
from functools import wraps

from flask import (
    Flask,
    abort,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

from database.db import CATEGORIES, get_db, init_db, seed_db
from database.queries import (
    get_category_breakdown,
    get_expense_by_id,
    get_recent_transactions,
    get_summary_stats,
    get_user_by_id,
    insert_expense,
    update_expense,
)

app = Flask(__name__)
# No hardcoded fallback: without SECRET_KEY a random key is used, which only
# means sessions reset when the app restarts.
app.secret_key = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024

MAX_AMOUNT = 10_000_000
MIN_EXPENSE_DATE = date(2000, 1, 1)
MAX_FUTURE_DAYS = 365

with app.app_context():
    init_db()
    seed_db()


# ------------------------------------------------------------------ #
# Helpers                                                             #
# ------------------------------------------------------------------ #


def login_required(view):
    """Redirect to the login page when no user is signed in."""

    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapped


def _csrf_token():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(16)
    return session["csrf_token"]


@app.context_processor
def inject_csrf_token():
    return {"csrf_token": _csrf_token}


@app.before_request
def protect_from_csrf():
    if request.method != "POST":
        return None
    if app.config.get("TESTING") and not app.config.get("CSRF_TEST_ENFORCE"):
        return None
    expected = session.get("csrf_token", "")
    submitted = request.form.get("csrf_token", "")
    if not expected or not hmac.compare_digest(expected, submitted):
        abort(400)
    return None


# ------------------------------------------------------------------ #
# Routes                                                              #
# ------------------------------------------------------------------ #


@app.route("/")
def landing():
    return render_template("landing.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return render_template("register.html")

    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")

    local, _, domain = email.partition("@")
    if not name:
        error = "Please enter your name."
    elif not local or not domain or "@" in domain:
        error = "Please enter a valid email address."
    elif len(password) < 8:
        error = "Password must be at least 8 characters."
    else:
        error = None

    if error:
        return (
            render_template("register.html", error=error, name=name, email=email),
            400,
        )

    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            (name, email, generate_password_hash(password)),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        return (
            render_template(
                "register.html",
                error="An account with this email already exists.",
                name=name,
                email=email,
            ),
            400,
        )
    finally:
        conn.close()

    flash("Account created. Please sign in.")
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id"):
        return redirect(url_for("profile"))

    if request.method == "GET":
        return render_template("login.html")

    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")

    conn = get_db()
    try:
        user = conn.execute(
            "SELECT id, name, password_hash FROM users WHERE email = ?",
            (email,),
        ).fetchone()
    finally:
        conn.close()

    if user is None or not check_password_hash(user["password_hash"], password):
        return (
            render_template(
                "login.html", error="Invalid email or password.", email=email
            ),
            401,
        )

    session.clear()
    session["user_id"] = user["id"]
    session["user_name"] = user["name"]
    return redirect(url_for("profile"))


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been signed out.")
    return redirect(url_for("login"))


@app.route("/terms")
def terms():
    return render_template("terms.html")


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


# ------------------------------------------------------------------ #
# Placeholder routes — students will implement these                  #
# ------------------------------------------------------------------ #


# --- SECTION: transaction history (subagent 1) ---
def _build_transactions(user_id, date_from=None, date_to=None):
    transactions = get_recent_transactions(
        user_id, date_from=date_from, date_to=date_to
    )
    return [
        {
            "id": t["id"],
            "date": datetime.strptime(t["date"][:10], "%Y-%m-%d").strftime("%d %b %Y"),
            "description": t["description"] or "",
            "category": t["category"],
            "amount": f"₹{t['amount']:.2f}",
            "category_class": t["category"].lower(),
        }
        for t in transactions
    ]


# --- SECTION: summary stats (subagent 2) ---
def _build_stats(user_id, date_from=None, date_to=None):
    stats = get_summary_stats(user_id, date_from=date_from, date_to=date_to)
    return {
        "total_spent": f"₹{stats['total_spent']:.2f}",
        "transaction_count": int(stats["transaction_count"]),
        "top_category": stats["top_category"],
    }


# --- SECTION: category breakdown (subagent 3) ---
def _build_categories(user_id, date_from=None, date_to=None):
    categories = []
    for c in get_category_breakdown(user_id, date_from=date_from, date_to=date_to):
        step = min(100, max(0, int(round(c["pct"] / 5.0)) * 5))
        categories.append(
            {
                "name": c["name"],
                "total": "₹{:.2f}".format(c["amount"]),
                "pct": c["pct"],
                "bar_class": "bar-w-{}".format(step),
            }
        )
    return categories


def _parse_date_filter(args):
    """Return ((date_from, date_to), error); dates are ISO strings or None if unusable."""
    parsed = []
    for key in ("date_from", "date_to"):
        value = args.get(key, "").strip()
        try:
            parsed.append(datetime.strptime(value, "%Y-%m-%d").date())
        except ValueError:
            return (None, None), None

    start, end = parsed
    if start > end:
        return (None, None), "Start date must be before end date."
    return (start.isoformat(), end.isoformat()), None


def _months_ago(today, months):
    index = today.year * 12 + today.month - 1 - months
    year, month = divmod(index, 12)
    month += 1
    return date(year, month, min(today.day, calendar.monthrange(year, month)[1]))


def _build_presets(today, date_from, date_to):
    ranges = [
        ("This Month", today.replace(day=1)),
        ("Last 3 Months", _months_ago(today, 3)),
        ("Last 6 Months", _months_ago(today, 6)),
    ]
    presets = []
    for label, start in ranges:
        start_iso, end_iso = start.isoformat(), today.isoformat()
        presets.append(
            {
                "label": label,
                "url": url_for("profile", date_from=start_iso, date_to=end_iso),
                "active": (date_from, date_to) == (start_iso, end_iso),
            }
        )
    presets.append(
        {
            "label": "All Time",
            "url": url_for("profile"),
            "active": date_from is None,
        }
    )
    return presets


@app.route("/profile")
@login_required
def profile():
    user_id = session["user_id"]
    row = get_user_by_id(user_id)
    if row is None:
        session.clear()
        return redirect(url_for("login"))

    user = {
        "name": row["name"],
        "initials": "".join(part[0] for part in row["name"].split()[:2]).upper(),
        "email": row["email"],
        "member_since": row["member_since"],
    }
    (date_from, date_to), filter_error = _parse_date_filter(request.args)
    if filter_error:
        flash(filter_error)
    is_filtered = date_from is not None
    presets = _build_presets(date.today(), date_from, date_to)
    custom_active = is_filtered and not any(p["active"] for p in presets)
    return render_template(
        "profile.html",
        user=user,
        stats=_build_stats(user_id, date_from, date_to),
        transactions=_build_transactions(user_id, date_from, date_to),
        categories=_build_categories(user_id, date_from, date_to),
        date_from=date_from,
        date_to=date_to,
        presets=presets,
        is_filtered=is_filtered,
        custom_active=custom_active,
    )


@app.route("/analytics")
@login_required
def analytics():
    return render_template("analytics.html")


def _validate_expense(form):
    """Return (values, error). values is cleaned only when error is None."""
    values = {
        "amount": form.get("amount", "").strip(),
        "category": form.get("category", ""),
        "date": form.get("date", "").strip(),
        "description": form.get("description", "").strip(),
    }

    try:
        amount = float(values["amount"])
    except ValueError:
        return values, "Please enter an amount greater than 0."
    if not math.isfinite(amount) or amount <= 0:
        return values, "Please enter an amount greater than 0."
    if amount > MAX_AMOUNT:
        return values, "Amount must be at most ₹{:,}.".format(MAX_AMOUNT)

    if values["category"] not in CATEGORIES:
        return values, "Please choose a valid category."

    try:
        expense_date = datetime.strptime(values["date"], "%Y-%m-%d").date()
    except ValueError:
        return values, "Please enter a valid date."
    if expense_date < MIN_EXPENSE_DATE or expense_date > date.today() + timedelta(
        days=MAX_FUTURE_DAYS
    ):
        return values, "Date is out of range."

    if len(values["description"]) > 200:
        return values, "Description must be 200 characters or fewer."

    return {
        **values,
        "amount": round(amount, 2),
        "description": values["description"] or None,
    }, None


@app.route("/expenses/add", methods=["GET", "POST"])
@login_required
def add_expense():
    form = {"date": date.today().isoformat()}
    error = None

    if request.method == "POST":
        form, error = _validate_expense(request.form)
        if error is None:
            insert_expense(
                session["user_id"],
                form["amount"],
                form["category"],
                form["date"],
                form["description"],
            )
            flash("Expense added.", "success")
            return redirect(url_for("profile"))

    return render_template(
        "add_expense.html", categories=CATEGORIES, form=form, error=error
    )


@app.route("/expenses/<int:id>/edit", methods=["GET", "POST"])
@login_required
def edit_expense(id):
    user_id = session["user_id"]
    form = get_expense_by_id(id, user_id)
    if form is None:
        abort(404)
    error = None

    if request.method == "POST":
        form, error = _validate_expense(request.form)
        if error is None:
            update_expense(
                id,
                user_id,
                form["amount"],
                form["category"],
                form["date"],
                form["description"],
            )
            flash("Expense updated.", "success")
            return redirect(url_for("profile"))

    return render_template(
        "edit_expense.html",
        expense_id=id,
        categories=CATEGORIES,
        form=form,
        error=error,
    )


@app.route("/expenses/<int:id>/delete")
def delete_expense(id):
    return "Delete expense — coming in Step 9"


if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1", port=5001)

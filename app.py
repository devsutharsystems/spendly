import calendar
import os
import sqlite3
from datetime import date, datetime

from flask import Flask, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from database.db import get_db, init_db, seed_db
from database.queries import get_user_by_id, get_recent_transactions, get_category_breakdown, get_summary_stats

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-me")

with app.app_context():
    init_db()
    seed_db()


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
        return render_template("register.html", error=error, name=name, email=email), 400

    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            (name, email, generate_password_hash(password)),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        return render_template(
            "register.html",
            error="An account with this email already exists.",
            name=name,
            email=email,
        ), 400
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
        return render_template(
            "login.html", error="Invalid email or password.", email=email
        ), 401

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
    transactions = get_recent_transactions(user_id, date_from=date_from, date_to=date_to)
    return [
        {
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
def profile():
    user_id = session.get("user_id")
    if not user_id:
        return redirect(url_for("login"))

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
def analytics():
    if not session.get("user_id"):
        return redirect(url_for("login"))
    return render_template("analytics.html")


@app.route("/expenses/add")
def add_expense():
    return "Add expense — coming in Step 7"


@app.route("/expenses/<int:id>/edit")
def edit_expense(id):
    return "Edit expense — coming in Step 8"


@app.route("/expenses/<int:id>/delete")
def delete_expense(id):
    return "Delete expense — coming in Step 9"


if __name__ == "__main__":
    app.run(debug=True, port=5001)

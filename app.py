import os
import sqlite3

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
def _build_transactions(user_id):
    from datetime import datetime

    return [
        {
            "date": datetime.strptime(t["date"][:10], "%Y-%m-%d").strftime("%d %b %Y"),
            "description": t["description"] or "",
            "category": t["category"],
            "amount": f"₹{t['amount']:.2f}",
            "category_class": t["category"].lower(),
        }
        for t in get_recent_transactions(user_id)
    ]


# --- SECTION: summary stats (subagent 2) ---
def _build_stats(user_id):
    stats = get_summary_stats(user_id)
    return {
        "total_spent": f"₹{stats['total_spent']:.2f}",
        "transaction_count": int(stats["transaction_count"]),
        "top_category": stats["top_category"],
    }


# --- SECTION: category breakdown (subagent 3) ---
def _build_categories(user_id):
    categories = []
    for c in get_category_breakdown(user_id):
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
    return render_template(
        "profile.html",
        user=user,
        stats=_build_stats(user_id),
        transactions=_build_transactions(user_id),
        categories=_build_categories(user_id),
    )


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

import os
import sqlite3

from flask import Flask, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from database.db import get_db, init_db, seed_db

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

@app.route("/profile")
def profile():
    if not session.get("user_id"):
        return redirect(url_for("login"))

    # Hardcoded display data — Step 5 replaces this with real database queries.
    name = session.get("user_name", "")
    user = {
        "name": name,
        "initials": "".join(part[0] for part in name.split()[:2]).upper(),
        "email": "demo@spendly.com",
        "member_since": "January 2026",
    }
    stats = {
        "total_spent": "₹354.79",
        "transaction_count": 8,
        "top_category": "Bills",
    }
    transactions = [
        {"date": "25 Sep 2026", "description": "Weekly groceries", "category": "Food", "amount": "₹54.30"},
        {"date": "20 Sep 2026", "description": "Gift wrapping", "category": "Other", "amount": "₹9.25"},
        {"date": "15 Sep 2026", "description": "New shoes", "category": "Shopping", "amount": "₹64.99"},
        {"date": "12 Sep 2026", "description": "Movie tickets", "category": "Entertainment", "amount": "₹18.00"},
        {"date": "08 Sep 2026", "description": "Pharmacy", "category": "Health", "amount": "₹30.75"},
        {"date": "05 Sep 2026", "description": "Electricity bill", "category": "Bills", "amount": "₹120.00"},
        {"date": "03 Sep 2026", "description": "Monthly bus pass", "category": "Transport", "amount": "₹45.00"},
        {"date": "01 Sep 2026", "description": "Lunch at cafe", "category": "Food", "amount": "₹12.50"},
    ]
    for txn in transactions:
        txn["category_class"] = txn["category"].lower()
    # bar_class is the share of total spend rounded to the nearest 5, matching .bar-w-N in style.css
    categories = [
        {"name": "Bills", "total": "₹120.00", "bar_class": "bar-w-35"},
        {"name": "Food", "total": "₹66.80", "bar_class": "bar-w-20"},
        {"name": "Shopping", "total": "₹64.99", "bar_class": "bar-w-20"},
        {"name": "Transport", "total": "₹45.00", "bar_class": "bar-w-15"},
        {"name": "Health", "total": "₹30.75", "bar_class": "bar-w-10"},
        {"name": "Entertainment", "total": "₹18.00", "bar_class": "bar-w-5"},
        {"name": "Other", "total": "₹9.25", "bar_class": "bar-w-5"},
    ]
    return render_template(
        "profile.html",
        user=user,
        stats=stats,
        transactions=transactions,
        categories=categories,
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

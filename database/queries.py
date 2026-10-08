from datetime import datetime

from database.db import get_db


def get_user_by_id(user_id):
    """Return {name, email, member_since} for the user, or None if not found."""
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT name, email, created_at FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
    finally:
        conn.close()

    if row is None:
        return None
    created = datetime.strptime(row["created_at"][:10], "%Y-%m-%d")
    return {
        "name": row["name"],
        "email": row["email"],
        "member_since": created.strftime("%B %Y"),
    }


def _date_clause(date_from, date_to):
    """Return (sql_fragment, params) restricting expenses to an inclusive date range."""
    if date_from and date_to:
        return " AND date BETWEEN ? AND ?", [date_from, date_to]
    return "", []


# --- SECTION: transaction history (subagent 1) ---


def get_recent_transactions(user_id, limit=10, date_from=None, date_to=None):
    """Return the user's latest expenses, newest first, as a list of dicts."""
    clause, params = _date_clause(date_from, date_to)
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT id, date, description, category, amount FROM expenses "
            "WHERE user_id = ?" + clause + " ORDER BY date DESC, id DESC LIMIT ?",
            [user_id, *params, limit],
        ).fetchall()
    finally:
        conn.close()

    return [
        {
            "id": r["id"],
            "date": r["date"],
            "description": r["description"],
            "category": r["category"],
            "amount": float(r["amount"]),
        }
        for r in rows
    ]


# --- SECTION: summary stats (subagent 2) ---


def get_summary_stats(user_id, date_from=None, date_to=None):
    """Return {total_spent, transaction_count, top_category} for the user."""
    clause, params = _date_clause(date_from, date_to)
    conn = get_db()
    try:
        totals = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) AS total, COUNT(*) AS cnt "
            "FROM expenses WHERE user_id = ?" + clause,
            [user_id, *params],
        ).fetchone()
        top = conn.execute(
            "SELECT category FROM expenses WHERE user_id = ?"
            + clause
            + " GROUP BY category ORDER BY SUM(amount) DESC, category ASC LIMIT 1",
            [user_id, *params],
        ).fetchone()
    finally:
        conn.close()

    if totals["cnt"] == 0:
        return {"total_spent": 0, "transaction_count": 0, "top_category": "—"}
    return {
        "total_spent": float(totals["total"]),
        "transaction_count": int(totals["cnt"]),
        "top_category": top["category"] if top else "—",
    }


# --- SECTION: category breakdown (subagent 3) ---


def get_category_breakdown(user_id, date_from=None, date_to=None):
    """Return [{name, amount, pct}] ordered by amount DESC; pct sums to 100."""
    clause, params = _date_clause(date_from, date_to)
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT category, SUM(amount) AS total FROM expenses "
            "WHERE user_id = ?" + clause + " GROUP BY category "
            "ORDER BY total DESC, category ASC",
            [user_id, *params],
        ).fetchall()
    finally:
        conn.close()

    grand = sum(r["total"] for r in rows)
    if not rows or grand <= 0:
        return []

    result = [
        {
            "name": r["category"],
            "amount": float(r["total"]),
            "pct": round(r["total"] * 100 / grand),
        }
        for r in rows
    ]
    result[0]["pct"] += 100 - sum(c["pct"] for c in result)
    return result


# --- SECTION: add expense ---


def insert_expense(user_id, amount, category, expense_date, description):
    """Insert an expense for the user and return its new id."""
    conn = get_db()
    try:
        cursor = conn.execute(
            "INSERT INTO expenses (user_id, amount, category, date, description) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, amount, category, expense_date, description),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


# --- SECTION: edit expense ---

def get_expense_by_id(expense_id, user_id):
    """Return the expense as a dict if it belongs to the user, else None."""
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT id, amount, category, date, description FROM expenses "
            "WHERE id = ? AND user_id = ?",
            (expense_id, user_id),
        ).fetchone()
    finally:
        conn.close()

    if row is None:
        return None
    return {
        "id": row["id"],
        "amount": float(row["amount"]),
        "category": row["category"],
        "date": row["date"],
        "description": row["description"],
    }


def update_expense(expense_id, user_id, amount, category, expense_date, description):
    """Update the user's expense; return True if a row was changed."""
    conn = get_db()
    try:
        cursor = conn.execute(
            "UPDATE expenses SET amount = ?, category = ?, date = ?, description = ? "
            "WHERE id = ? AND user_id = ?",
            (amount, category, expense_date, description, expense_id, user_id),
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def delete_expense(expense_id, user_id):
    """Delete the user's expense; return True if a row was removed."""
    conn = get_db()
    try:
        cursor = conn.execute(
            "DELETE FROM expenses WHERE id = ? AND user_id = ?",
            (expense_id, user_id),
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()

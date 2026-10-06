import pytest
from werkzeug.security import generate_password_hash

import app as app_module
from database import db, queries


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "test.db"))
    db.init_db()
    db.seed_db()
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


def add_user(email="new@example.com", name="New User"):
    conn = db.get_db()
    try:
        cur = conn.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            (name, email, generate_password_hash("password123")),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def login(client, email="demo@spendly.com", password="demo123"):
    return client.post("/login", data={"email": email, "password": password})


# ---- query helpers ----

def test_get_user_by_id(client):
    user = queries.get_user_by_id(1)
    assert user["name"] == "Demo User"
    assert user["email"] == "demo@spendly.com"
    assert len(user["member_since"].split()) == 2


def test_get_user_by_id_missing(client):
    assert queries.get_user_by_id(9999) is None


def test_summary_stats_with_expenses(client):
    stats = queries.get_summary_stats(1)
    assert stats["total_spent"] == pytest.approx(354.79)
    assert stats["transaction_count"] == 8
    assert stats["top_category"] == "Bills"


def test_summary_stats_empty(client):
    uid = add_user()
    assert queries.get_summary_stats(uid) == {
        "total_spent": 0,
        "transaction_count": 0,
        "top_category": "—",
    }


def test_recent_transactions_newest_first(client):
    txns = queries.get_recent_transactions(1)
    assert len(txns) == 8
    assert [t["date"] for t in txns] == sorted((t["date"] for t in txns), reverse=True)
    assert set(txns[0]) == {"date", "description", "category", "amount"}


def test_recent_transactions_empty(client):
    assert queries.get_recent_transactions(add_user()) == []


def test_category_breakdown(client):
    cats = queries.get_category_breakdown(1)
    assert len(cats) == 7
    amounts = [c["amount"] for c in cats]
    assert amounts == sorted(amounts, reverse=True)
    assert all(isinstance(c["pct"], int) for c in cats)
    assert sum(c["pct"] for c in cats) == 100


def test_category_breakdown_empty(client):
    assert queries.get_category_breakdown(add_user()) == []


def test_queries_are_scoped_to_user(client):
    uid = add_user()
    conn = db.get_db()
    conn.execute(
        "INSERT INTO expenses (user_id, amount, category, date, description) "
        "VALUES (?, 10, 'Food', '2026-01-01', 'Other user lunch')",
        (uid,),
    )
    conn.commit()
    conn.close()
    assert queries.get_summary_stats(uid)["transaction_count"] == 1
    assert queries.get_summary_stats(1)["transaction_count"] == 8


# ---- /profile route ----

def test_profile_requires_login(client):
    resp = client.get("/profile")
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/login")


def test_profile_shows_real_seed_data(client):
    login(client)
    html = client.get("/profile").get_data(as_text=True)
    assert "Demo User" in html and "demo@spendly.com" in html
    assert "₹354.79" in html
    assert "Bills" in html
    assert html.count('class="cat-row"') == 7
    assert html.index("Weekly groceries") < html.index("Lunch at cafe")


def test_profile_new_user_empty_state(client):
    add_user("fresh@example.com", "Fresh Person")
    login(client, "fresh@example.com", "password123")
    resp = client.get("/profile")
    html = resp.get_data(as_text=True)
    assert resp.status_code == 200
    assert "Fresh Person" in html and "fresh@example.com" in html
    assert "demo@spendly.com" not in html
    assert "₹0.00" in html
    assert "No expenses yet" in html


def test_profile_deleted_user_redirects(client):
    with client.session_transaction() as sess:
        sess["user_id"] = 9999
    resp = client.get("/profile")
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/login")

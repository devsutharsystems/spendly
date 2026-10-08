import pytest
from werkzeug.security import generate_password_hash

import app as app_module
from database import db, queries
from database.db import get_db


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "test.db"))
    db.init_db()
    db.seed_db()
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


@pytest.fixture
def auth(client):
    client.post("/login", data={"email": "demo@spendly.com", "password": "demo123"})
    return client


@pytest.fixture
def other_user_id():
    conn = get_db()
    try:
        cur = conn.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            ("Other", "other@spendly.com", generate_password_hash("password1")),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def demo_user_id():
    conn = get_db()
    try:
        return conn.execute("SELECT id FROM users WHERE email = 'demo@spendly.com'").fetchone()[0]
    finally:
        conn.close()


def first_expense_id():
    conn = get_db()
    try:
        return conn.execute("SELECT id FROM expenses ORDER BY id LIMIT 1").fetchone()[0]
    finally:
        conn.close()


def row(expense_id):
    conn = get_db()
    try:
        return conn.execute("SELECT * FROM expenses WHERE id = ?", (expense_id,)).fetchone()
    finally:
        conn.close()


# ---- query helper ----

def test_delete_expense_owner(client):
    eid = first_expense_id()
    assert queries.delete_expense(eid, demo_user_id()) is True
    assert row(eid) is None


def test_delete_expense_wrong_user(client, other_user_id):
    eid = first_expense_id()
    assert queries.delete_expense(eid, other_user_id) is False
    assert row(eid) is not None


def test_delete_expense_nonexistent(client):
    assert queries.delete_expense(99999, demo_user_id()) is False


# ---- route ----

def test_delete_unauthenticated_redirects_to_login(client):
    eid = first_expense_id()
    resp = client.post(f"/expenses/{eid}/delete")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]
    assert row(eid) is not None


def test_delete_own_expense(auth):
    eid = first_expense_id()
    resp = auth.post(f"/expenses/{eid}/delete")
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/profile")
    assert row(eid) is None


def test_delete_other_users_expense_404(auth, other_user_id):
    conn = get_db()
    try:
        cur = conn.execute(
            "INSERT INTO expenses (user_id, amount, category, date) VALUES (?, 5, 'Food', '2026-01-01')",
            (other_user_id,),
        )
        conn.commit()
        eid = cur.lastrowid
    finally:
        conn.close()
    assert auth.post(f"/expenses/{eid}/delete").status_code == 404
    assert row(eid) is not None


def test_delete_nonexistent_404(auth):
    assert auth.post("/expenses/99999/delete").status_code == 404


def test_delete_get_not_allowed(auth):
    eid = first_expense_id()
    assert auth.get(f"/expenses/{eid}/delete").status_code == 405
    assert row(eid) is not None


def test_delete_requires_csrf_token(auth):
    eid = first_expense_id()
    app_module.app.config["CSRF_TEST_ENFORCE"] = True
    try:
        assert auth.post(f"/expenses/{eid}/delete").status_code == 400
    finally:
        app_module.app.config["CSRF_TEST_ENFORCE"] = False
    assert row(eid) is not None


def test_profile_shows_delete_button(auth):
    body = auth.get("/profile").get_data(as_text=True)
    assert "txn-delete" in body
    assert "/delete" in body

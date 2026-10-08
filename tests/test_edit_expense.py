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


VALID = {"amount": "99.5", "category": "Bills", "date": "2026-04-01", "description": "Updated"}


# ---- query helpers ----

def test_get_expense_by_id_owner(client):
    eid = first_expense_id()
    result = queries.get_expense_by_id(eid, demo_user_id())
    assert result["id"] == eid
    assert result["category"] == "Food"


def test_get_expense_by_id_wrong_user(client, other_user_id):
    assert queries.get_expense_by_id(first_expense_id(), other_user_id) is None


def test_get_expense_by_id_missing(client):
    assert queries.get_expense_by_id(99999, demo_user_id()) is None


def test_update_expense_owner(client):
    eid = first_expense_id()
    assert queries.update_expense(eid, demo_user_id(), 99.0, "Bills", "2026-04-01", None)
    r = row(eid)
    assert r["amount"] == 99.0 and r["category"] == "Bills" and r["description"] is None


def test_update_expense_wrong_user(client, other_user_id):
    eid = first_expense_id()
    before = tuple(row(eid))
    assert queries.update_expense(eid, other_user_id, 99.0, "Bills", "2026-04-01", "x") is False
    assert tuple(row(eid)) == before


# ---- routes ----

def test_get_unauthenticated_redirects(client):
    r = client.get("/expenses/1/edit")
    assert r.status_code == 302 and "/login" in r.headers["Location"]


def test_post_unauthenticated_redirects(client):
    r = client.post("/expenses/1/edit", data=VALID)
    assert r.status_code == 302 and "/login" in r.headers["Location"]


def test_get_prefilled(auth):
    eid = first_expense_id()
    r = auth.get(f"/expenses/{eid}/edit")
    body = r.get_data(as_text=True)
    assert r.status_code == 200
    assert "Lunch at cafe" in body
    assert 'value="12.5"' in body
    assert '<option value="Food" selected>' in body
    assert 'name="csrf_token"' in body


def test_get_other_users_expense_404(auth, other_user_id):
    conn = get_db()
    cur = conn.execute(
        "INSERT INTO expenses (user_id, amount, category, date) VALUES (?, 5, 'Food', '2026-01-01')",
        (other_user_id,),
    )
    conn.commit()
    conn.close()
    assert auth.get(f"/expenses/{cur.lastrowid}/edit").status_code == 404


def test_get_missing_404(auth):
    assert auth.get("/expenses/99999/edit").status_code == 404


def test_post_other_users_expense_404_and_unchanged(auth, other_user_id):
    conn = get_db()
    cur = conn.execute(
        "INSERT INTO expenses (user_id, amount, category, date) VALUES (?, 5, 'Food', '2026-01-01')",
        (other_user_id,),
    )
    conn.commit()
    conn.close()
    assert auth.post(f"/expenses/{cur.lastrowid}/edit", data=VALID).status_code == 404
    assert row(cur.lastrowid)["amount"] == 5


def test_post_valid_updates(auth):
    eid = first_expense_id()
    r = auth.post(f"/expenses/{eid}/edit", data=VALID)
    assert r.status_code == 302 and "/profile" in r.headers["Location"]
    updated = row(eid)
    assert updated["amount"] == 99.5
    assert updated["category"] == "Bills"
    assert updated["date"] == "2026-04-01"
    assert updated["description"] == "Updated"


def test_post_blank_description_stored_null(auth):
    eid = first_expense_id()
    r = auth.post(f"/expenses/{eid}/edit", data={**VALID, "description": "  "})
    assert r.status_code == 302
    assert row(eid)["description"] is None


@pytest.mark.parametrize(
    "override",
    [
        {"amount": ""},
        {"amount": "0"},
        {"amount": "abc"},
        {"category": "Nope"},
        {"date": "not-a-date"},
    ],
)
def test_post_invalid_rerenders_with_error(auth, override):
    eid = first_expense_id()
    before = tuple(row(eid))
    r = auth.post(f"/expenses/{eid}/edit", data={**VALID, **override})
    assert r.status_code == 200
    assert 'class="auth-error"' in r.get_data(as_text=True)
    assert tuple(row(eid)) == before


def test_post_invalid_keeps_submitted_values(auth):
    eid = first_expense_id()
    r = auth.post(f"/expenses/{eid}/edit", data={**VALID, "category": "Nope"})
    assert 'value="Updated"' in r.get_data(as_text=True)


def test_post_requires_csrf(auth):
    app_module.app.config["CSRF_TEST_ENFORCE"] = True
    try:
        assert auth.post(f"/expenses/{first_expense_id()}/edit", data=VALID).status_code == 400
    finally:
        app_module.app.config["CSRF_TEST_ENFORCE"] = False


def test_profile_has_edit_links(auth):
    eid = first_expense_id()
    assert f'href="/expenses/{eid}/edit"' in auth.get("/profile").get_data(as_text=True)

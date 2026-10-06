import pytest

import app as app_module
from database import db, queries
from database.db import CATEGORIES, get_db


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


VALID = {"amount": "50.0", "category": "Food", "date": "2026-03-20", "description": "Lunch"}


def fetch_expense(date="2026-03-20"):
    conn = get_db()
    try:
        return conn.execute(
            "SELECT * FROM expenses WHERE date = ? AND amount = 50.0", (date,)
        ).fetchall()
    finally:
        conn.close()


def count_expenses():
    conn = get_db()
    try:
        return conn.execute("SELECT COUNT(*) FROM expenses").fetchone()[0]
    finally:
        conn.close()


# --- insert_expense ------------------------------------------------- #

def test_insert_expense_stores_row(client):
    new_id = queries.insert_expense(1, 50.0, "Food", "2026-03-20", "Lunch")
    conn = get_db()
    row = conn.execute("SELECT * FROM expenses WHERE id = ?", (new_id,)).fetchone()
    conn.close()
    assert (row["user_id"], row["amount"], row["category"], row["date"], row["description"]) == (
        1, 50.0, "Food", "2026-03-20", "Lunch",
    )


def test_insert_expense_null_description(client):
    new_id = queries.insert_expense(1, 50.0, "Food", "2026-03-20", None)
    conn = get_db()
    row = conn.execute("SELECT description FROM expenses WHERE id = ?", (new_id,)).fetchone()
    conn.close()
    assert row["description"] is None


# --- auth ----------------------------------------------------------- #

def test_get_unauthenticated_redirects_to_login(client):
    resp = client.get("/expenses/add")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_post_unauthenticated_redirects_and_saves_nothing(client):
    before = count_expenses()
    resp = client.post("/expenses/add", data=VALID)
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]
    assert count_expenses() == before


# --- GET ------------------------------------------------------------ #

def test_get_authenticated_shows_form(auth):
    resp = auth.get("/expenses/add")
    body = resp.get_data(as_text=True)
    assert resp.status_code == 200
    assert "<form" in body and 'method="POST"' in body
    for category in CATEGORIES:
        assert f'<option value="{category}"' in body


# --- POST valid ----------------------------------------------------- #

def test_post_valid_redirects_and_inserts(auth):
    resp = auth.post("/expenses/add", data=VALID)
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/profile")
    rows = fetch_expense()
    assert len(rows) == 1
    assert rows[0]["description"] == "Lunch"
    assert rows[0]["user_id"] == 1


def test_post_without_description_stores_null(auth):
    resp = auth.post("/expenses/add", data={**VALID, "description": "  "})
    assert resp.status_code == 302
    assert fetch_expense()[0]["description"] is None


def test_new_expense_shown_on_profile_with_success_flash(auth):
    resp = auth.post("/expenses/add", data={**VALID, "description": "Zebra lunch"}, follow_redirects=True)
    body = resp.get_data(as_text=True)
    assert "Zebra lunch" in body
    assert "Expense added." in body
    assert 'class="auth-success"' in body


# --- POST invalid --------------------------------------------------- #

@pytest.mark.parametrize(
    "override",
    [
        {"amount": ""},
        {"amount": "0"},
        {"amount": "-5"},
        {"amount": "abc"},
        {"amount": "nan"},
        {"amount": "inf"},
        {"category": "Gambling"},
        {"category": ""},
        {"date": "not-a-date"},
        {"date": ""},
        {"description": "x" * 201},
        {"amount": "1e308"},
        {"amount": "10000000.01"},
        {"date": "0001-01-01"},
        {"date": "9999-12-31"},
    ],
)
def test_post_invalid_rerenders_with_error(auth, override):
    before = count_expenses()
    resp = auth.post("/expenses/add", data={**VALID, **override})
    body = resp.get_data(as_text=True)
    assert resp.status_code == 200
    assert 'class="auth-error"' in body
    assert count_expenses() == before


def test_invalid_post_preserves_values(auth):
    resp = auth.post("/expenses/add", data={**VALID, "category": "Bills", "amount": "0"})
    body = resp.get_data(as_text=True)
    assert 'value="Lunch"' in body
    assert '<option value="Bills" selected>' in body


# --- navigation ----------------------------------------------------- #

def test_nav_and_profile_link_to_add_expense(auth):
    body = auth.get("/profile").get_data(as_text=True)
    assert body.count('href="/expenses/add"') >= 2


@pytest.mark.parametrize("category", CATEGORIES)
def test_each_category_accepted(auth, category):
    resp = auth.post("/expenses/add", data={**VALID, "category": category})
    assert resp.status_code == 302


def test_description_is_stripped(auth):
    auth.post("/expenses/add", data={**VALID, "description": "  Lunch  "})
    assert fetch_expense()[0]["description"] == "Lunch"


def test_sql_injection_description_stored_literally(auth):
    evil = "x'); DROP TABLE expenses; --"
    auth.post("/expenses/add", data={**VALID, "description": evil})
    assert fetch_expense()[0]["description"] == evil


def test_nav_link_hidden_when_logged_out(client):
    assert "/expenses/add" not in client.get("/login").get_data(as_text=True)


# --- CSRF ----------------------------------------------------------- #

def test_post_without_csrf_token_rejected(auth):
    app_module.app.config["CSRF_TEST_ENFORCE"] = True
    try:
        before = count_expenses()
        assert auth.post("/expenses/add", data=VALID).status_code == 400
        assert count_expenses() == before
    finally:
        app_module.app.config["CSRF_TEST_ENFORCE"] = False


def test_post_with_valid_csrf_token_accepted(auth):
    app_module.app.config["CSRF_TEST_ENFORCE"] = True
    try:
        body = auth.get("/expenses/add").get_data(as_text=True)
        token = body.split('name="csrf_token" value="')[1].split('"')[0]
        resp = auth.post("/expenses/add", data={**VALID, "csrf_token": token})
        assert resp.status_code == 302
    finally:
        app_module.app.config["CSRF_TEST_ENFORCE"] = False

import pytest
from werkzeug.security import check_password_hash

import app as app_module
from database import db


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "test.db"))
    db.init_db()
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


def users():
    conn = db.get_db()
    try:
        return conn.execute("SELECT * FROM users").fetchall()
    finally:
        conn.close()


def register(client, name="Asha Rao", email="asha@example.com", password="password123"):
    return client.post("/register", data={"name": name, "email": email, "password": password})


def test_get_register_renders_form(client):
    resp = client.get("/register")
    assert resp.status_code == 200
    for field in (b'name="name"', b'name="email"', b'name="password"'):
        assert field in resp.data


def test_valid_registration_creates_hashed_user_and_redirects(client):
    resp = register(client)
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/login")
    rows = users()
    assert len(rows) == 1
    assert rows[0]["password_hash"] != "password123"
    assert check_password_hash(rows[0]["password_hash"], "password123")


def test_login_shows_success_message(client):
    resp = client.post(
        "/register",
        data={"name": "Asha Rao", "email": "asha@example.com", "password": "password123"},
        follow_redirects=True,
    )
    assert b"Account created" in resp.data


def test_duplicate_email_is_rejected_case_insensitively(client):
    register(client, email="a@x.com")
    resp = register(client, email="A@X.com")
    assert resp.status_code == 400
    assert b"already exists" in resp.data
    assert len(users()) == 1


def test_repeat_submit_gives_error_not_500(client):
    register(client)
    assert register(client).status_code == 400


@pytest.mark.parametrize(
    "kwargs",
    [
        {"name": ""},
        {"name": "   "},
        {"email": "foo"},
        {"email": "@x.com"},
        {"email": "a@"},
        {"password": "1234567"},
    ],
)
def test_invalid_input_is_rejected(client, kwargs):
    resp = register(client, **kwargs)
    assert resp.status_code == 400
    assert b"auth-error" in resp.data
    assert users() == []


def test_failed_submit_keeps_name_and_email_but_not_password(client):
    resp = register(client, name="Asha Rao", email="asha@example.com", password="short")
    assert b'value="Asha Rao"' in resp.data
    assert b'value="asha@example.com"' in resp.data
    assert b"short" not in resp.data.replace(b"Min. 8 characters", b"")


def test_demo_user_is_unaffected(client):
    db.seed_db()
    register(client)
    emails = [r["email"] for r in users()]
    assert emails.count("demo@spendly.com") == 1
    assert "asha@example.com" in emails

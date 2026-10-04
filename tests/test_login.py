import pytest

import app as app_module
from database import db


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "test.db"))
    db.init_db()
    db.seed_db()
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


def login(client, email="demo@spendly.com", password="demo123"):
    return client.post("/login", data={"email": email, "password": password})


def test_get_login_renders_form(client):
    resp = client.get("/login")
    assert resp.status_code == 200
    assert b'name="email"' in resp.data
    assert b'name="password"' in resp.data


def test_valid_login_sets_session_and_redirects(client):
    resp = login(client)
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/profile")
    with client.session_transaction() as sess:
        assert sess["user_id"] == 1
        assert sess["user_name"] == "Demo User"


def test_email_is_normalised(client):
    resp = login(client, email="  Demo@Spendly.com ")
    assert resp.status_code == 302


def test_wrong_password_returns_401_without_session(client):
    resp = login(client, password="wrong-password")
    assert resp.status_code == 401
    assert b"Invalid email or password." in resp.data
    assert b'value="demo@spendly.com"' in resp.data
    with client.session_transaction() as sess:
        assert "user_id" not in sess


def test_unknown_email_gives_same_error(client):
    resp = login(client, email="nobody@example.com")
    assert resp.status_code == 401
    assert b"Invalid email or password." in resp.data
    with client.session_transaction() as sess:
        assert "user_id" not in sess


def test_login_page_redirects_when_signed_in(client):
    login(client)
    resp = client.get("/login")
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/profile")


def test_registered_user_sees_flash_and_can_sign_in(client):
    client.post(
        "/register",
        data={"name": "Asha Rao", "email": "asha@example.com", "password": "password123"},
    )
    page = client.get("/login")
    assert b"Account created" in page.data
    resp = login(client, email="asha@example.com", password="password123")
    assert resp.status_code == 302


def test_navbar_reflects_auth_state(client):
    out = client.get("/").data
    assert b"Sign in" in out and b"Sign out" not in out
    login(client)
    inn = client.get("/").data
    assert b"Sign out" in inn and b"Demo User" in inn
    assert b"Get started" not in inn


def test_logout_clears_session_and_flashes(client):
    login(client)
    resp = client.get("/logout")
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/login")
    with client.session_transaction() as sess:
        assert "user_id" not in sess
    assert b"You have been signed out." in client.get("/login").data


def test_logout_when_signed_out_redirects(client):
    resp = client.get("/logout")
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/login")

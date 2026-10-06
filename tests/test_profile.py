import re

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


def test_profile_redirects_when_signed_out(client):
    resp = client.get("/profile")
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/login")


def test_profile_renders_when_signed_in(client):
    login(client)
    resp = client.get("/profile")
    assert resp.status_code == 200
    assert b"demo@spendly.com" in resp.data
    assert b"Demo User" in resp.data
    assert b"Total spent" in resp.data
    assert b"Sign out" in resp.data


def test_profile_has_transactions_and_categories(client):
    login(client)
    html = client.get("/profile").data.decode()
    assert html.count('class="badge ') >= 3
    assert html.count('class="cat-row"') >= 3


def test_profile_has_no_inline_styles_or_hex_colours(client):
    login(client)
    html = client.get("/profile").data.decode()
    assert 'style="' not in html
    assert not re.search(r"#[0-9a-fA-F]{3,6}\b", html)


def test_profile_shows_stats_and_rows(client):
    login(client)
    html = client.get("/profile").data.decode()
    assert "₹354.79" in html
    assert "Top category" in html
    assert html.count("<tr>") >= 4  # header + at least 3 transactions

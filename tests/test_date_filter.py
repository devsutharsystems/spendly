import re
from datetime import date

import pytest

import app as app_module
from database import db, queries


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "test.db"))
    db.init_db()
    db.seed_db()
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


def login(client):
    return client.post("/login", data={"email": "demo@spendly.com", "password": "demo123"})


def day(d):
    return date.today().replace(day=d).isoformat()


def rng(start_day, end_day):
    return f"/profile?date_from={day(start_day)}&date_to={day(end_day)}"


# --- query helpers -------------------------------------------------- #

def test_stats_range_is_inclusive():
    stats = queries.get_summary_stats(1, day(5), day(15))
    # Bills 120.00 (5), Health 30.75 (8), Entertainment 18.00 (12), Shopping 64.99 (15)
    assert stats["transaction_count"] == 4
    assert stats["total_spent"] == pytest.approx(233.74)
    assert stats["top_category"] == "Bills"


def test_transactions_filtered_newest_first():
    rows = queries.get_recent_transactions(1, date_from=day(5), date_to=day(15))
    assert [r["date"] for r in rows] == [day(15), day(12), day(8), day(5)]


def test_breakdown_filtered_pct_sums_to_100():
    cats = queries.get_category_breakdown(1, day(1), day(20))
    assert sum(c["pct"] for c in cats) == 100


def test_no_match_range_returns_zeros():
    assert queries.get_summary_stats(1, "1999-01-01", "1999-01-31") == {
        "total_spent": 0, "transaction_count": 0, "top_category": "—",
    }
    assert queries.get_recent_transactions(1, date_from="1999-01-01", date_to="1999-01-31") == []
    assert queries.get_category_breakdown(1, "1999-01-01", "1999-01-31") == []


def test_unfiltered_unchanged():
    assert queries.get_summary_stats(1)["transaction_count"] == 8


# --- route ---------------------------------------------------------- #

def test_unauthenticated_with_params_redirects(client):
    resp = client.get(rng(1, 5))
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/login")


def test_no_params_is_all_time(client):
    login(client)
    html = client.get("/profile").get_data(as_text=True)
    assert "₹354.79" in html


def test_valid_range_filters_all_sections(client):
    login(client)
    html = client.get(rng(5, 15)).get_data(as_text=True)
    assert "₹233.74" in html
    assert "Electricity bill" in html
    assert "Lunch at cafe" not in html
    assert "Weekly groceries" not in html
    assert "Food" not in re.sub(r"<option.*?</option>", "", html)


def test_empty_range_shows_empty_state(client):
    login(client)
    html = client.get("/profile?date_from=1999-01-01&date_to=1999-01-31").get_data(as_text=True)
    assert "₹0.00" in html
    assert html.count("No expenses in this period.") == 2


def test_reversed_range_flashes_and_falls_back(client):
    login(client)
    html = client.get(f"/profile?date_from={day(15)}&date_to={day(5)}").get_data(as_text=True)
    assert "Start date must be before end date." in html
    assert "₹354.79" in html


@pytest.mark.parametrize(
    "qs",
    [
        "date_from=not-a-date&date_to=2026-01-01",
        "date_from=2026-13-45&date_to=2026-14-99",
        "date_from=2026-01-01",
        "date_from=' OR 1=1 --&date_to=' OR 1=1 --",
    ],
)
def test_malformed_params_fall_back(client, qs):
    login(client)
    resp = client.get("/profile?" + qs)
    assert resp.status_code == 200
    assert "₹354.79" in resp.get_data(as_text=True)


def test_presets_rendered_and_all_time_is_clean(client):
    login(client)
    html = client.get("/profile").get_data(as_text=True)
    for label in ("This Month", "Last 3 Months", "Last 6 Months", "All Time"):
        assert label in html
    assert re.search(r'href="/profile"[^>]*>All Time', html) or 'href="/profile" class="filter-preset active">All Time' in html


def test_this_month_preset_is_active(client):
    login(client)
    start = date.today().replace(day=1).isoformat()
    html = client.get(f"/profile?date_from={start}&date_to={date.today().isoformat()}").get_data(as_text=True)
    assert 'filter-preset active">This Month' in html


def test_months_ago_clamps_day():
    assert app_module._months_ago(date(2026, 5, 31), 3) == date(2026, 2, 28)
    assert app_module._months_ago(date(2026, 2, 10), 6) == date(2025, 8, 10)

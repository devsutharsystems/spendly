"""Tests for Step 6: date-range filter on GET /profile (date_from / date_to)."""
import re
import sqlite3
from datetime import date

import pytest

import app as app_module
from database import db

SEED = {1: 12.50, 3: 45.00, 5: 120.00, 8: 30.75, 12: 18.00, 15: 64.99, 20: 9.25, 25: 54.30}
SEED_TOTAL = 354.79


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "test.db"))
    db.init_db()
    db.seed_db()
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


@pytest.fixture
def auth_client(client):
    client.post("/login", data={"email": "demo@spendly.com", "password": "demo123"})
    return client


def day(d):
    return date.today().replace(day=d).isoformat()


def money(x):
    return f"₹{x:.2f}"


def get_profile(client, **params):
    return client.get("/profile", query_string=params, follow_redirects=True)


def html_of(resp):
    return resp.data.decode()


def assert_unfiltered(html):
    assert money(SEED_TOTAL) in html, "Expected unfiltered total"
    for amt in SEED.values():
        assert money(amt) in html, f"Expected {money(amt)} in unfiltered view"


def expense_count(path):
    conn = sqlite3.connect(path)
    try:
        return conn.execute("SELECT COUNT(*) FROM expenses").fetchone()[0]
    finally:
        conn.close()


def expense_rows(path):
    conn = sqlite3.connect(path)
    try:
        return conn.execute(
            "SELECT id, user_id, amount, category, date FROM expenses ORDER BY id"
        ).fetchall()
    finally:
        conn.close()


class TestAuthGuard:
    @pytest.mark.parametrize("params", [
        {},
        {"date_from": "2020-01-01", "date_to": "2030-01-01"},
        {"date_from": "garbage"},
    ])
    def test_profile_with_filter_redirects_to_login_when_signed_out(self, client, params):
        resp = client.get("/profile", query_string=params)
        assert resp.status_code == 302, "Signed-out request must redirect"
        assert resp.headers["Location"].endswith("/login")


class TestUnfiltered:
    def test_no_params_shows_all_expenses(self, auth_client):
        resp = get_profile(auth_client)
        assert resp.status_code == 200
        assert_unfiltered(html_of(resp))

    def test_wide_range_matches_unfiltered_totals(self, auth_client):
        resp = get_profile(auth_client, date_from="2000-01-01", date_to="2999-12-31")
        assert resp.status_code == 200
        assert_unfiltered(html_of(resp))


class TestCustomRange:
    def test_range_shows_only_expenses_inside(self, auth_client):
        resp = get_profile(auth_client, date_from=day(3), date_to=day(12))
        assert resp.status_code == 200
        html = html_of(resp)
        included = [SEED[3], SEED[5], SEED[8], SEED[12]]
        excluded = [SEED[1], SEED[15], SEED[20], SEED[25]]
        assert money(sum(included)) in html, "Total should be sum of in-range expenses"
        for amt in included:
            assert money(amt) in html, f"{money(amt)} should be listed"
        for amt in excluded:
            assert money(amt) not in html, f"{money(amt)} should be filtered out"
        assert money(SEED_TOTAL) not in html

    def test_range_bounds_are_inclusive(self, auth_client):
        html = html_of(get_profile(auth_client, date_from=day(5), date_to=day(5)))
        assert money(SEED[5]) in html, "Single-day range should include that day"
        for d, amt in SEED.items():
            if d != 5:
                assert money(amt) not in html, f"{money(amt)} should be excluded"

    def test_range_lower_bound_inclusive_upper_exclusive_of_next(self, auth_client):
        html = html_of(get_profile(auth_client, date_from=day(15), date_to=day(24)))
        assert money(SEED[15]) in html
        assert money(SEED[20]) in html
        assert money(SEED[25]) not in html
        assert money(SEED[12]) not in html

    def test_range_filters_category_breakdown_too(self, auth_client):
        full = html_of(get_profile(auth_client))
        narrow = html_of(get_profile(auth_client, date_from=day(5), date_to=day(5)))
        assert full.count('class="cat-row"') > narrow.count('class="cat-row"'), (
            "Narrow range should yield fewer category rows"
        )
        assert narrow.count('class="cat-row"') == 1

    def test_range_filters_transaction_rows(self, auth_client):
        full = html_of(get_profile(auth_client))
        narrow = html_of(get_profile(auth_client, date_from=day(3), date_to=day(5)))
        assert narrow.count("<tr>") < full.count("<tr>")
        # header + 2 transactions
        assert narrow.count("<tr>") == 3

    def test_rupee_symbol_shown_when_filtered(self, auth_client):
        html = html_of(get_profile(auth_client, date_from=day(3), date_to=day(12)))
        assert "₹" in html

    def test_filter_values_reflected_in_inputs(self, auth_client):
        html = html_of(get_profile(auth_client, date_from=day(3), date_to=day(12)))
        assert f'value="{day(3)}"' in html, "date_from should be echoed in input"
        assert f'value="{day(12)}"' in html, "date_to should be echoed in input"


class TestEmptyRange:
    @pytest.mark.parametrize("frm,to", [
        ("2000-01-01", "2000-12-31"),
        ("2999-01-01", "2999-12-31"),
    ])
    def test_range_with_no_expenses_shows_zero_without_error(self, auth_client, frm, to):
        resp = get_profile(auth_client, date_from=frm, date_to=to)
        assert resp.status_code == 200
        html = html_of(resp)
        assert money(0) in html, "Expected ₹0.00 total"
        assert money(SEED_TOTAL) not in html
        for amt in SEED.values():
            assert money(amt) not in html
        assert html.count('class="cat-row"') == 0, "Category breakdown should be empty"

    def test_gap_between_expenses_is_empty(self, auth_client):
        resp = get_profile(auth_client, date_from=day(2), date_to=day(2))
        assert resp.status_code == 200
        html = html_of(resp)
        assert money(0) in html
        assert html.count('class="cat-row"') == 0


class TestInvalidInput:
    @pytest.mark.parametrize("params", [
        {"date_from": "not-a-date"},
        {"date_to": "not-a-date"},
        {"date_from": "not-a-date", "date_to": "also-bad"},
        {"date_from": "2025-02-30", "date_to": "2025-03-01"},
        {"date_from": "2025/01/01", "date_to": "2025/12/31"},
        {"date_from": "", "date_to": ""},
        {"date_from": "01-01-2025", "date_to": "31-12-2025"},
        {"date_from": "x" * 5000},
    ])
    def test_malformed_dates_fall_back_to_unfiltered(self, auth_client, params):
        resp = get_profile(auth_client, **params)
        assert resp.status_code == 200, "Malformed dates must not crash the app"
        assert_unfiltered(html_of(resp))

    @pytest.mark.parametrize("params", [
        {"date_from": day(3)},
        {"date_to": day(12)},
    ])
    def test_only_one_bound_falls_back_to_unfiltered(self, auth_client, params):
        resp = get_profile(auth_client, **params)
        assert resp.status_code == 200
        assert_unfiltered(html_of(resp))

    def test_from_after_to_falls_back_and_flashes_error(self, auth_client):
        resp = get_profile(auth_client, date_from=day(20), date_to=day(5))
        assert resp.status_code == 200
        html = html_of(resp)
        assert "Start date must be before end date." in html
        assert_unfiltered(html)

    def test_valid_range_does_not_flash_error(self, auth_client):
        html = html_of(get_profile(auth_client, date_from=day(3), date_to=day(12)))
        assert "Start date must be before end date." not in html

    @pytest.mark.parametrize("payload", [
        "2020-01-01' OR '1'='1",
        "'; DROP TABLE expenses; --",
        "1; DELETE FROM expenses",
    ])
    def test_sql_injection_attempt_is_harmless(self, auth_client, payload):
        resp = get_profile(auth_client, date_from=payload, date_to=payload)
        assert resp.status_code == 200
        assert_unfiltered(html_of(resp))
        assert expense_count(db.DB_PATH) == len(SEED), "Expenses must be intact"


class TestPresets:
    def test_filter_bar_has_all_presets_and_date_inputs(self, auth_client):
        html = html_of(get_profile(auth_client))
        for label in ("This Month", "Last 3 Months", "Last 6 Months", "All Time"):
            assert label in html, f"Missing preset: {label}"
        assert html.count('type="date"') >= 2
        assert 'name="date_from"' in html
        assert 'name="date_to"' in html
        assert "Apply" in html

    def test_custom_form_submits_via_get(self, auth_client):
        html = html_of(get_profile(auth_client))
        assert re.search(r'<form[^>]*method="get"', html, re.I), (
            "Filter form should submit with GET"
        )

    def test_all_time_preset_link_is_clean_profile_url(self, auth_client):
        html = html_of(get_profile(auth_client, date_from=day(3), date_to=day(12)))
        anchors = re.findall(r'<a\b[^>]*href="([^"]*)"[^>]*>\s*All Time\s*</a>', html, re.S)
        assert anchors, "All Time should be a link"
        assert anchors[0].rstrip("?") == "/profile", "All Time must carry no query params"

    @pytest.mark.parametrize("label", ["This Month", "Last 3 Months", "Last 6 Months"])
    def test_date_presets_link_to_profile_with_both_params(self, auth_client, label):
        html = html_of(get_profile(auth_client))
        anchors = re.findall(
            r'<a\b[^>]*href="([^"]*)"[^>]*>\s*' + re.escape(label) + r"\s*</a>", html, re.S
        )
        assert anchors, f"{label} should be a link"
        href = anchors[0].replace("&amp;", "&")
        assert href.startswith("/profile?")
        assert "date_from=" in href and "date_to=" in href

    def _follow_preset(self, client, label):
        html = html_of(get_profile(client))
        href = re.findall(
            r'<a\b[^>]*href="([^"]*)"[^>]*>\s*' + re.escape(label) + r"\s*</a>", html, re.S
        )[0].replace("&amp;", "&")
        return client.get(href)

    def test_this_month_preset_only_includes_current_month_expenses(self, auth_client):
        resp = self._follow_preset(auth_client, "This Month")
        assert resp.status_code == 200
        html = html_of(resp)
        today = date.today().day
        # All seed rows are in the current month; the window may end today or
        # at month end, so accept either, but nothing before day 1 exists.
        up_to_today = round(sum(a for d, a in SEED.items() if d <= today), 2)
        assert (money(up_to_today) in html) or (money(SEED_TOTAL) in html), (
            "This Month total should match current month's expenses"
        )

    @pytest.mark.parametrize("label", ["Last 3 Months", "Last 6 Months"])
    def test_multi_month_presets_include_current_month_to_date(self, auth_client, label):
        resp = self._follow_preset(auth_client, label)
        assert resp.status_code == 200
        html = html_of(resp)
        today = date.today().day
        for d, amt in SEED.items():
            if d <= today:
                assert money(amt) in html, f"{money(amt)} (day {d}) should be in {label}"

    def test_active_state_indicated_for_default_and_filtered(self, auth_client):
        default = html_of(get_profile(auth_client)).lower()
        filtered = html_of(get_profile(auth_client, date_from=day(3), date_to=day(12))).lower()
        assert "active" in default, "Default view should mark All Time active"
        assert "active" in filtered or f'value="{day(3)}"' in filtered


class TestReadOnly:
    def test_filtering_does_not_modify_expenses(self, auth_client):
        before = expense_rows(db.DB_PATH)
        for params in (
            {},
            {"date_from": day(3), "date_to": day(12)},
            {"date_from": day(20), "date_to": day(5)},
            {"date_from": "bad", "date_to": "worse"},
            {"date_from": "2000-01-01", "date_to": "2000-01-02"},
        ):
            assert get_profile(auth_client, **params).status_code == 200
        after = expense_rows(db.DB_PATH)
        assert before == after, "Filtering must not change expense data"
        assert len(after) == len(SEED)

    def test_filter_does_not_persist_between_requests(self, auth_client):
        get_profile(auth_client, date_from=day(3), date_to=day(5))
        assert_unfiltered(html_of(get_profile(auth_client)))


class TestHtmlRules:
    def test_filtered_page_has_no_inline_styles_or_hex_colours(self, auth_client):
        html = html_of(get_profile(auth_client, date_from=day(3), date_to=day(12)))
        assert 'style="' not in html
        assert not re.search(r"#[0-9a-fA-F]{3,6}\b", html)

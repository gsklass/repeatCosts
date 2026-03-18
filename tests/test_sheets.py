from app.sheets import estimate_amount, FREQUENCY_MULTIPLIERS


TRANSACTIONS = [
    {"Date": "2026-01-01", "Description": "Netflix monthly", "Amount": 15.99},
    {"Date": "2026-02-01", "Description": "Netflix monthly", "Amount": 15.99},
    {"Date": "2026-03-01", "Description": "Netflix monthly", "Amount": 17.99},
    {"Date": "2026-01-15", "Description": "Spotify Premium", "Amount": 9.99},
    {"Date": "2026-01-05", "Description": "Amazon Prime", "Amount": 14.99},
]


def test_estimate_amount_returns_median():
    result = estimate_amount("Netflix", TRANSACTIONS)
    # sorted amounts: 15.99, 15.99, 17.99 → median = 15.99
    assert result == 15.99


def test_estimate_amount_case_insensitive():
    result = estimate_amount("spotify", TRANSACTIONS)
    assert result == 9.99


def test_estimate_amount_no_match_returns_none():
    result = estimate_amount("Hulu", TRANSACTIONS)
    assert result is None


def test_estimate_amount_single_match():
    result = estimate_amount("Amazon Prime", TRANSACTIONS)
    assert result == 14.99


def test_frequency_multipliers_present():
    assert set(FREQUENCY_MULTIPLIERS.keys()) == {
        "weekly", "monthly", "yearly", "quarterly", "biweekly"
    }


def test_monthly_normalization():
    assert FREQUENCY_MULTIPLIERS["monthly"] == 1.0
    assert abs(FREQUENCY_MULTIPLIERS["yearly"] - 1 / 12) < 1e-9
    assert abs(FREQUENCY_MULTIPLIERS["quarterly"] - 1 / 3) < 1e-9
    assert abs(FREQUENCY_MULTIPLIERS["weekly"] - 4.33) < 1e-9
    assert abs(FREQUENCY_MULTIPLIERS["biweekly"] - 2.17) < 1e-9

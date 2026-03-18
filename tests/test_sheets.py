from unittest.mock import MagicMock, patch

from app.sheets import estimate_amount, FREQUENCY_MULTIPLIERS, get_expenses


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

TRANSACTIONS = [
    {"Date": "2026-01-01", "Description": "Netflix monthly", "Amount": 15.99},
    {"Date": "2026-02-01", "Description": "Netflix monthly", "Amount": 15.99},
    {"Date": "2026-03-01", "Description": "Netflix monthly", "Amount": 17.99},
    {"Date": "2026-01-15", "Description": "Spotify Premium", "Amount": 9.99},
    {"Date": "2026-01-05", "Description": "Amazon Prime", "Amount": 14.99},
    {"Date": "2026-01-10", "Description": "AMAZON PRIME annual", "Amount": 139.00},
]

AUTOCAT_ROWS = [
    {"Category": "Netflix", "Description Contains": "netflix", "Amount": "-$15.99", "Frequency": "monthly"},
    {"Category": "Spotify", "Description Contains": "spotify", "Amount": "", "Frequency": "monthly"},
    {"Category": "Amazon Prime", "Description Contains": "amazon prime", "Amount": "", "Frequency": "yearly"},
    {"Category": "Transfer", "Description Contains": "", "Amount": "1000", "Frequency": "monthly"},
    {"Category": "", "Description Contains": "", "Amount": "5.00", "Frequency": "monthly"},
    {"Category": "Gym", "Description Contains": "gym", "Amount": "", "Frequency": "weekly"},
]


# ---------------------------------------------------------------------------
# estimate_amount
# ---------------------------------------------------------------------------

def test_estimate_amount_returns_median():
    result = estimate_amount("Netflix", TRANSACTIONS)
    # sorted: 15.99, 15.99, 17.99 → median = 15.99
    assert result == 15.99


def test_estimate_amount_case_insensitive():
    result = estimate_amount("spotify", TRANSACTIONS)
    assert result == 9.99


def test_estimate_amount_no_match_returns_none():
    result = estimate_amount("Hulu", TRANSACTIONS)
    assert result is None


def test_estimate_amount_single_match():
    result = estimate_amount("Spotify Premium", TRANSACTIONS)
    assert result == 9.99


def test_estimate_amount_strips_dollar_signs():
    txns = [{"Description": "Rent payment", "Amount": "$2,500.00"}]
    result = estimate_amount("Rent", txns)
    assert result == 2500.0


def test_estimate_amount_uses_abs_for_negative():
    txns = [{"Description": "Netflix charge", "Amount": "-$15.99"}]
    result = estimate_amount("Netflix", txns)
    assert result == 15.99


def test_estimate_amount_skips_blank_amount():
    txns = [
        {"Description": "Netflix charge", "Amount": ""},
        {"Description": "Netflix charge", "Amount": None},
        {"Description": "Netflix charge", "Amount": 12.99},
    ]
    result = estimate_amount("Netflix", txns)
    assert result == 12.99


def test_estimate_amount_multiple_matches_even_count():
    txns = [
        {"Description": "Gym membership", "Amount": 10.00},
        {"Description": "Gym membership", "Amount": 20.00},
    ]
    result = estimate_amount("Gym", txns)
    assert result == 15.0


# ---------------------------------------------------------------------------
# FREQUENCY_MULTIPLIERS
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# get_expenses (mocked sheet)
# ---------------------------------------------------------------------------

def _make_mock_sheet(autocat_rows, transactions):
    autocat_ws = MagicMock()
    autocat_ws.get_all_records.return_value = autocat_rows
    transactions_ws = MagicMock()
    transactions_ws.get_all_records.return_value = transactions

    sheet = MagicMock()
    sheet.worksheet.side_effect = lambda name: (
        autocat_ws if name == "AutoCat" else transactions_ws
    )
    return sheet


def _patched_get_expenses(autocat_rows, transactions):
    sheet = _make_mock_sheet(autocat_rows, transactions)
    with patch("app.sheets.get_sheet_client") as mock_client:
        mock_client.return_value.open.return_value = sheet
        return get_expenses()


def test_get_expenses_sorted_by_monthly_amount_desc():
    expenses = _patched_get_expenses(AUTOCAT_ROWS, TRANSACTIONS)
    amounts = [e["monthly_amount"] for e in expenses]
    assert amounts == sorted(amounts, reverse=True)


def test_get_expenses_filters_transfer():
    expenses = _patched_get_expenses(AUTOCAT_ROWS, TRANSACTIONS)
    assert all(e["category"].lower() != "transfer" for e in expenses)


def test_get_expenses_filters_blank_category():
    expenses = _patched_get_expenses(AUTOCAT_ROWS, TRANSACTIONS)
    assert all(e["category"] for e in expenses)


def test_get_expenses_actual_amount_not_estimated():
    expenses = _patched_get_expenses(AUTOCAT_ROWS, TRANSACTIONS)
    netflix = next(e for e in expenses if e["category"] == "Netflix")
    assert netflix["estimated"] is False
    assert abs(netflix["amount"]) == 15.99


def test_get_expenses_blank_amount_marked_estimated():
    expenses = _patched_get_expenses(AUTOCAT_ROWS, TRANSACTIONS)
    spotify = next(e for e in expenses if e["category"] == "Spotify")
    assert spotify["estimated"] is True


def test_get_expenses_monthly_amount_uses_multiplier():
    expenses = _patched_get_expenses(AUTOCAT_ROWS, TRANSACTIONS)
    amazon = next(e for e in expenses if e["category"] == "Amazon Prime")
    # Amazon Prime matched amount: median(14.99, 139.00) = (14.99+139.00)/2 = 76.995
    # yearly multiplier: 1/12
    assert amazon["frequency"] == "yearly"
    assert abs(amazon["monthly_amount"] - amazon["amount"] / 12) < 0.01


def test_get_expenses_unknown_frequency_defaults_to_monthly():
    rows = [{"Category": "Misc", "Description Contains": "", "Amount": "10.00", "Frequency": "fortnightly"}]
    expenses = _patched_get_expenses(rows, [])
    assert expenses[0]["monthly_amount"] == 10.0


def test_get_expenses_filters_aperiodic():
    rows = [{"Category": "Bonus", "Description Contains": "", "Amount": "500", "Frequency": "aperiodic"}]
    expenses = _patched_get_expenses(rows, [])
    assert expenses == []


def test_get_expenses_filters_old():
    rows = [{"Category": "OldService", "Description Contains": "", "Amount": "20", "Frequency": "OLD"}]
    expenses = _patched_get_expenses(rows, [])
    assert expenses == []


def test_get_expenses_filters_delete_category():
    rows = [{"Category": "DELETE", "Description Contains": "", "Amount": "50", "Frequency": "monthly"}]
    expenses = _patched_get_expenses(rows, [])
    assert expenses == []


def test_get_expenses_no_match_for_blank_amount_sets_zero():
    expenses = _patched_get_expenses(AUTOCAT_ROWS, TRANSACTIONS)
    gym = next((e for e in expenses if e["category"] == "Gym"), None)
    assert gym is not None
    assert gym["amount"] is None
    assert gym["monthly_amount"] == 0.0


def test_get_expenses_includes_description_contains():
    expenses = _patched_get_expenses(AUTOCAT_ROWS, TRANSACTIONS)
    netflix = next(e for e in expenses if e["category"] == "Netflix")
    assert netflix["description_contains"] == "netflix"

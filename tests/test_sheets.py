from datetime import date
from unittest.mock import MagicMock, patch

from app.sheets import estimate_amount, FREQUENCY_MULTIPLIERS, get_expenses, is_ceased, latest_transaction_date


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
    result = estimate_amount("Netflix monthly", TRANSACTIONS)
    # sorted: 15.99, 15.99, 17.99 → median = 15.99
    assert result == 15.99


def test_estimate_amount_case_insensitive():
    result = estimate_amount("spotify premium", TRANSACTIONS)
    assert result == 9.99


def test_estimate_amount_no_match_returns_none():
    result = estimate_amount("Hulu", TRANSACTIONS)
    assert result is None


def test_estimate_amount_single_match():
    result = estimate_amount("Spotify Premium", TRANSACTIONS)
    assert result == 9.99


def test_estimate_amount_uses_description_contains_over_category():
    # "Cookunity Inc" should match precisely; "Food" would match broadly
    txns = [
        {"Description": "Cookunity Inc charge", "Amount": "-$52.53"},
        {"Description": "Whole Foods purchase", "Amount": "-$120.00"},
    ]
    result = estimate_amount("Cookunity Inc", txns)
    assert result == 52.53


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
        "weekly", "monthly", "yearly", "annually", "quarterly",
        "halfyearly", "biweekly", "bi-weekly",
    }


def test_monthly_normalization():
    assert FREQUENCY_MULTIPLIERS["monthly"] == 1.0
    assert abs(FREQUENCY_MULTIPLIERS["yearly"] - 1 / 12) < 1e-9
    assert abs(FREQUENCY_MULTIPLIERS["annually"] - 1 / 12) < 1e-9
    assert abs(FREQUENCY_MULTIPLIERS["quarterly"] - 1 / 3) < 1e-9
    assert abs(FREQUENCY_MULTIPLIERS["halfyearly"] - 1 / 6) < 1e-9
    assert abs(FREQUENCY_MULTIPLIERS["weekly"] - 4.33) < 1e-9
    assert abs(FREQUENCY_MULTIPLIERS["biweekly"] - 2.17) < 1e-9
    assert abs(FREQUENCY_MULTIPLIERS["bi-weekly"] - 2.17) < 1e-9


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
    assert netflix["amount"] == 15.99


def test_get_expenses_income_amount_is_negative():
    rows = [{"Category": "Income:salary", "Description Contains": "payroll", "Amount": "-$5000", "Frequency": "monthly", "Notes": ""}]
    expenses = _patched_get_expenses(rows, [])
    assert expenses[0]["amount"] == -5000.0


def test_get_expenses_expense_amount_is_positive():
    rows = [{"Category": "Rent", "Description Contains": "landlord", "Amount": "-$2000", "Frequency": "monthly", "Notes": ""}]
    expenses = _patched_get_expenses(rows, [])
    assert expenses[0]["amount"] == 2000.0


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


def test_get_expenses_no_match_for_blank_amount_excluded():
    expenses = _patched_get_expenses(AUTOCAT_ROWS, TRANSACTIONS)
    gym = next((e for e in expenses if e["category"] == "Gym"), None)
    assert gym is None


def test_get_expenses_income_flagged():
    rows = [
        {"Category": "Income:salary", "Description Contains": "payroll", "Amount": "5000", "Frequency": "monthly", "Notes": ""},
        {"Category": "Rent", "Description Contains": "landlord", "Amount": "2000", "Frequency": "monthly", "Notes": ""},
    ]
    expenses = _patched_get_expenses(rows, [])
    income = next(e for e in expenses if e["category"] == "Income:salary")
    rent = next(e for e in expenses if e["category"] == "Rent")
    assert income["is_income"] is True
    assert rent["is_income"] is False


def test_get_expenses_includes_description_contains():
    expenses = _patched_get_expenses(AUTOCAT_ROWS, TRANSACTIONS)
    netflix = next(e for e in expenses if e["category"] == "Netflix")
    assert netflix["description_contains"] == "netflix"


# ---------------------------------------------------------------------------
# latest_transaction_date
# ---------------------------------------------------------------------------

def test_latest_transaction_date_returns_most_recent():
    result = latest_transaction_date("netflix", TRANSACTIONS)
    assert result == date(2026, 3, 1)


def test_latest_transaction_date_case_insensitive():
    result = latest_transaction_date("NETFLIX", TRANSACTIONS)
    assert result == date(2026, 3, 1)


def test_latest_transaction_date_no_match_returns_none():
    result = latest_transaction_date("hulu", TRANSACTIONS)
    assert result is None


def test_latest_transaction_date_skips_unparseable_dates():
    txns = [
        {"Date": "not-a-date", "Description": "Netflix", "Amount": 15.99},
        {"Date": "2026-02-01", "Description": "Netflix", "Amount": 15.99},
    ]
    result = latest_transaction_date("netflix", txns)
    assert result == date(2026, 2, 1)


# ---------------------------------------------------------------------------
# is_ceased
# ---------------------------------------------------------------------------

def test_is_ceased_recent_transaction_not_ceased():
    today = date(2026, 3, 19)
    txns = [{"Date": "2026-03-01", "Description": "Netflix monthly", "Amount": 15.99}]
    assert is_ceased("netflix", "monthly", txns, today=today) is False


def test_is_ceased_old_transaction_is_ceased():
    today = date(2026, 3, 19)
    # Last seen 2025-12-01 — over 2 months ago, period is 31 days, cutoff = 2026-01-16
    txns = [{"Date": "2025-12-01", "Description": "Netflix monthly", "Amount": 15.99}]
    assert is_ceased("netflix", "monthly", txns, today=today) is True


def test_is_ceased_no_transactions_returns_false():
    today = date(2026, 3, 19)
    assert is_ceased("hulu", "monthly", TRANSACTIONS, today=today) is False


def test_is_ceased_uses_frequency_period():
    today = date(2026, 3, 19)
    # Annual subscription last seen 8 months ago — within 2 * 366 days, not ceased
    txns = [{"Date": "2025-07-19", "Description": "Adobe annual", "Amount": 600.00}]
    assert is_ceased("adobe", "yearly", txns, today=today) is False


def test_get_expenses_includes_ceased_field():
    expenses = _patched_get_expenses(AUTOCAT_ROWS, TRANSACTIONS)
    for e in expenses:
        assert "ceased" in e

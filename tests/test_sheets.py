from datetime import date
from unittest.mock import MagicMock, patch

from app.sheets import ceased_by_last_date, estimate_amount, FREQUENCY_MULTIPLIERS, get_expenses


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
    {"Category": "Netflix", "Description Contains": "netflix", "Amount": "-$15.99", "Frequency": "monthly", "Notes": "", "Last Date": "2026-03-01"},
    {"Category": "Spotify", "Description Contains": "spotify", "Amount": "", "Frequency": "monthly", "Notes": "", "Last Date": "2026-03-01"},
    {"Category": "Amazon Prime", "Description Contains": "amazon prime", "Amount": "", "Frequency": "yearly", "Notes": "", "Last Date": "2026-01-10"},
    {"Category": "Transfer", "Description Contains": "", "Amount": "1000", "Frequency": "monthly", "Notes": "", "Last Date": "2026-03-01"},
    {"Category": "", "Description Contains": "", "Amount": "5.00", "Frequency": "monthly", "Notes": "", "Last Date": "2026-03-01"},
    {"Category": "Gym", "Description Contains": "gym", "Amount": "", "Frequency": "weekly", "Notes": "", "Last Date": "2026-03-01"},
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
    rows = [{"Category": "Income:salary", "Description Contains": "payroll", "Amount": "-$5000", "Frequency": "monthly", "Notes": "", "Last Date": "2026-03-01"}]
    expenses = _patched_get_expenses(rows, [])
    assert expenses[0]["amount"] == -5000.0


def test_get_expenses_expense_amount_is_positive():
    rows = [{"Category": "Rent", "Description Contains": "landlord", "Amount": "-$2000", "Frequency": "monthly", "Notes": "", "Last Date": "2026-03-01"}]
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
    rows = [{"Category": "Misc", "Description Contains": "", "Amount": "10.00", "Frequency": "fortnightly", "Last Date": "2026-03-01"}]
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
        {"Category": "Income:salary", "Description Contains": "payroll", "Amount": "5000", "Frequency": "monthly", "Notes": "", "Last Date": "2026-03-01"},
        {"Category": "Rent", "Description Contains": "landlord", "Amount": "2000", "Frequency": "monthly", "Notes": "", "Last Date": "2026-03-01"},
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
# ceased_by_last_date
# ---------------------------------------------------------------------------

def test_ceased_blank_last_date():
    assert ceased_by_last_date("", "monthly", today=date(2026, 3, 19)) is True


def test_ceased_whitespace_last_date():
    assert ceased_by_last_date("   ", "monthly", today=date(2026, 3, 19)) is True


def test_ceased_unparseable_last_date():
    assert ceased_by_last_date("not-a-date", "monthly", today=date(2026, 3, 19)) is True


def test_ceased_recent_last_date_not_ceased():
    # 2026-03-01 is 18 days ago; monthly cutoff = 62 days → not ceased
    assert ceased_by_last_date("2026-03-01", "monthly", today=date(2026, 3, 19)) is False


def test_ceased_mdyyyy_format_not_ceased():
    # Google Sheets M/D/YYYY format
    assert ceased_by_last_date("3/1/2026", "monthly", today=date(2026, 3, 19)) is False


def test_ceased_mdyyyy_format_is_ceased():
    assert ceased_by_last_date("12/1/2025", "monthly", today=date(2026, 3, 19)) is True


def test_ceased_old_last_date_is_ceased():
    # 2025-12-01 is 108 days ago; monthly cutoff = 62 days → ceased
    assert ceased_by_last_date("2025-12-01", "monthly", today=date(2026, 3, 19)) is True


def test_ceased_yearly_not_ceased_within_two_years():
    # 2025-07-19 is ~8 months ago; yearly cutoff = 732 days → not ceased
    assert ceased_by_last_date("2025-07-19", "yearly", today=date(2026, 3, 19)) is False


def test_ceased_rows_excluded_from_expenses():
    rows = [
        {"Category": "Active", "Description Contains": "active", "Amount": "10", "Frequency": "monthly", "Notes": "", "Last Date": "2026-03-01"},
        {"Category": "Gone", "Description Contains": "gone", "Amount": "20", "Frequency": "monthly", "Notes": "", "Last Date": "2025-01-01"},
        {"Category": "NeverSeen", "Description Contains": "never", "Amount": "5", "Frequency": "monthly", "Notes": "", "Last Date": ""},
    ]
    expenses = _patched_get_expenses(rows, [])
    assert len(expenses) == 1
    assert expenses[0]["category"] == "Active"


def test_get_expenses_no_ceased_field():
    expenses = _patched_get_expenses(AUTOCAT_ROWS, TRANSACTIONS)
    for e in expenses:
        assert "ceased" not in e

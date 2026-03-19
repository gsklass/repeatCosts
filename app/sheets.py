import statistics
from datetime import date, datetime, timedelta
from pathlib import Path

import gspread
from google.oauth2 import service_account

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]

FREQUENCY_DAYS = {
    "weekly": 7,
    "biweekly": 14,
    "bi-weekly": 14,
    "monthly": 31,
    "quarterly": 92,
    "halfyearly": 183,
    "yearly": 366,
    "annually": 366,
}

FREQUENCY_MULTIPLIERS = {
    "weekly": 4.33,
    "monthly": 1.0,
    "yearly": 1 / 12,
    "annually": 1 / 12,
    "quarterly": 1 / 3,
    "halfyearly": 1 / 6,
    "biweekly": 2.17,
    "bi-weekly": 2.17,
}

PROJECT_ROOT = Path(__file__).parent.parent


def get_sheet_client() -> gspread.Client:
    creds_path = PROJECT_ROOT / "credentials.json"
    creds = service_account.Credentials.from_service_account_file(
        str(creds_path), scopes=SCOPES
    )
    return gspread.authorize(creds)


def load_autocat(sheet: gspread.Spreadsheet) -> list[dict]:
    ws = sheet.worksheet("AutoCat")
    rows = ws.get_all_records()
    return rows


def load_transactions(sheet: gspread.Spreadsheet) -> list[dict]:
    ws = sheet.worksheet("Transactions")
    rows = ws.get_all_records(expected_headers=["Date", "Description", "Amount"])
    return rows


def ceased_by_last_date(last_date_str: str, frequency: str, today: date | None = None) -> bool:
    if not str(last_date_str).strip():
        return True
    try:
        last = datetime.strptime(str(last_date_str).strip(), "%Y-%m-%d").date()
    except ValueError:
        return True
    if today is None:
        today = date.today()
    period_days = FREQUENCY_DAYS.get(frequency, 31)
    return last < today - timedelta(days=period_days * 2)


def estimate_amount(match_string: str, transactions: list[dict]) -> float | None:
    matched = [
        abs(float(str(t["Amount"]).replace("$", "").replace(",", "").strip()))
        for t in transactions
        if match_string.lower() in str(t.get("Description", "")).lower()
        and t.get("Amount") not in ("", None)
    ]
    if not matched:
        return None
    return statistics.median(matched)


def get_expenses() -> list[dict]:
    client = get_sheet_client()
    sheet = client.open("Greg\u2019s money")
    autocat_rows = load_autocat(sheet)
    transactions = load_transactions(sheet)

    expenses = []
    for row in autocat_rows:
        category = str(row.get("Category", "")).strip()
        if not category or category.lower() in ("transfer", "delete"):
            continue

        raw_amount = row.get("Amount")
        frequency = str(row.get("Frequency", "monthly")).strip().lower()

        if frequency in ("aperiodic", "old"):
            continue

        last_date = str(row.get("Last Date", "")).strip()
        if ceased_by_last_date(last_date, frequency):
            continue

        desc_contains = str(row.get("Description Contains", "")).strip()
        match_string = desc_contains if desc_contains else category

        estimated = False
        if raw_amount in ("", None):
            raw_amount = estimate_amount(match_string, transactions)
            estimated = True

        is_income = category.lower().startswith("income")

        if raw_amount in ("", None):
            amount = None
            monthly_amount = 0.0
        else:
            raw = abs(float(str(raw_amount).replace("$", "").replace(",", "").strip()))
            amount = -raw if is_income else raw
            multiplier = FREQUENCY_MULTIPLIERS.get(frequency, 1.0)
            monthly_amount = raw * multiplier

        if not monthly_amount:
            continue

        expenses.append(
            {
                "description_contains": str(row.get("Description Contains", "")).strip(),
                "notes": str(row.get("Notes", "")).strip(),
                "category": category,
                "amount": amount,
                "frequency": frequency,
                "estimated": estimated,
                "monthly_amount": monthly_amount,
                "is_income": is_income,
            }
        )

    expenses.sort(key=lambda x: x["monthly_amount"], reverse=True)

    from collections import Counter
    desc_counts = Counter(e["description_contains"] for e in expenses)
    for e in expenses:
        if desc_counts[e["description_contains"]] > 1 and e["notes"]:
            e["description_contains"] = f"{e['description_contains']} - {e['notes']}"

    return expenses

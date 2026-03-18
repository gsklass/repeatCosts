import statistics
from pathlib import Path

import gspread
from google.oauth2 import service_account

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]

FREQUENCY_MULTIPLIERS = {
    "weekly": 4.33,
    "monthly": 1.0,
    "yearly": 1 / 12,
    "quarterly": 1 / 3,
    "biweekly": 2.17,
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


def estimate_amount(category: str, transactions: list[dict]) -> float | None:
    matched = [
        abs(float(str(t["Amount"]).replace("$", "").replace(",", "").strip()))
        for t in transactions
        if category.lower() in str(t.get("Description", "")).lower()
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

        estimated = False
        if raw_amount in ("", None):
            raw_amount = estimate_amount(category, transactions)
            estimated = True

        if raw_amount in ("", None):
            amount = None
            monthly_amount = 0.0
        else:
            amount = float(str(raw_amount).replace("$", "").replace(",", "").strip())
            multiplier = FREQUENCY_MULTIPLIERS.get(frequency, 1.0)
            monthly_amount = abs(amount) * multiplier

        expenses.append(
            {
                "description_contains": str(row.get("Description Contains", "")).strip(),
                "category": category,
                "amount": amount,
                "frequency": frequency,
                "estimated": estimated,
                "monthly_amount": monthly_amount,
            }
        )

    expenses.sort(key=lambda x: x["monthly_amount"], reverse=True)
    return expenses

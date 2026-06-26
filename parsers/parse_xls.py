"""Parse a Barclays XLSX bank export (.xlsx statement download).

Barclays exports the same column layout as CSV when saved as Excel:
    Number | Date | Account | Amount | Subcategory | Memo

Returns the same shape as parse_csv / parse_pdf:
    {
        'date':        datetime.date,
        'description': str,
        'subcategory': str,
        'money_in':    float,
        'money_out':   float,
        'balance':     None,   # XLSX export has no running balance column
    }
"""

from datetime import datetime, date
from pathlib import Path

import pandas as pd


def parse_xls(path) -> list[dict]:
    path = Path(path)

    df = pd.read_excel(path, engine='openpyxl', dtype=str)
    df.columns = [str(c).strip() for c in df.columns]

    col_map = _detect_columns(df.columns.tolist())

    transactions = []
    for _, row in df.iterrows():
        date_raw   = str(row.get(col_map['date'],   '')).strip()
        amount_raw = str(row.get(col_map['amount'], '')).strip()

        if not date_raw or not amount_raw or date_raw == 'nan' or amount_raw == 'nan':
            continue

        d = _parse_date(date_raw)
        if d is None:
            continue

        try:
            amount = float(amount_raw.replace(',', ''))
        except ValueError:
            continue

        memo_raw   = str(row.get(col_map['memo'],   '')).strip()
        subcat_raw = str(row.get(col_map['subcat'], '')).strip()

        description = memo_raw   if memo_raw   != 'nan' else ''
        subcategory = subcat_raw if subcat_raw != 'nan' else ''

        if amount >= 0:
            money_in  = amount
            money_out = 0.0
        else:
            money_in  = 0.0
            money_out = abs(amount)

        transactions.append({
            'date':        d,
            'description': description,
            'subcategory': subcategory,
            'money_in':    money_in,
            'money_out':   money_out,
            'balance':     None,
        })

    return transactions


def _detect_columns(columns: list[str]) -> dict:
    lower = {c.lower(): c for c in columns}

    def find(candidates):
        for candidate in candidates:
            for key, original in lower.items():
                if candidate in key:
                    return original
        return columns[0]

    return {
        'date':   find(['date']),
        'amount': find(['amount']),
        'memo':   find(['memo', 'description', 'reference', 'details']),
        'subcat': find(['subcategor', 'type', 'category']),
    }


def _parse_date(raw: str) -> date | None:
    for fmt in ('%d/%m/%Y', '%d-%m-%Y', '%Y-%m-%d', '%d %b %Y', '%d/%m/%y'):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None

"""Parse a Barclays CSV bank export (May_24.csv format).

Column layout: Number, Date, Account, Amount, Subcategory, Memo

Returns a list of transaction dicts:
    {
        'date':        datetime.date,
        'description': str,      # cleaned Memo
        'subcategory': str,      # bank's own type, e.g. 'Contactless Card Purchase'
        'money_in':    float,    # positive credit; 0 if debit
        'money_out':   float,    # positive debit;  0 if credit
        'balance':     None,     # CSV has no running balance
    }
"""

import re
import csv
from datetime import datetime
from pathlib import Path


def _clean_memo(raw: str) -> str:
    """Strip tabs, collapse multiple spaces, strip outer whitespace."""
    text = raw.replace('\t', ' ')
    text = re.sub(r' {2,}', ' ', text)
    return text.strip()


def parse_csv(path) -> list[dict]:
    path = Path(path)
    transactions = []

    with open(path, newline='', encoding='utf-8-sig') as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            # Skip blank rows
            date_raw = row.get('Date', '').strip()
            amount_raw = row.get('Amount', '').strip()
            if not date_raw or not amount_raw:
                continue

            try:
                d = datetime.strptime(date_raw.strip(), '%d/%m/%Y').date()
            except ValueError:
                try:
                    d = datetime.strptime(date_raw.strip(), '%m/%d/%Y').date()
                except ValueError:
                    continue

            try:
                amount = float(amount_raw)
            except ValueError:
                continue

            memo_raw = row.get('Memo', '')
            subcategory = row.get('Subcategory', '').strip()
            description = _clean_memo(memo_raw)

            if amount >= 0:
                money_in = amount
                money_out = 0.0
            else:
                money_in = 0.0
                money_out = abs(amount)

            transactions.append({
                'date': d,
                'description': description,
                'subcategory': subcategory,
                'money_in': money_in,
                'money_out': money_out,
                'balance': None,
            })

    return transactions

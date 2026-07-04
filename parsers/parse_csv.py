"""Universal bank statement CSV parser.

Auto-detects column layout from headers. Handles:
  - Signed Amount column  (Barclays standard, Matthew Farris)
  - Separate Paid in / Paid out columns  (Chido Hove, Ahmed Ibrahim, Shaifa Remtulla)
  - Date-time stamps  (DD/MM/YYYY HH:MM)
  - Comma-formatted numbers  (1,000.00)
  - Newest-first ordering — always returns ascending
  - Multiple encodings  (utf-8-sig, utf-8, latin-1, cp1252)
"""

import csv
import re
from datetime import datetime
from pathlib import Path


def _clean(raw: str) -> str:
    return re.sub(r'\s{2,}', ' ', raw.replace('\t', ' ')).strip()


def _parse_amount(raw: str):
    if not raw or not raw.strip():
        return None
    cleaned = re.sub(r'[£,\s]', '', raw.strip())
    try:
        return float(cleaned)
    except ValueError:
        return None


def _parse_date(raw: str):
    for fmt in ('%d/%m/%Y %H:%M', '%d/%m/%Y', '%m/%d/%Y'):
        try:
            return datetime.strptime(raw.strip(), fmt).date()
        except ValueError:
            continue
    return None


def _open_csv(path: Path):
    for enc in ('utf-8-sig', 'utf-8', 'latin-1', 'cp1252'):
        try:
            fh = open(path, newline='', encoding=enc)
            fh.read(2048)
            fh.seek(0)
            return fh, enc
        except UnicodeDecodeError:
            try:
                fh.close()
            except Exception:
                pass
    raise ValueError(f"Cannot decode {path.name} — tried utf-8-sig, utf-8, latin-1, cp1252")


def _find(headers: list, *candidates: str):
    norm = {h.strip().lower(): h for h in headers}
    for c in candidates:
        found = norm.get(c.lower())
        if found is not None:
            return found
    return None


def parse_csv(path) -> list[dict]:
    path = Path(path)
    fh, _ = _open_csv(path)
    try:
        reader = csv.DictReader(fh)
        rows = list(reader)
        raw_headers = list(reader.fieldnames or [])
    finally:
        fh.close()

    if not rows:
        return []

    # Strip whitespace from all headers and row keys
    headers = [h.strip() for h in raw_headers]
    rows = [{k.strip(): v for k, v in row.items()} for row in rows]

    # ── Column detection ──────────────────────────────────────────────────────
    date_col = _find(headers, 'Date', 'Transaction Date', 'Value Date')
    if not date_col:
        raise ValueError(f"No Date column found in {path.name}. Headers: {headers}")

    desc_col = _find(headers,
        'Memo', 'Counter Party', 'Description', 'Transaction description',
        'Details', 'Narrative', 'Payee', 'From',
    )
    ref_col      = _find(headers, 'Reference', 'Ref', 'Transaction ID')
    type_col     = _find(headers, 'Type', 'Transaction Type', 'Transaction type')
    csv_cat_col  = _find(headers, 'Spending Category', 'Category name', 'Category')
    bal_col      = _find(headers, 'Balance', 'Balance (GBP)', 'Balance (£)', 'Running Balance')

    # Separate in/out takes priority over signed Amount
    in_col  = _find(headers, 'Paid in', 'Paid In', 'IN', 'In', 'In (£)', 'In (GBP)', 'Credit')
    out_col = _find(headers, 'Paid out', 'Paid Out', 'OUT', 'Out', 'Out (£)', 'Out (GBP)', 'Debit')
    amt_col = _find(headers, 'Amount', 'Amount (GBP)', 'Amount (£)')

    transactions = []

    for row in rows:
        date_raw = row.get(date_col, '').strip()
        if not date_raw:
            continue
        d = _parse_date(date_raw)
        if d is None:
            continue

        description  = _clean(row.get(desc_col, ''))    if desc_col    else ''
        reference    = row.get(ref_col, '').strip()      if ref_col     else ''
        subcategory  = row.get(type_col, '').strip()     if type_col    else ''
        csv_category = row.get(csv_cat_col, '').strip()  if csv_cat_col else ''

        # Strip leading apostrophe Excel inserts for text-prefix formatting
        reference = reference.lstrip("'")

        money_in  = 0.0
        money_out = 0.0

        if in_col or out_col:
            money_in  = _parse_amount(row.get(in_col,  '') if in_col  else '') or 0.0
            money_out = _parse_amount(row.get(out_col, '') if out_col else '') or 0.0
        elif amt_col:
            amt = _parse_amount(row.get(amt_col, ''))
            if amt is None:
                continue
            if amt >= 0:
                money_in = amt
            else:
                money_out = abs(amt)
        else:
            continue  # no usable money column

        if money_in == 0 and money_out == 0:
            continue  # blank / header row

        balance = _parse_amount(row.get(bal_col, '')) if bal_col else None

        transactions.append({
            'date':         d,
            'description':  description,
            'subcategory':  subcategory,
            'reference':    reference,
            'csv_category': csv_category,
            'money_in':     money_in,
            'money_out':    money_out,
            'balance':      balance,
        })

    # Sort ascending by date (some bank exports are newest-first)
    transactions.sort(key=lambda t: t['date'])
    return transactions

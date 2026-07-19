"""Parse a bank statement PDF.

Two-layer strategy:
 1. Barclays text-mode parser  – fast, handles Barclays multi-line descriptions.
 2. Generic table parser       – works for most other banks (HSBC, Lloyds,
                                 NatWest, Halifax, Santander, etc.) whose
                                 PDFs contain proper table cells.

If both layers return 0 transactions a ValueError is raised with a helpful
message so the API returns a readable error to the user.

Returns the same shape as parse_csv:
    {
        'date':        datetime.date,
        'description': str,
        'subcategory': str,
        'reference':   str,
        'csv_category': str,
        'money_in':    float,
        'money_out':   float,
        'balance':     float | None,
    }

Privacy: account numbers, sort codes, IBANs are NEVER returned.
"""

import re
from datetime import datetime
from pathlib import Path

import pdfplumber


# ── Shared regex helpers ──────────────────────────────────────────────────────

_MONTHS = r'(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)'

# "6 Apr", "12 Apr", "6 Apr 2025"
_DATE_DMY_TEXT = re.compile(
    rf'^(\d{{1,2}}\s+{_MONTHS}(?:\s+\d{{4}})?)\s+(.*)',
    re.IGNORECASE,
)

# "01/04/2025", "01-04-2025", "01.04.2025"
_DATE_SLASH = re.compile(r'^(\d{2}[/\-\.]\d{2}[/\-\.]\d{4})\s+(.*)')

# "2025-04-01"
_DATE_ISO = re.compile(r'^(\d{4}-\d{2}-\d{2})\s+(.*)')

_AMOUNT_RE   = re.compile(r'[\d,]+\.\d{2}')
_TWO_AMOUNTS = re.compile(r'^(.*?)\s+([\d,]+\.\d{2})\s+([\d,]+\.\d{2})\s*$')
_ONE_AMOUNT  = re.compile(r'^(.*?)\s+([\d,]+\.\d{2})\s*$')


def _parse_amount(s: str) -> float:
    return float(str(s).replace(',', '').replace('£', '').strip())


def _parse_date_str(s: str, year_hint: int) -> 'datetime.date | None':
    """Parse a date string in any common format."""
    s = s.strip()
    for fmt in ('%d %b %Y', '%d %b'):
        try:
            d = datetime.strptime(s, fmt)
            if '%Y' not in fmt:
                d = d.replace(year=year_hint)
            return d.date()
        except ValueError:
            pass
    for sep in ('/', '-', '.'):
        for fmt in (f'%d{sep}%m{sep}%Y', f'%m{sep}%d{sep}%Y'):
            try:
                return datetime.strptime(s, fmt).date()
            except ValueError:
                pass
    try:
        return datetime.strptime(s, '%Y-%m-%d').date()
    except ValueError:
        pass
    return None


def _try_parse_amount_cell(val) -> float | None:
    """Convert a table cell value to float, or None if not a number."""
    if val is None:
        return None
    s = str(val).strip().replace(',', '').replace('£', '').replace('(', '-').replace(')', '')
    if not s or s in ('-', '—', ''):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _infer_year(path: Path) -> int:
    """Guess statement year from the filename.

    Handles patterns like:
      'Statement 03-MAY-24 ...'  -> 2024
      'May 24.csv'               -> 2024
      'statement_2025_04.pdf'    -> 2025
      'Apr25'                    -> 2025
    """
    name = path.stem
    # 4-digit year anywhere
    m = re.search(r'20(\d{2})', name)
    if m:
        return int('20' + m.group(1))
    # DD-MMM-YY pattern (e.g. "03-MAY-24") — take the last 2-digit number after a month
    m = re.search(
        r'\d{1,2}[-/\s](?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[-/\s](\d{2})',
        name, re.IGNORECASE,
    )
    if m:
        return 2000 + int(m.group(1))
    # MMM-YY or MMM YY (e.g. "May 24", "Apr25")
    m = re.search(
        r'(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[-/\s]?(\d{2})\b',
        name, re.IGNORECASE,
    )
    if m:
        return 2000 + int(m.group(1))
    # Bare 2-digit year at end of filename (e.g. "statement_24")
    m = re.search(r'[-_\s](\d{2})$', name)
    if m:
        yr = int(m.group(1))
        if 20 <= yr <= 99:
            return 2000 + yr
    return datetime.now().year


# ── Privacy filter ────────────────────────────────────────────────────────────

_SENSITIVE_RE = re.compile(
    r'\b\d{8}\b'           # 8-digit account number
    r'|\b\d{2}-\d{2}-\d{2}\b'  # sort code XX-XX-XX
    r'|IBAN\s*[:\s]+[A-Z]{2}\d{2}[A-Z0-9]+',
    re.IGNORECASE,
)


def _scrub(text: str) -> str:
    return _SENSITIVE_RE.sub('[REDACTED]', text)


# ── Layer 1: Barclays text-mode parser ───────────────────────────────────────

_BARCLAYS_SKIP = re.compile(
    r'balance brought forward|bbaallaannccee|'
    r'start balance|'
    r'date\s+description\s+money|'
    r'barclays bank|registered in england|financial services register|'
    r'authorised by the prudential|regulated by the financial|'
    r'registered office|registered no\.|'
    r'your deposit is eligible|financial services compensation|'
    r'anything wrong\?|bank of england base rate|rate effective from|'
    r'sort code|account no|swiftbic|iban|issued on|'
    r'^see optyx|^the director|stanmore|ha7 |woodcroft|'
    r'^at a glance|^\d{2}\s+[a-z]{3}\s+-\s+\d{2}\s+[a-z]{3}|'
    r'^your business|page$|continued$|^\d+$|'
    r'u commission charges|u interest paid|money in|money out|end balance',
    re.IGNORECASE,
)

_BARCLAYS_END = re.compile(
    r'balance carried forward|total payments|total receipts|helpful information',
    re.IGNORECASE,
)

_SIDEBAR_SUFFIX = re.compile(
    r'\s+u\s+.*$'
    r'|\s+Money (?:in|out)\s+.*$'
    r'|\s+End balance\s+.*$'
    r'|\s+by the Financial Services.*$'
    r'|\s+Compensation Scheme.*$',
    re.IGNORECASE,
)


def _parse_barclays(pdf, year_hint: int) -> list[dict]:
    transactions = []
    current_date = None
    prev_balance = None
    pending = None

    def flush():
        nonlocal pending
        if pending is not None:
            transactions.append(pending.copy())
            pending = None

    for page in pdf.pages:
        text = page.extract_text()
        if not text:
            continue
        for raw_line in text.split('\n'):
            line = raw_line.strip()
            if not line:
                continue
            line = _SIDEBAR_SUFFIX.sub('', line).strip()

            if _BARCLAYS_END.search(line):
                flush()
                break

            if _BARCLAYS_SKIP.search(line):
                m = re.search(r'start balance\s+([\d,]+\.\d{2})', line, re.I)
                if m:
                    prev_balance = _parse_amount(m.group(1))
                continue

            # Date prefix?
            dm = _DATE_DMY_TEXT.match(line)
            if dm:
                date_str = dm.group(1).strip()
                line = dm.group(2).strip()
                # Inject year if not present
                if not re.search(r'\d{4}', date_str):
                    date_str = f"{date_str} {year_hint}"
                d = _parse_date_str(date_str, year_hint)
                if d:
                    current_date = d

            m2 = _TWO_AMOUNTS.match(line)
            m1 = _ONE_AMOUNT.match(line) if not m2 else None

            if m2:
                desc_part = m2.group(1).strip()
                balance = _parse_amount(m2.group(3))
                delta = balance - prev_balance if prev_balance is not None else None
                if delta is not None:
                    money_in  = round(delta, 2)  if delta >  0.001 else 0.0
                    money_out = round(-delta, 2) if delta < -0.001 else 0.0
                else:
                    money_out = _parse_amount(m2.group(2))
                    money_in = 0.0
                prev_balance = balance
                flush()
                pending = {
                    'date': current_date, 'description': _scrub(desc_part),
                    'subcategory': '', 'reference': '', 'csv_category': '',
                    'money_in': money_in, 'money_out': money_out, 'balance': balance,
                }
            elif m1:
                desc_part = m1.group(1).strip()
                if not desc_part:
                    prev_balance = _parse_amount(m1.group(2))
                    continue
                balance = _parse_amount(m1.group(2))
                delta = balance - prev_balance if prev_balance is not None else None
                if delta is not None:
                    money_in  = round(delta, 2)  if delta >  0.001 else 0.0
                    money_out = round(-delta, 2) if delta < -0.001 else 0.0
                else:
                    money_in = money_out = 0.0
                prev_balance = balance
                flush()
                pending = {
                    'date': current_date, 'description': _scrub(desc_part),
                    'subcategory': '', 'reference': '', 'csv_category': '',
                    'money_in': money_in, 'money_out': money_out, 'balance': balance,
                }
            else:
                # Fallback: find rightmost two decimal amounts
                matches = list(_AMOUNT_RE.finditer(line))
                if len(matches) >= 2:
                    balance = _parse_amount(matches[-1].group())
                    amt     = _parse_amount(matches[-2].group())
                    desc_part = line[:matches[-2].start()].strip()
                    delta = balance - prev_balance if prev_balance is not None else None
                    if delta is not None:
                        money_in  = round(delta, 2)  if delta >  0.001 else 0.0
                        money_out = round(-delta, 2) if delta < -0.001 else 0.0
                    else:
                        money_in = 0.0; money_out = amt
                    prev_balance = balance
                    flush()
                    pending = {
                        'date': current_date, 'description': _scrub(desc_part),
                        'subcategory': '', 'reference': '', 'csv_category': '',
                        'money_in': money_in, 'money_out': money_out, 'balance': balance,
                    }
                elif pending is not None and line:
                    pending['description'] = (pending['description'] + ' ' + line).strip()

    flush()
    return [
        t for t in transactions
        if t['date'] is not None and (t['money_in'] > 0 or t['money_out'] > 0)
    ]


# ── Layer 2: Generic table parser ────────────────────────────────────────────

# Column header patterns for common banks
_COL_DATE  = re.compile(r'^date$', re.I)
_COL_DESC  = re.compile(r'description|details|narrative|merchant|payee|party', re.I)
_COL_IN    = re.compile(r'paid.?in|credit|money.?in|deposits?|receipts?', re.I)
_COL_OUT   = re.compile(r'paid.?out|debit|money.?out|withdrawals?|payments?', re.I)
_COL_AMT   = re.compile(r'^amount$', re.I)
_COL_BAL   = re.compile(r'^balance', re.I)
_COL_REF   = re.compile(r'reference|ref$', re.I)
_COL_TYPE  = re.compile(r'^type$|transaction.?type', re.I)


def _match_col(headers: list[str], pattern: re.Pattern) -> int | None:
    for i, h in enumerate(headers):
        if h and pattern.search(str(h).strip()):
            return i
    return None


def _parse_generic_table(pdf, year_hint: int) -> list[dict]:
    """Extract transactions from any PDF that renders a clear table."""
    transactions = []

    for page in pdf.pages:
        tables = page.extract_tables()
        for table in tables:
            if not table or len(table) < 2:
                continue

            # First row is usually the header
            headers = [str(c or '').strip() for c in table[0]]
            i_date = _match_col(headers, _COL_DATE)
            i_desc = _match_col(headers, _COL_DESC)
            i_in   = _match_col(headers, _COL_IN)
            i_out  = _match_col(headers, _COL_OUT)
            i_amt  = _match_col(headers, _COL_AMT)
            i_bal  = _match_col(headers, _COL_BAL)
            i_ref  = _match_col(headers, _COL_REF)
            i_type = _match_col(headers, _COL_TYPE)

            if i_date is None or i_desc is None:
                continue  # not a transaction table
            if i_in is None and i_out is None and i_amt is None:
                continue

            for row in table[1:]:
                if not row or all(c is None or str(c).strip() == '' for c in row):
                    continue

                def cell(idx):
                    if idx is None or idx >= len(row):
                        return None
                    return row[idx]

                date_val = cell(i_date)
                if not date_val or not str(date_val).strip():
                    continue
                d = _parse_date_str(str(date_val).strip(), year_hint)
                if d is None:
                    continue

                desc = _scrub(str(cell(i_desc) or '').strip())

                money_in  = _try_parse_amount_cell(cell(i_in))  or 0.0
                money_out = _try_parse_amount_cell(cell(i_out)) or 0.0
                balance   = _try_parse_amount_cell(cell(i_bal))

                # Signed amount column (positive = in, negative = out)
                if i_amt is not None and money_in == 0.0 and money_out == 0.0:
                    raw_amt = _try_parse_amount_cell(cell(i_amt))
                    if raw_amt is not None:
                        if raw_amt >= 0:
                            money_in = raw_amt
                        else:
                            money_out = -raw_amt

                if money_in == 0.0 and money_out == 0.0:
                    continue

                ref  = _scrub(str(cell(i_ref)  or '').strip())
                typ  = str(cell(i_type) or '').strip()

                transactions.append({
                    'date': d, 'description': desc,
                    'subcategory': typ, 'reference': ref, 'csv_category': '',
                    'money_in': round(money_in, 2),
                    'money_out': round(money_out, 2),
                    'balance': balance,
                })

    return transactions


# ── Public entry point ────────────────────────────────────────────────────────

def parse_pdf(path, year_hint: int = None) -> list[dict]:
    """Parse a bank statement PDF and return transactions.

    Tries the Barclays text-mode parser first, then a generic table parser.
    Raises ValueError if no transactions can be extracted.

    year_hint: the calendar year (e.g. 2025). Auto-detected from the filename
               if not supplied.
    """
    path = Path(path)
    if year_hint is None:
        year_hint = _infer_year(path)

    with pdfplumber.open(path) as pdf:
        # Layer 1: Barclays text-mode
        txns = _parse_barclays(pdf, year_hint)
        if txns:
            print(f"  [parse_pdf] Barclays parser: {len(txns)} transactions from {path.name}")
            return sorted(txns, key=lambda t: t['date'])

        # Layer 2: Generic table extraction
        txns = _parse_generic_table(pdf, year_hint)
        if txns:
            print(f"  [parse_pdf] Generic table parser: {len(txns)} transactions from {path.name}")
            return sorted(txns, key=lambda t: t['date'])

    raise ValueError(
        f"Could not read any transactions from '{path.name}'. "
        "Supported: Barclays text statements and any bank PDF with a clear table layout. "
        "If your bank's PDF is not working, please export a CSV instead — "
        "most online banking portals offer a 'Download transactions (CSV)' option. "
        f"(Year hint: {year_hint})"
    )

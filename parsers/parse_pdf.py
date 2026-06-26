"""Parse a Barclays PDF bank statement.

The Barclays statement has a text-based table:
    Date | Description | Money out £ | Money in £ | Balance £

Key behaviours handled:
- Dates appear once and carry forward to subsequent rows on the same day.
- Descriptions can wrap to the next line (joined with a space).
- Ref: lines are appended to the previous description.
- Non-transaction lines are skipped (Start Balance, Balance brought/carried
  forward, Total Payments/Receipts, page headers/footers, sidebar glances).
- The running Balance column is used to fill column I.
- Account number, sort code, IBAN are NEVER returned (privacy).

Returns the same shape as parse_csv:
    {
        'date':        datetime.date,
        'description': str,
        'subcategory': str,   # always '' – PDF has no subcategory field
        'money_in':    float,
        'money_out':   float,
        'balance':     float | None,
    }
"""

import re
from datetime import datetime
from pathlib import Path

import pdfplumber


# Matches "6 Apr", "12 Apr", "1 May" at the start of a line
_DATE_PREFIX = re.compile(
    r'^(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec))\s+(.*)',
    re.IGNORECASE,
)

# Matches one or two decimal amounts at the end of a line
# e.g. "... 5.50 15,676.83" or "... 375.00 15,983.59"
_TWO_AMOUNTS = re.compile(r'^(.*?)\s+([\d,]+\.\d{2})\s+([\d,]+\.\d{2})\s*$')
_ONE_AMOUNT = re.compile(r'^(.*?)\s+([\d,]+\.\d{2})\s*$')

# Lines that are NOT transactions and should be skipped entirely
_SKIP_RE = re.compile(
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

# Lines that mark the END of real transaction data on a page – flush and ignore rest
_END_OF_TXNS_RE = re.compile(
    r'balance carried forward|total payments|total receipts|helpful information',
    re.IGNORECASE,
)

# Sidebar "at a glance" amounts that appear inline with page 1 transactions
_SIDEBAR_SUFFIX = re.compile(
    r'\s+u\s+.*$'
    r'|\s+Money (?:in|out)\s+.*$'
    r'|\s+End balance\s+.*$'
    r'|\s+by the Financial Services.*$'
    r'|\s+Compensation Scheme.*$',
    re.IGNORECASE,
)

# All decimal amounts within a line (for fallback extraction)
_ALL_AMOUNTS_RE = re.compile(r'[\d,]+\.\d{2}')


def _parse_amount(s: str) -> float:
    return float(s.replace(',', ''))


def _extract_amounts_fallback(text: str):
    """Scan text for the rightmost two decimal numbers → (desc, amount, balance).

    Used when a line has trailing non-decimal junk (e.g. sidebar phrases)
    that prevent the main regexes from matching.
    Returns None if fewer than 2 decimal numbers found.
    """
    matches = list(_ALL_AMOUNTS_RE.finditer(text))
    if len(matches) < 2:
        return None
    bal_m = matches[-1]
    amt_m = matches[-2]
    balance = _parse_amount(bal_m.group())
    amount  = _parse_amount(amt_m.group())
    desc = text[:amt_m.start()].strip()
    return desc, amount, balance


def _parse_date(s: str) -> datetime.date:
    for fmt in ('%d %b %Y', '%d %b'):
        try:
            d = datetime.strptime(s, fmt)
            if fmt == '%d %b':
                d = d.replace(year=datetime.now().year)
            return d.date()
        except ValueError:
            pass
    raise ValueError(f"Cannot parse date: {s!r}")


def parse_pdf(path, year_hint: int = None) -> list[dict]:
    """Parse the Barclays PDF at *path* and return transactions.

    year_hint: the calendar year of the statement (for parsing bare dates
    like '6 Apr' without a year). Defaults to the current year.
    """
    path = Path(path)
    if year_hint is None:
        year_hint = datetime.now().year

    transactions = []
    current_date = None
    prev_balance = None
    # Accumulate the current in-progress transaction
    pending = None  # dict or None

    def flush_pending():
        if pending is not None:
            transactions.append(pending.copy())

    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text:
                continue

            lines = text.split('\n')
            for raw_line in lines:
                line = raw_line.strip()
                if not line:
                    continue

                # Strip sidebar clutter (page 1 "at a glance" column)
                line = _SIDEBAR_SUFFIX.sub('', line).strip()

                # End-of-transactions marker: flush pending and skip rest of page
                if _END_OF_TXNS_RE.search(line):
                    flush_pending()
                    pending = None
                    break  # stop processing this page's lines

                # Skip non-transaction boilerplate
                if _SKIP_RE.search(line):
                    # Special case: extract start balance for tracking
                    m = re.search(r'start balance\s+([\d,]+\.\d{2})', line, re.I)
                    if m:
                        prev_balance = _parse_amount(m.group(1))
                    continue

                # Try to detect a date prefix: "8 Apr Some description 5.50 12345.67"
                date_match = _DATE_PREFIX.match(line)
                if date_match:
                    date_str = date_match.group(1).strip()
                    rest = date_match.group(2).strip()
                    # Parse the date, inject year_hint
                    try:
                        current_date = datetime.strptime(
                            f"{date_str} {year_hint}", '%d %b %Y'
                        ).date()
                    except ValueError:
                        pass
                    line = rest  # process the remainder of the line

                # Check if the line (or remainder) has transaction amounts
                m2 = _TWO_AMOUNTS.match(line)
                m1 = _ONE_AMOUNT.match(line) if not m2 else None

                if m2:
                    # description + amount + balance
                    desc_part = m2.group(1).strip()
                    balance_str = m2.group(3)
                    flush_pending()
                    balance = _parse_amount(balance_str)
                    delta = balance - prev_balance if prev_balance is not None else None
                    if delta is not None:
                        money_in = round(delta, 2) if delta > 0.001 else 0.0
                        money_out = round(-delta, 2) if delta < -0.001 else 0.0
                    else:
                        amt = _parse_amount(m2.group(2))
                        money_in = 0.0
                        money_out = amt
                    prev_balance = balance
                    pending = {
                        'date': current_date,
                        'description': desc_part,
                        'subcategory': '',
                        'money_in': money_in,
                        'money_out': money_out,
                        'balance': balance,
                    }

                elif m1:
                    desc_part = m1.group(1).strip()
                    balance_str = m1.group(2)
                    if not desc_part:
                        prev_balance = _parse_amount(balance_str)
                        continue
                    flush_pending()
                    balance = _parse_amount(balance_str)
                    delta = balance - prev_balance if prev_balance is not None else None
                    if delta is not None:
                        money_in = round(delta, 2) if delta > 0.001 else 0.0
                        money_out = round(-delta, 2) if delta < -0.001 else 0.0
                    else:
                        money_in = 0.0
                        money_out = 0.0
                    prev_balance = balance
                    pending = {
                        'date': current_date,
                        'description': desc_part,
                        'subcategory': '',
                        'money_in': money_in,
                        'money_out': money_out,
                        'balance': balance,
                    }

                else:
                    # No clean match – try fallback (handles sidebar junk after amounts)
                    fb = _extract_amounts_fallback(line)
                    if fb is not None:
                        desc_part, _amt, balance = fb
                        flush_pending()
                        delta = balance - prev_balance if prev_balance is not None else None
                        if delta is not None:
                            money_in = round(delta, 2) if delta > 0.001 else 0.0
                            money_out = round(-delta, 2) if delta < -0.001 else 0.0
                        else:
                            money_in = 0.0
                            money_out = _amt
                        prev_balance = balance
                        pending = {
                            'date': current_date,
                            'description': desc_part,
                            'subcategory': '',
                            'money_in': money_in,
                            'money_out': money_out,
                            'balance': balance,
                        }
                    else:
                        # Pure continuation of previous description
                        if pending is not None and line:
                            pending['description'] = (
                                pending['description'] + ' ' + line
                            ).strip()

    flush_pending()

    # Remove any rows with no date or zero amounts that crept through
    transactions = [
        t for t in transactions
        if t['date'] is not None and (t['money_in'] > 0 or t['money_out'] > 0)
    ]

    return transactions

"""UK financial year helpers.

The UK tax year runs 6 April to 5 April.
  - On/after 6 April of year Y  → FY Y/Y+1, SA=FY{YY}, ACC={YY}/{YY+1}
  - Before 6 April of year Y    → FY (Y-1)/Y, SA=FY{YY-1}, ACC={YY-1}/{YY}

Example: 2 May 2024 → start_year=2024 → SA='FY24', ACC='24/25'
"""

from datetime import date as _date


def get_fy(d):
    """Return (sa, acc) for a date d.

    sa  – e.g. 'FY24'
    acc – e.g. '24/25'
    """
    if isinstance(d, str):
        raise TypeError("Expected date/datetime, got str")
    month = d.month
    day = d.day
    year = d.year
    if month > 4 or (month == 4 and day >= 6):
        start = year
    else:
        start = year - 1
    end = start + 1
    sa = f"FY{str(start)[2:]}"
    acc = f"{str(start)[2:]}/{str(end)[2:]}"
    return sa, acc

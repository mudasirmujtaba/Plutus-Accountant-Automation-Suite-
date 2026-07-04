"""Dynamic Excel writer for Milestone 1.

Works with any client template by reading column headers from the RAW sheet
at runtime. Sheet names and column positions are auto-detected.
"""

import re
import shutil
from datetime import datetime
from pathlib import Path

import openpyxl
from openpyxl.utils import get_column_letter

from core.financial_year import get_fy


# ── Sheet detection ───────────────────────────────────────────────────────────

def _detect_sheet(wb: openpyxl.Workbook, keyword: str) -> str:
    """Return first sheet name containing keyword (case-insensitive)."""
    kw = keyword.lower()
    for name in wb.sheetnames:
        if kw in name.lower():
            return name
    raise KeyError(f"No sheet containing '{keyword}' found in {wb.sheetnames}")


# ── Column index helpers ──────────────────────────────────────────────────────

def _read_headers(ws) -> dict:
    """Return {header_stripped_lower: 1-based_col_index} for the first row."""
    row1 = next(ws.iter_rows(min_row=1, max_row=1, values_only=True), ())
    return {str(v).strip().lower(): i + 1 for i, v in enumerate(row1) if v is not None}


def _col(hdrs: dict, *names: str):
    """Return 1-based col index for the first matching header name, or None."""
    for n in names:
        idx = hdrs.get(n.lower())
        if idx is not None:
            return idx
    return None


def _detect_year_col_format(ws, col_idx: int) -> str:
    """Detect the format of a year column from existing data values.

    Returns one of:
      'sa_range'   "SA24/25"
      'sa_dotted'  "SA23.24"
      'sa_short'   "SA24"
      'fy_label'   "FY24"
      'acc_range'  "24/25"
      'year_num'   "2025"
    """
    for row in ws.iter_rows(min_row=2, max_row=min(ws.max_row, 15), values_only=True):
        val = row[col_idx - 1] if len(row) >= col_idx else None
        if val:
            s = str(val).strip()
            if re.match(r'^SA\d{2}/\d{2}$', s):     return 'sa_range'
            if re.match(r'^SA\d{2}\.\d{2}$', s):    return 'sa_dotted'
            if re.match(r'^SA\d{2}$', s):            return 'sa_short'
            if re.match(r'^FY\d{2}$', s, re.I):     return 'fy_label'
            if re.match(r'^\d{2}/\d{2}$', s):       return 'acc_range'
            if re.match(r'^\d{4}$', s):              return 'year_num'
    return 'fy_label'  # default


def _format_year(sa: str, acc: str, fmt: str):
    """Format a year value for a specific column format.

    sa  = "FY25"  (start-year label from get_fy)
    acc = "25/26" (year range from get_fy)
    """
    acc_start = acc[:2]   # "25"
    acc_end   = acc[3:]   # "26"
    if fmt == 'sa_range':   return f"SA{acc}"
    if fmt == 'sa_dotted':  return f"SA{acc_start}.{acc_end}"
    if fmt == 'sa_short':   return f"SA{acc_end}"
    if fmt == 'fy_label':   return sa
    if fmt == 'acc_range':  return acc
    if fmt == 'year_num':   return int(f"20{acc_end}")
    return sa  # fallback


# ── Analysis rebuild ──────────────────────────────────────────────────────────

def _rebuild_analysis(
    wb: openpyxl.Workbook,
    raw_ws,
    year_col: int,
    net_col: int,
    uc_col: int,
    analysis_name: str,
) -> None:
    """Rebuild the Analysis sheet with SUMIFS formulas against the RAW sheet."""
    raw_name     = raw_ws.title
    year_letter  = get_column_letter(year_col)
    net_letter   = get_column_letter(net_col)
    uc_letter    = get_column_letter(uc_col)

    # Collect unique year values (##/## range style OR FY## label style)
    years: set = set()
    for row in raw_ws.iter_rows(
        min_row=2, max_row=raw_ws.max_row, min_col=year_col, max_col=year_col, values_only=True
    ):
        val = row[0]
        if val:
            s = str(val).strip()
            if re.match(r'^\d{2}/\d{2}$', s) or re.match(r'^FY\d{2}$', s, re.I):
                years.add(s)
    acc_years = sorted(years)

    # Collect unique category values from UC Category column
    cats: set = set()
    for row in raw_ws.iter_rows(
        min_row=2, max_row=raw_ws.max_row, min_col=uc_col, max_col=uc_col, values_only=True
    ):
        val = row[0]
        if val and str(val).strip():
            cats.add(str(val).strip())

    ws_a = wb[analysis_name]
    ws_a.delete_rows(1, ws_a.max_row)

    n_years = len(acc_years)

    # Row 3: title
    ws_a.cell(row=3, column=1, value='Sum of NET')
    ws_a.cell(row=3, column=2, value='Column Labels')

    # Row 4: headers
    ws_a.cell(row=4, column=1, value='Row Labels')
    for j, yr in enumerate(acc_years):
        ws_a.cell(row=4, column=2 + j, value=yr)

    # Rows 5+: one per category
    for r_off, cat in enumerate(sorted(cats)):
        r = 5 + r_off
        ws_a.cell(row=r, column=1, value=cat)
        for j, yr in enumerate(acc_years):
            yr_ref = f"${get_column_letter(2 + j)}$4"
            formula = (
                f"=SUMIFS('{raw_name}'!${net_letter}:${net_letter},"
                f"'{raw_name}'!${year_letter}:${year_letter},{yr_ref},"
                f"'{raw_name}'!${uc_letter}:${uc_letter},$A{r})"
            )
            ws_a.cell(row=r, column=2 + j, value=formula)

    # Grand Total row
    total_r = 5 + len(cats)
    ws_a.cell(row=total_r, column=1, value='Grand Total')
    for j in range(n_years):
        col_letter = get_column_letter(2 + j)
        ws_a.cell(row=total_r, column=2 + j,
                  value=f"=SUM({col_letter}5:{col_letter}{total_r - 1})")


# ── Main entry point ──────────────────────────────────────────────────────────

def write_workbook(
    transactions: list,
    categories: list,
    template_path,
    output_path,
    sheet_name: str = None,
) -> None:
    """Append transactions to template and save to output_path.

    sheet_name – RAW sheet to use; auto-detected if None.
    """
    template_path = Path(template_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    shutil.copy2(template_path, output_path)
    wb = openpyxl.load_workbook(output_path)

    # ── Detect RAW sheet ──────────────────────────────────────────────────────
    if sheet_name:
        try:
            ws = wb[sheet_name]
        except KeyError:
            ws = wb[_detect_sheet(wb, 'raw')]
    else:
        ws = wb[_detect_sheet(wb, 'raw')]

    # ── Build column index from template headers ───────────────────────────────
    hdrs = _read_headers(ws)

    no_col    = _col(hdrs, 'No', '#')
    sa_col    = _col(hdrs, 'SA')
    acc_col   = _col(hdrs, 'ACC', 'AC')
    date_col  = _col(hdrs, 'Date')
    desc_col  = _col(hdrs, 'Counter Party', 'Description', 'Transaction description',
                     'Details', 'Memo', 'Narrative')
    ref_col   = _col(hdrs, 'Reference', 'Ref')
    type_col  = _col(hdrs, 'Type', 'Transaction Type', 'Transaction type')
    in_col    = _col(hdrs, 'Paid in', 'Paid In', 'IN', 'In', 'In (£)', 'In (GBP)')
    out_col   = _col(hdrs, 'Paid out', 'Paid Out', 'OUT', 'Out', 'Out (£)', 'Out (GBP)')
    amt_col   = _col(hdrs, 'Amount (GBP)', 'Amount (£)', 'Amount')
    bal_col   = _col(hdrs, 'Balance', 'Balance (GBP)', 'Balance (£)')
    net_col   = _col(hdrs, 'NET', 'Net')
    buc_col   = _col(hdrs, 'Balance UC')
    chk_col   = _col(hdrs, 'Check UC', 'Check')
    csv_cat_col = _col(hdrs, 'Spending Category', 'Category name')
    uc_col    = _col(hdrs, 'UC category', 'UC Category')

    # Detect year column formats from existing data
    sa_fmt  = _detect_year_col_format(ws, sa_col)  if sa_col  else None
    acc_fmt = _detect_year_col_format(ws, acc_col) if acc_col else None
    fy_col  = _col(hdrs, 'FY')
    fy_fmt  = _detect_year_col_format(ws, fy_col)  if fy_col  else None

    # Determine NET formula target and signed-amount column
    # When in_col and out_col exist: net formula is written to net_col or amt_col (as fallback)
    # When only amt_col: no formula — write static signed value
    if net_col and in_col and out_col:
        net_formula_col = net_col
        signed_col = amt_col if (amt_col and amt_col != net_col) else None
    elif not net_col and amt_col and in_col and out_col:
        net_formula_col = amt_col
        signed_col = None
    elif amt_col and not in_col and not out_col:
        net_formula_col = None
        signed_col = amt_col
    else:
        net_formula_col = None
        signed_col = None

    # ── Find last row and highest sequence number ─────────────────────────────
    last_row = ws.max_row
    last_no = 0
    if no_col:
        for row in ws.iter_rows(
            min_row=2, max_row=last_row, min_col=no_col, max_col=no_col, values_only=True
        ):
            val = row[0]
            if val is not None:
                try:
                    last_no = max(last_no, int(val))
                except (TypeError, ValueError):
                    pass

    # ── Write transaction rows ────────────────────────────────────────────────
    def w(col, val):
        if col:
            ws.cell(row=r, column=col, value=val)

    for i, (txn, cat) in enumerate(zip(transactions, categories)):
        r = last_row + 1 + i
        seq = last_no + 1 + i

        d = txn['date']
        if not isinstance(d, datetime):
            d = datetime(d.year, d.month, d.day)

        sa, acc = get_fy(d)
        money_in  = txn['money_in']
        money_out = txn['money_out']
        balance   = txn.get('balance')

        w(no_col,   seq)
        if sa_col  and sa_fmt:  w(sa_col,  _format_year(sa, acc, sa_fmt))
        if acc_col and acc_fmt: w(acc_col, _format_year(sa, acc, acc_fmt))
        if fy_col  and fy_fmt:  w(fy_col,  _format_year(sa, acc, fy_fmt))
        w(date_col, d)
        w(desc_col, txn.get('description') or None)
        w(ref_col,  txn.get('reference')   or None)
        w(type_col, txn.get('subcategory') or None)
        w(in_col,   money_in  if money_in  > 0 else None)
        w(out_col,  money_out if money_out > 0 else None)
        w(bal_col,  balance)
        w(csv_cat_col, txn.get('csv_category') or None)
        w(uc_col,   cat)

        # Signed amount column (e.g. Matthew Farris "Amount (GBP)")
        if signed_col:
            signed = money_in if money_in > 0 else (-money_out if money_out > 0 else None)
            w(signed_col, signed)

        # NET formula
        if net_formula_col and in_col and out_col:
            in_l  = get_column_letter(in_col)
            out_l = get_column_letter(out_col)
            w(net_formula_col, f'={in_l}{r}-{out_l}{r}')

        # Balance UC formula chain
        if buc_col and net_formula_col:
            buc_l = get_column_letter(buc_col)
            net_l = get_column_letter(net_formula_col)
            if i == 0 and last_row > 1:
                w(buc_col, f'={buc_l}{last_row}+{net_l}{r}')
            elif i == 0:
                w(buc_col, f'={net_l}{r}')
            else:
                w(buc_col, f'={buc_l}{r - 1}+{net_l}{r}')

        # Check UC formula (only when balance is present in the statement)
        if chk_col and bal_col and buc_col and balance is not None:
            bal_l = get_column_letter(bal_col)
            buc_l = get_column_letter(buc_col)
            w(chk_col, f'={bal_l}{r}-{buc_l}{r}')

    # ── Rebuild Analysis pivot ────────────────────────────────────────────────
    try:
        analysis_name = _detect_sheet(wb, 'analysis')
    except KeyError:
        print("  [excel_writer] No Analysis sheet found — skipping pivot rebuild.")
        wb.save(output_path)
        print(f"  [excel_writer] Saved -> {output_path}")
        return

    # Choose year-grouping column for Analysis SUMIFS.
    # Prefer the column that has range-style values (24/25) since it's most distinct,
    # but any year column works — SUMIFS just matches whatever value is in the header cell.
    pivot_year_col = acc_col or fy_col or sa_col

    if not pivot_year_col or not net_formula_col or not uc_col:
        print("  [excel_writer] Missing year/net/category columns — skipping Analysis rebuild.")
    else:
        print(f"  [excel_writer] Rebuilding {analysis_name} pivot...")
        _rebuild_analysis(wb, ws, pivot_year_col, net_formula_col, uc_col, analysis_name)

    wb.save(output_path)
    print(f"  [excel_writer] Saved -> {output_path}")

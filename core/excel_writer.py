"""Excel writer for Milestone 1.

Loads the master template (Bank_summarised_Behesta_v1_2025.xlsx), appends
new transaction rows to RAW (2) in the exact A-M column layout with live
Excel formulas, then rebuilds the Analysis 24 Raw (2) pivot using SUMIFS.

Column layout of RAW (2) / RAW (3):
    A  No            – sequential integer
    B  SA            – FY label e.g. 'FY24'
    C  ACC           – '24/25'
    D  Date          – Excel date (datetime)
    E  Subcategory   – bank's own type
    F  Memo          – cleaned description
    G  Paid in       – positive credit amount
    H  Paid out      – positive debit amount
    I  Balance       – from statement; blank if not available
    J  NET           – formula =G{row}-H{row}
    K  Balance UC    – formula =J{row} (first) or =K{prev}+J{row}
    L  Check UC      – formula =I{row}-K{row} (only when I has a value)
    M  UC Category   – Claude's category
"""

import re
import shutil
from datetime import datetime
from pathlib import Path

import openpyxl
from openpyxl.utils import get_column_letter

from core.financial_year import get_fy


# ── Category metadata (read from the existing Analysis tab) ──────────────────
# PL/BS tag and presentation name for each category.
# These are extracted from the real template and normalised to Title Case.

_DEFAULT_META: dict[str, tuple[str, str]] = {
    'Accountancy':              ('BS', 'Accountancy'),
    'Bank charges':             ('PL', 'Bank charges'),
    'Car Insurance':            ('PL', 'Car Insurance'),
    'Charging':                 ('PL', 'Charging'),
    'Company Car':              ('PL', 'Company Car'),
    'Directors salary':         ('PL', 'Directors salary'),
    'DLA':                      ('BS', 'DLA'),
    'Donation':                 ('PL', 'Donations'),
    'Entertainment':            ('PL', 'Entertainment'),
    'Equipment':                ('PL', 'Equipment'),
    'Gym':                      ('PL', 'Benefits'),
    'HMRC':                     ('BS', 'Corporation tax'),
    'In/Out':                   ('PL', 'In/Out'),
    'Income':                   ('PL', 'Income'),
    'Insurance':                ('PL', 'Insurance'),
    'Interest income':          ('PL', 'Interest income'),
    'Investment':               ('BS', 'Investment'),
    'Lunch':                    ('PL', 'Subiststence'),
    'Mobile phone':             ('PL', 'Mobile'),
    'Mother Salary':            ('PL', 'Wages'),
    'Parking':                  ('PL', 'Travel'),
    'Penalty fee':              ('BS', 'DLA'),
    'Petrol':                   ('BS', 'DLA'),
    'Postage':                  ('PL', 'Postage'),
    'Professional':             ('PL', 'Professional'),
    'Professional fees - College': ('PL', 'Professional'),
    'Refund':                   ('PL', 'Subiststence'),
    'Subscription':             ('PL', 'Subscription'),
    'Sundry':                   ('PL', 'Subiststence'),
    'Taxes for mother':         ('PL', 'Wages'),
    'Taxi':                     ('PL', 'Travel'),
    'Train':                    ('PL', 'Travel'),
    'Travel':                   ('PL', 'Travel'),
    'Unknown':                  ('BS', 'Unknown'),
    # Legacy entries present in template
    'Lunch?':                   ('PL', 'Subiststence'),
    'Professional ':            ('PL', 'Professional'),
}


def _read_analysis_meta(wb: openpyxl.Workbook) -> dict[str, tuple[str, str]]:
    """Read PL/BS tags and presentation names from the existing Analysis sheet."""
    meta = {}
    ws = wb['Analysis 24 Raw (2)']
    # Headers are in row 4; data starts row 5; categories are in column A.
    # We need to find which column holds PL/BS and which holds presentation name.
    # In the existing template: after the year columns (B, C, D) comes E=PL/BS, F=presentation.
    # We detect year-column count by scanning row 4 for '##/##' patterns.
    header_row = list(ws.iter_rows(min_row=4, max_row=4, values_only=True))[0]
    year_col_count = 0
    for val in header_row[1:]:  # skip column A
        if val and re.match(r'\d{2}/\d{2}', str(val)):
            year_col_count += 1
        else:
            break

    pl_bs_col = 1 + year_col_count + 1   # 1-indexed (A=1)
    pres_col  = pl_bs_col + 1

    for row in ws.iter_rows(min_row=5, max_row=ws.max_row, values_only=True):
        cat = row[0]
        if not cat or str(cat).strip().lower() in ('grand total', ''):
            continue
        pl_bs = row[pl_bs_col - 1] if len(row) >= pl_bs_col else None
        pres  = row[pres_col - 1]  if len(row) >= pres_col  else None
        if cat and pl_bs:
            meta[str(cat).strip()] = (str(pl_bs).strip(), str(pres).strip() if pres else str(cat).strip())

    # Merge with defaults for any missing entries
    for k, v in _DEFAULT_META.items():
        if k not in meta:
            meta[k] = v

    return meta


def _get_all_acc_years(wb: openpyxl.Workbook) -> list[str]:
    """Return sorted list of unique ACC (##/##) values across both RAW sheets."""
    years = set()
    for sheet_name in ('RAW (2)', 'RAW (3)'):
        try:
            ws = wb[sheet_name]
        except KeyError:
            continue
        for row in ws.iter_rows(min_row=2, max_row=ws.max_row, min_col=3, max_col=3, values_only=True):
            val = row[0]
            if val and re.match(r'\d{2}/\d{2}', str(val)):
                years.add(str(val))
    return sorted(years)


def _rebuild_analysis(wb: openpyxl.Workbook, category_meta: dict[str, tuple[str, str]]) -> None:
    """Rebuild the Analysis 24 Raw (2) sheet using SUMIFS formulas."""
    ws = wb['Analysis 24 Raw (2)']
    ws.delete_rows(1, ws.max_row)   # clear everything

    acc_years = _get_all_acc_years(wb)

    # Column layout:
    #   A  = Row Labels (category name)
    #   B+ = one column per FY year
    #   next = PL/BS tag
    #   next = presentation name
    n_years = len(acc_years)
    plbs_col = n_years + 2    # 1-indexed
    pres_col = n_years + 3

    # Row 3: title
    ws.cell(row=3, column=1, value='Sum of NET')
    ws.cell(row=3, column=2, value='Column Labels')

    # Row 4: header
    ws.cell(row=4, column=1, value='Row Labels')
    for j, yr in enumerate(acc_years):
        ws.cell(row=4, column=2 + j, value=yr)
    ws.cell(row=4, column=plbs_col, value='PL/BS')
    ws.cell(row=4, column=pres_col, value='Presentation name')

    # Collect ordered categories (use keys from meta, preserving existing Analysis order)
    existing_order = []
    seen = set()
    # First: categories from _DEFAULT_META in their natural order
    for cat in _DEFAULT_META:
        norm = cat.strip()
        if norm and norm.lower() != 'grand total' and norm not in seen:
            existing_order.append(norm)
            seen.add(norm)
    # Then: any categories from meta not already listed
    for cat in category_meta:
        norm = cat.strip()
        if norm and norm.lower() != 'grand total' and norm not in seen:
            existing_order.append(norm)
            seen.add(norm)

    data_row_start = 5
    for r_offset, cat in enumerate(existing_order):
        row = data_row_start + r_offset
        meta = category_meta.get(cat, _DEFAULT_META.get(cat, ('PL', cat)))
        ws.cell(row=row, column=1, value=cat)
        ws.cell(row=row, column=plbs_col, value=meta[0])
        ws.cell(row=row, column=pres_col, value=meta[1])

        for j, yr in enumerate(acc_years):
            col = 2 + j
            yr_cell = f"${get_column_letter(col)}$4"  # e.g. $B$4
            # SUMIFS across both RAW sheets
            formula = (
                f"=SUMIFS('RAW (2)'!$J:$J,'RAW (2)'!$C:$C,{yr_cell},'RAW (2)'!$M:$M,$A{row})"
                f"+SUMIFS('RAW (3)'!$J:$J,'RAW (3)'!$C:$C,{yr_cell},'RAW (3)'!$M:$M,$A{row})"
            )
            ws.cell(row=row, column=col, value=formula)

    # Grand Total row
    total_row = data_row_start + len(existing_order)
    ws.cell(row=total_row, column=1, value='Grand Total')
    for j in range(n_years):
        col = 2 + j
        col_letter = get_column_letter(col)
        formula = f"=SUM({col_letter}{data_row_start}:{col_letter}{total_row - 1})"
        ws.cell(row=total_row, column=col, value=formula)


def write_workbook(
    transactions: list[dict],
    categories: list[str],
    template_path,
    output_path,
    sheet_name: str = 'RAW (2)',
) -> None:
    """Append transactions to the template and save to output_path.

    transactions – list of dicts from parse_csv / parse_pdf
    categories   – list of category strings (same length as transactions)
    template_path – path to Bank_summarised_Behesta_v1_2025.xlsx
    output_path   – where to write the result
    sheet_name    – which RAW sheet to append to (default 'RAW (2)')
    """
    template_path = Path(template_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Copy template so we don't modify the original
    shutil.copy2(template_path, output_path)

    wb = openpyxl.load_workbook(output_path)
    ws = wb[sheet_name]

    # Find last existing row number and last sequence number
    last_row = ws.max_row
    last_no = 0
    for row in ws.iter_rows(min_row=2, max_row=last_row, min_col=1, max_col=1, values_only=True):
        val = row[0]
        if val is not None:
            try:
                last_no = max(last_no, int(val))
            except (TypeError, ValueError):
                pass

    prev_k_row = last_row  # row number of the last K formula (for chaining)

    for i, (txn, cat) in enumerate(zip(transactions, categories)):
        new_row = last_row + 1 + i
        seq_no = last_no + 1 + i

        d = txn['date']
        if not isinstance(d, datetime):
            d = datetime(d.year, d.month, d.day)

        sa, acc = get_fy(d)

        money_in  = txn['money_in']  if txn['money_in']  > 0 else None
        money_out = txn['money_out'] if txn['money_out'] > 0 else None
        balance   = txn['balance']

        ws.cell(row=new_row, column=1,  value=seq_no)      # A: No
        ws.cell(row=new_row, column=2,  value=sa)          # B: SA
        ws.cell(row=new_row, column=3,  value=acc)         # C: ACC
        ws.cell(row=new_row, column=4,  value=d)           # D: Date
        ws.cell(row=new_row, column=5,  value=txn.get('subcategory', '') or None)  # E: Subcategory
        ws.cell(row=new_row, column=6,  value=txn['description'] or None)           # F: Memo
        ws.cell(row=new_row, column=7,  value=money_in)    # G: Paid in
        ws.cell(row=new_row, column=8,  value=money_out)   # H: Paid out
        ws.cell(row=new_row, column=9,  value=balance)     # I: Balance

        # J: NET formula
        ws.cell(row=new_row, column=10, value=f'=G{new_row}-H{new_row}')

        # K: Balance UC formula (chain from previous K)
        if new_row == last_row + 1 and last_row > 1:
            ws.cell(row=new_row, column=11, value=f'=K{prev_k_row}+J{new_row}')
        elif new_row == last_row + 1 and last_row == 1:
            ws.cell(row=new_row, column=11, value=f'=J{new_row}')
        else:
            ws.cell(row=new_row, column=11, value=f'=K{new_row - 1}+J{new_row}')

        # L: Check UC – only when balance is present
        if balance is not None:
            ws.cell(row=new_row, column=12, value=f'=I{new_row}-K{new_row}')

        # M: UC Category
        ws.cell(row=new_row, column=13, value=cat)

    # Rebuild Analysis pivot
    print("  [excel_writer] Rebuilding Analysis 24 Raw (2) pivot...")
    category_meta = _read_analysis_meta(wb)
    _rebuild_analysis(wb, category_meta)

    wb.save(output_path)
    print(f"  [excel_writer] Saved to {output_path}")

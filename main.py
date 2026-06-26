"""Plutus Accountant Automation Suite – Milestone 1 entry point.

Usage:
    python main.py --input "Samples/May 24.csv"
    python main.py --input "Samples/Statement 03-MAY-24 AC 23996530  05073028.pdf"
    python main.py --input <path> --template <path> --output <path> --sheet "RAW (2)"

The script:
  1. Parses the input file (CSV or PDF).
  2. Assigns UK financial year labels.
  3. Categorises each transaction (rule layer + Claude Haiku).
  4. Appends rows to the RAW (2) tab of the template workbook.
  5. Rebuilds the Analysis pivot with SUMIFS formulas.
  6. Saves the result to output/.
"""

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

BASE_DIR   = Path(__file__).parent
SAMPLES    = BASE_DIR / 'Samples'
TEMPLATE   = SAMPLES / 'Bank summarised Behesta v1 2025.xlsx'
OUTPUT_DIR = BASE_DIR / 'output'


def main():
    parser = argparse.ArgumentParser(description='Plutus M1 – Bank Statement → Excel')
    parser.add_argument('--input',    required=True,  help='Path to CSV or PDF bank statement')
    parser.add_argument('--template', default=str(TEMPLATE), help='Master Excel template')
    parser.add_argument('--output',   default=None,   help='Output xlsx path (default: output/<input_stem>.xlsx)')
    parser.add_argument('--sheet',    default='RAW (2)', help='RAW sheet to append to')
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: input file not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    template_path = Path(args.template)
    if not template_path.exists():
        print(f"Error: template not found: {template_path}", file=sys.stderr)
        sys.exit(1)

    if args.output:
        output_path = Path(args.output)
    else:
        OUTPUT_DIR.mkdir(exist_ok=True)
        output_path = OUTPUT_DIR / (input_path.stem + '_processed.xlsx')

    suffix = input_path.suffix.lower()

    # ── 1. Parse ──────────────────────────────────────────────────────────────
    print(f"[main] Parsing {input_path.name} ...")
    if suffix == '.csv':
        from parsers.parse_csv import parse_csv
        transactions = parse_csv(input_path)
    elif suffix == '.pdf':
        from parsers.parse_pdf import parse_pdf
        year_hint = _infer_year(input_path.name)
        transactions = parse_pdf(input_path, year_hint=year_hint)
    elif suffix == '.xlsx':
        from parsers.parse_xls import parse_xls
        transactions = parse_xls(input_path)
    else:
        print(f"Error: unsupported file type '{suffix}'. Use .csv, .pdf or .xlsx", file=sys.stderr)
        sys.exit(1)

    print(f"[main] Parsed {len(transactions)} transactions.")
    if not transactions:
        print("[main] No transactions found. Exiting.")
        sys.exit(0)

    # Preview first few rows
    for t in transactions[:3]:
        print(f"  {t['date']}  in={t['money_in']:.2f}  out={t['money_out']:.2f}  {t['description'][:50]}")

    # ── 2. Categorise ─────────────────────────────────────────────────────────
    print("[main] Categorising transactions...")
    from core.categorise import categorise
    categories = categorise(transactions)
    print(f"[main] Categories assigned.")

    # Print summary
    from collections import Counter
    cat_counts = Counter(categories)
    for cat, count in cat_counts.most_common():
        print(f"  {cat}: {count}")

    # ── 3. Write to Excel ─────────────────────────────────────────────────────
    print(f"[main] Writing to {output_path} ...")
    from core.excel_writer import write_workbook
    write_workbook(
        transactions,
        categories,
        template_path=template_path,
        output_path=output_path,
        sheet_name=args.sheet,
    )

    # ── 4. Recalculate (LibreOffice) ──────────────────────────────────────────
    print("[main] Attempting LibreOffice recalculation...")
    from scripts.recalc import recalc
    recalc(output_path)

    print(f"\n[main] Done. Output: {output_path}")


def _infer_year(filename: str) -> int:
    """Try to extract a 4-digit year from a filename, else return current year."""
    import re
    from datetime import datetime
    m = re.search(r'(\d{4})', filename)
    if m:
        yr = int(m.group(1))
        if 2000 <= yr <= 2100:
            return yr
    # Try 2-digit year like "-24"
    m2 = re.search(r'-(\d{2})[^0-9]', filename)
    if m2:
        return 2000 + int(m2.group(1))
    return datetime.now().year


if __name__ == '__main__':
    main()

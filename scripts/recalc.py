"""Run LibreOffice headless recalculation on a workbook.

Usage:
    python scripts/recalc.py path/to/output.xlsx

LibreOffice evaluates all formulas and re-saves the file, producing a clean
workbook with no #REF!, #DIV/0!, #VALUE!, or #NAME? errors.
"""

import subprocess
import sys
import shutil
from pathlib import Path


def recalc(xlsx_path: str | Path) -> None:
    xlsx_path = Path(xlsx_path).resolve()
    if not xlsx_path.exists():
        print(f"[recalc] File not found: {xlsx_path}", file=sys.stderr)
        sys.exit(1)

    # Find LibreOffice binary
    candidates = [
        r'C:\Program Files\LibreOffice\program\soffice.exe',
        r'C:\Program Files (x86)\LibreOffice\program\soffice.exe',
        'soffice',
        'libreoffice',
    ]
    soffice = next((c for c in candidates if shutil.which(c) or Path(c).exists()), None)
    if not soffice:
        print(
            "[recalc] LibreOffice not found. Install from https://www.libreoffice.org/ "
            "or run the workbook in Excel to recalculate.",
            file=sys.stderr,
        )
        return

    out_dir = xlsx_path.parent
    cmd = [
        soffice,
        '--headless',
        '--norestore',
        '--convert-to', 'xlsx',
        '--outdir', str(out_dir),
        str(xlsx_path),
    ]
    print(f"[recalc] Running: {' '.join(str(c) for c in cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"[recalc] LibreOffice stderr:\n{result.stderr}", file=sys.stderr)
    else:
        print(f"[recalc] Done. Output in {out_dir}")


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python scripts/recalc.py <path_to_xlsx>")
        sys.exit(1)
    recalc(sys.argv[1])

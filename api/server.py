"""Plutus Milestone 1 – FastAPI backend.

Endpoints:
  POST /api/upload          – upload CSV/PDF, starts background job, returns job_id
  GET  /api/progress/{id}   – poll job status
  GET  /api/download/{id}   – download processed Excel when status == 'done'
"""

import sys
import threading
import uuid
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

load_dotenv()

# Make root importable (api/ lives one level under project root)
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from main import _infer_year  # noqa: E402

TEMPLATE   = ROOT / 'Samples' / 'Bank summarised Behesta v1 2025.xlsx'
OUTPUT_DIR = ROOT / 'output'
UPLOAD_DIR = ROOT / 'uploads'

OUTPUT_DIR.mkdir(exist_ok=True)
UPLOAD_DIR.mkdir(exist_ok=True)

# In-memory job store  {job_id: {...}}
JOBS: dict[str, dict] = {}

app = FastAPI(title='Plutus Accountant API')

app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_methods=['*'],
    allow_headers=['*'],
)


# ── Background worker ─────────────────────────────────────────────────────────

def _run_pipeline(job_id: str, file_path: Path, original_name: str) -> None:
    job = JOBS[job_id]
    try:
        # Step 1 – parse
        _update(job, step='parsing', progress=10, message='Parsing bank statement…')
        suffix = file_path.suffix.lower()
        if suffix == '.csv':
            from parsers.parse_csv import parse_csv
            transactions = parse_csv(file_path)
        elif suffix == '.pdf':
            from parsers.parse_pdf import parse_pdf
            year_hint = _infer_year(original_name)
            transactions = parse_pdf(file_path, year_hint=year_hint)
        elif suffix == '.xlsx':
            from parsers.parse_xls import parse_xls
            transactions = parse_xls(file_path)
        else:
            raise ValueError(f'Unsupported file type: {suffix}')

        n = len(transactions)
        if n == 0:
            raise ValueError('No transactions found in the uploaded file.')

        # Step 2 – categorise
        _update(job, step='categorising', progress=40,
                message=f'Parsed {n} transactions. Categorising with AI…')
        from core.categorise import categorise
        categories = categorise(transactions)

        # Step 3 – write Excel
        _update(job, step='writing', progress=75,
                message=f'Categorised. Writing to Excel…')
        from core.excel_writer import write_workbook
        stem = Path(original_name).stem
        output_path = OUTPUT_DIR / f"{job_id}_{stem}_processed.xlsx"
        write_workbook(transactions, categories, TEMPLATE, output_path)

        # Done
        from collections import Counter
        cat_summary = dict(Counter(categories).most_common(5))
        _update(job, step='done', progress=100, status='done',
                message=f'Complete! {n} transactions processed.',
                transaction_count=n,
                top_categories=cat_summary,
                output_path=str(output_path),
                output_name=output_path.name)

    except Exception as exc:
        JOBS[job_id].update({'status': 'error', 'progress': 0,
                             'message': str(exc), 'step': 'error'})
    finally:
        # Clean up upload file
        try:
            file_path.unlink(missing_ok=True)
        except Exception:
            pass


def _update(job: dict, **kwargs) -> None:
    job.update(kwargs)
    if 'status' not in kwargs:
        job.setdefault('status', 'processing')


# ── Routes ────────────────────────────────────────────────────────────────────

@app.post('/api/upload')
async def upload(file: UploadFile = File(...)):
    name = file.filename or ''
    ext  = Path(name).suffix.lower()
    if ext not in ('.csv', '.pdf', '.xlsx'):
        raise HTTPException(status_code=400,
                            detail='Only CSV, PDF and XLSX files are supported.')

    job_id     = str(uuid.uuid4())
    saved_path = UPLOAD_DIR / f"{job_id}{ext}"
    content    = await file.read()

    with open(saved_path, 'wb') as fh:
        fh.write(content)

    JOBS[job_id] = {
        'status':   'processing',
        'step':     'queued',
        'progress': 0,
        'message':  'Queued…',
        'filename': name,
    }

    t = threading.Thread(target=_run_pipeline,
                         args=(job_id, saved_path, name),
                         daemon=True)
    t.start()

    return {'job_id': job_id, 'filename': name}


@app.get('/api/progress/{job_id}')
async def progress(job_id: str):
    job = JOBS.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail='Job not found.')
    return job


@app.get('/api/download/{job_id}')
async def download(job_id: str):
    job = JOBS.get(job_id)
    if job is None or job.get('status') != 'done':
        raise HTTPException(status_code=404, detail='File not ready yet.')
    output_path = job.get('output_path')
    if not output_path or not Path(output_path).exists():
        raise HTTPException(status_code=500, detail='Output file missing.')
    return FileResponse(
        output_path,
        media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        filename=job['output_name'],
    )


@app.get('/api/health')
async def health():
    return {'status': 'ok'}

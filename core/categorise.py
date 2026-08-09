"""Transaction categorisation — AI-driven.

Per client request the rule layer was removed: every transaction is
categorised by Claude using ALL available columns (date, description,
type, reference, bank category hint, amounts) — not just the description.

The AI learns each client's own vocabulary from two sources:
 1. The client's template: existing rows already contain the accountant's
    own (description -> category) decisions. These are extracted at runtime
    and given to the AI as examples (highest priority).
 2. core/learned_examples.json: corrections the accountant made on previous
    outputs (built by scripts/learn_from_feedback.py).

The AI prefers the client's own categories, but is NOT limited to them —
if nothing fits, it proposes the most appropriate accounting category.

Privacy: account numbers, sort codes and IBANs are scrubbed from all text
before it is sent to the API.
"""

import json
import os
import re
from pathlib import Path

import anthropic
from dotenv import load_dotenv

load_dotenv()

_MODEL = os.environ.get('CATEGORISE_MODEL', 'claude-sonnet-5')

# Master vocabulary: the client's supplied list plus categories the
# accountant actually used in corrected feedback files.
CATEGORIES = [
    'AOP', 'Accommodation', 'Accountancy', 'Accountancy fee', 'Bank charges',
    'Car', 'Car insurance', 'Car lease', 'Charging Car', 'Cleaning',
    'College', 'Company Car', 'Computer', 'CPD Grant', 'DBS', 'Dinner',
    'Directors Loan Account', 'DLA', 'Directors salary', 'Dividends',
    'Donation', 'Education Course', 'Entertainment', 'Equipment', 'FODO',
    'Food', 'GOC', 'Gym', 'Heat', 'HMRC', 'HMRC-CT', 'HMRC-PAYE', 'HMRC-SA',
    'HMRC-VAT', 'HMRC - maternity pay', 'Hotel', 'Income', 'Insurance',
    'Insurance - AOP', 'Interest income', 'Internet', 'Light and heat',
    'Lunch', 'Marketing', 'Mobile phone', 'Other direct costs', 'Parking',
    'PCSE', 'Penalty fee', 'Petrol', 'Postage', 'Professional fee',
    'Professional - College', 'Professional - AOP', 'Professional - GOC',
    'Purchase', 'Refund', 'Rent', 'Repairs', 'Sales', 'Security', 'SIPP',
    'SMP', 'Staff benefits', 'Stationary', 'Subscriptions', 'Sundry',
    'Taxi', 'Telephone', 'Toll', 'Train', 'Transfer', 'Travel',
    'Trivial benefits', 'Wages', 'Wages-staff', 'Water', 'Website',
    'Work from home', 'Unknown',
]

_LEARNED_PATH = Path(__file__).parent / 'learned_examples.json'


# ── Privacy scrub ─────────────────────────────────────────────────────────────

_SENSITIVE_RE = re.compile(
    r'\bA/?C\s*:?\s*\d{6,}\b'          # "A/C 41204042"
    r'|\b\d{2}-\d{2}-\d{2}\b'          # sort code
    r'|\b\d{8,}\b'                     # bare 8+ digit account-like numbers
    r'|\bIBAN\s*:?\s*[A-Z]{2}\d{2}[A-Z0-9]{4,}\b',
    re.IGNORECASE,
)


def _scrub(text) -> str:
    return _SENSITIVE_RE.sub('#', str(text or ''))


# ── Payee normalisation (shared with learn_from_feedback) ─────────────────────

_STOP = {'CARD', 'PAYMENT', 'TO', 'ON', 'DIRECT', 'DEBIT', 'CREDIT', 'AUTOMATED',
         'ONLINE', 'TRANSACTION', 'VIA', 'MOBILE', 'FP', 'THE', 'REF', 'BGC',
         'TFR', 'DD', 'SO', 'FASTER', 'INWARD', 'OUTWARD', 'BACS', 'RECEIVED',
         'TRANSFER', 'PYMT', 'IN', 'OUT', 'LVP'}


def _payee_key(desc: str) -> str:
    s = str(desc).upper()
    s = re.sub(r'\d+', ' ', s)
    s = re.sub(r'[^A-Z& ]+', ' ', s)
    words = [w for w in s.split() if len(w) > 1 and w not in _STOP]
    return ' '.join(words[:4])


def _load_learned() -> dict:
    if _LEARNED_PATH.exists():
        try:
            with open(_LEARNED_PATH, encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {}


# ── Example assembly ──────────────────────────────────────────────────────────

def _build_examples(client_examples: list | None) -> tuple[list, list]:
    """Merge template examples (priority) with global learned corrections.

    client_examples – list of dicts {'description','type','reference','category'}
                       extracted from the client's own template rows.
    Returns (example_lines, client_categories).
    """
    seen_keys = {}
    lines = []
    client_cats = []

    # 1. Client's own template rows (authoritative for THIS client)
    for ex in (client_examples or []):
        cat = str(ex.get('category') or '').strip()
        desc = str(ex.get('description') or '').strip()
        if not cat or not desc or cat.startswith('='):
            continue
        if cat not in client_cats:
            client_cats.append(cat)
        key = _payee_key(desc)
        if not key or key in seen_keys:
            continue
        seen_keys[key] = True
        ref = str(ex.get('reference') or '').strip()
        typ = str(ex.get('type') or '').strip()
        extra = f' | ref: {_scrub(ref)}' if ref else ''
        extra += f' | type: {typ}' if typ else ''
        lines.append(f'"{_scrub(desc)[:60]}"{extra} -> {cat}')

    # 2. Global corrections from past accountant feedback
    for key, info in _load_learned().items():
        if key in seen_keys:
            continue
        seen_keys[key] = True
        lines.append(f'"{_scrub(info["example"])[:60]}" -> {info["category"]}')

    return lines[:150], client_cats


# ── Claude call ───────────────────────────────────────────────────────────────

_CACHE: dict[tuple, str] = {}
_CANON: dict[str, str] = {c.lower(): c for c in CATEGORIES}


def _cache_key(t: dict) -> tuple:
    return (
        str(t.get('description', '')).upper(),
        str(t.get('reference', '')).upper(),
        'in' if t.get('money_in', 0) > 0 else 'out',
    )


def _build_system_prompt(example_lines: list, client_cats: list) -> str:
    cats = ', '.join(f"'{c}'" for c in CATEGORIES)
    client_block = ''
    if client_cats:
        client_block = (
            "\nThis client's own category vocabulary (STRONGLY prefer these exact "
            "spellings when they apply):\n" + ', '.join(f"'{c}'" for c in client_cats) + '\n'
        )
    ex_block = ''
    if example_lines:
        ex_block = (
            '\nExamples of how this accountant categorises (payee -> category):\n'
            + '\n'.join(example_lines) + '\n'
        )

    return f"""You are an expert UK accountant's assistant categorising bank transactions
for an optician / optometrist practice. For every transaction you receive the
date, description, transaction type, payment reference, the bank's own category
hint, and the money in/out amounts. Use ALL of these fields, not just the
description. The payment reference is often decisive — e.g. a transfer to the
director with reference 'Salary' is a salary, with reference 'Dividend' it is a dividend.
{client_block}{ex_block}
General category list (fallback when the client vocabulary doesn't cover it):
{cats}

Domain knowledge:
- AOP = Association of Optometrists; GOC = General Optical Council;
  FODO = opticians' trade body; PCSE = Primary Care Support England (NHS income);
  DBS = Disclosure and Barring Service; SIPP = personal pension contributions
  (e.g. Hargreaves Lansdown, Vanguard, AJ Bell).
- Payments to the business owner: use the reference and amount pattern to
  distinguish salary (regular, fixed, often ref 'Salary') from dividends
  (ref 'Dividend' or irregular round amounts) from DLA (Directors Loan Account).
- HMRC payments: use the reference to pick HMRC-PAYE / HMRC-VAT / HMRC-CT /
  HMRC-SA. Plain 'HMRC' only when the reference gives no clue.
- Credits from opticians chains (Specsavers, Vision Express, Boots Opticians),
  NHS/PCSE, or locum agencies are 'Income'.
- Petrol stations (Shell, BP, Esso, Texaco, Rontec, MFG, Sainsburys Petrol,
  garage names) are 'Petrol', not Equipment or Food.
- Supermarket small amounts near lunchtime, cafes, bakeries (Greggs, Caffe Nero,
  Sainsbury's Local small amounts) are usually 'Lunch'.

Rules:
1. Return ONLY a JSON array of category strings, one per transaction, same order.
2. Prefer the client's own vocabulary above; then the general list.
3. If genuinely nothing fits, invent the most appropriate short accounting
   category name (e.g. 'Software', 'Cleaning') — do NOT force a bad match.
4. Use 'Unknown' only when the transaction cannot be identified at all."""


def _batch_classify(transactions: list[dict], system_prompt: str) -> list[str]:
    client = anthropic.Anthropic(api_key=os.environ['ANTHROPIC_API_KEY'])

    items = []
    for t in transactions:
        direction = 'IN' if t.get('money_in', 0) > 0 else 'OUT'
        amount = t.get('money_in', 0) if direction == 'IN' else t.get('money_out', 0)
        d = t.get('date')
        parts = [
            f"date: {d}",
            f"desc: {_scrub(t.get('description', ''))}",
        ]
        if t.get('subcategory'):
            parts.append(f"type: {t['subcategory']}")
        if t.get('reference'):
            parts.append(f"ref: {_scrub(t['reference'])}")
        if t.get('csv_category'):
            parts.append(f"bank-hint: {t['csv_category']}")
        parts.append(f"{direction} {amount:.2f}")
        items.append(' | '.join(parts))

    user_msg = 'Categorise these transactions:\n' + '\n'.join(
        f"{i + 1}. {item}" for i, item in enumerate(items)
    )

    response = client.messages.create(
        model=_MODEL,
        max_tokens=4000,
        system=system_prompt,
        messages=[{'role': 'user', 'content': user_msg}],
    )

    text = ''.join(
        block.text for block in response.content if getattr(block, 'type', '') == 'text'
    ).strip()
    match = re.search(r'\[.*\]', text, re.DOTALL)
    if not match:
        raise ValueError(f"Claude returned unexpected output: {text[:200]!r}")
    cats = json.loads(match.group())

    out = []
    for c in cats:
        s = str(c).strip()
        out.append(s if s else 'Unknown')

    # Canonicalise case-variant duplicates ('Bank charge' vs 'Bank Charge')
    # against the master list and everything seen so far this run.
    for s in out:
        _CANON.setdefault(s.lower(), s)
    out = [_CANON[s.lower()] for s in out]

    n = len(transactions)
    if len(out) > n:
        out = out[:n]
    elif len(out) < n:
        out += ['Unknown'] * (n - len(out))
    return out


def categorise(
    transactions: list[dict],
    client_examples: list | None = None,
    batch_size: int = 40,
) -> list[str]:
    """Return a category for each transaction using Claude.

    client_examples – (description/type/reference/category) dicts extracted
    from the client's template; they teach the AI this client's vocabulary.
    """
    example_lines, client_cats = _build_examples(client_examples)
    system_prompt = _build_system_prompt(example_lines, client_cats)
    for c in client_cats:                  # client's own spellings are canonical
        _CANON.setdefault(c.lower(), c)

    results: list = [None] * len(transactions)
    todo_idx, todo_txn = [], []

    for i, t in enumerate(transactions):
        key = _cache_key(t)
        if key in _CACHE:
            results[i] = _CACHE[key]
        else:
            todo_idx.append(i)
            todo_txn.append(t)

    if todo_txn:
        api_key = os.environ.get('ANTHROPIC_API_KEY', '')
        if not api_key or api_key.startswith('sk-ant-...'):
            print(f"  [categorise] No API key — marking {len(todo_txn)} txns as 'Unknown'")
            for i, t in zip(todo_idx, todo_txn):
                results[i] = 'Unknown'
                _CACHE[_cache_key(t)] = 'Unknown'
        else:
            print(f"  [categorise] Model: {_MODEL}, examples: {len(example_lines)} "
                  f"({len(client_cats)} client categories)")
            for start in range(0, len(todo_txn), batch_size):
                batch = todo_txn[start:start + batch_size]
                batch_idx = todo_idx[start:start + batch_size]
                print(f"  [categorise] Claude batch {start // batch_size + 1}: {len(batch)} txns...")
                cats = _batch_classify(batch, system_prompt)
                for i, t, cat in zip(batch_idx, batch, cats):
                    results[i] = cat
                    _CACHE[_cache_key(t)] = cat

    return results

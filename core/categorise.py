"""Transaction categorisation.

Two-layer approach:
 1. Rule layer – fast, zero-cost, handles obvious repeat payees.
 2. Claude Haiku – for anything the rules don't cover.

Results are cached by (description, direction) so repeated payees aren't
re-sent to the API.
"""

import json
import os
import re
from pathlib import Path

import anthropic
from dotenv import load_dotenv

load_dotenv()

# ── Fixed category vocabulary ────────────────────────────────────────────────

CATEGORIES = [
    'Accountancy', 'Bank charges', 'Car Insurance', 'Charging', 'Company Car',
    'DLA', 'Directors salary', 'Donation', 'Entertainment', 'Equipment',
    'Gym', 'HMRC', 'In/Out', 'Income', 'Insurance', 'Interest income',
    'Investment', 'Lunch', 'Mobile phone', 'Mother Salary', 'Parking',
    'Penalty fee', 'Petrol', 'Postage', 'Professional',
    'Professional fees - College', 'Refund', 'Subscription', 'Sundry',
    'Taxes for mother', 'Taxi', 'Train', 'Travel',
]

# ── Rule layer ───────────────────────────────────────────────────────────────
# Each rule: (regex pattern, direction, category)
# direction: 'in' | 'out' | 'any'

_RULES: list[tuple[re.Pattern, str, str]] = [
    (re.compile(r'TFL|TRAVEL CH', re.I), 'any', 'Travel'),
    (re.compile(r'MISS\s+B\s+HAMID|SALARY\s+STO', re.I), 'any', 'Directors salary'),
    (re.compile(r'MRS\s+M\s+HAMID|SEE OPTYX STO', re.I), 'any', 'Mother Salary'),
    (re.compile(r'THE COLLEGE OF OPT|COLLEGE OF OPT|DD\d+\s+DDR', re.I), 'any', 'Professional fees - College'),
    (re.compile(r'HERTS PARKING|RINGGO PARKING|PLACES FOR LONDON', re.I), 'out', 'Parking'),
    (re.compile(r'LONDON BOROUGH OF', re.I), 'out', 'Parking'),
    (re.compile(r'COMMISSION.*CHARGES|CHARGES.*COMMISSION|COMMISSION FOR PERIOD', re.I), 'out', 'Bank charges'),
    (re.compile(r'AYAOPTICS|KITE EYEWEAR', re.I), 'in', 'Income'),
    (re.compile(r'BOOTS OPTICIANS|BOOTS.*OPTICIAN', re.I), 'in', 'Income'),
    (re.compile(r'SPECSAVERS', re.I), 'in', 'Income'),
    (re.compile(r'JETPLUS', re.I), 'in', 'Income'),
    (re.compile(r'JOE THE JUICE|BLANK STREET|CAFFE|COFFEE|WATCHHOUSE|BOMBAY|UZBEK STREET|PEPES', re.I), 'out', 'Lunch'),
    (re.compile(r'SAINSBURYS|SAINSBURY', re.I), 'out', 'Sundry'),
    (re.compile(r'POST OFFICE', re.I), 'out', 'Postage'),
]


def _direction(txn: dict) -> str:
    return 'in' if txn['money_in'] > 0 else 'out'


def _apply_rules(txn: dict) -> str | None:
    direction = _direction(txn)
    desc = txn['description']
    for pattern, rule_dir, category in _RULES:
        if rule_dir != 'any' and rule_dir != direction:
            continue
        if pattern.search(desc):
            return category
    return None


# ── Claude Haiku categorisation ──────────────────────────────────────────────

_CACHE: dict[tuple[str, str], str] = {}


def _cache_key(txn: dict) -> tuple[str, str]:
    return (txn['description'].upper(), _direction(txn))


_SYSTEM_PROMPT = f"""You are a UK accountant's assistant. Categorise each bank
transaction into exactly one category from this fixed list:

{', '.join(CATEGORIES)}

Rules:
- Return a JSON array of strings, one per transaction, in the same order.
- Never invent a new category name. Use 'Sundry' or 'Unknown' if genuinely unsure.
- Normalise spelling: use Title Case (e.g. 'Lunch', 'Company Car', 'Mother Salary').
- DLA = Director's Loan Account → use 'DLA'.
- 'Income' is the main credit/receipt category.
- Return ONLY the JSON array, nothing else."""


def _batch_classify(transactions: list[dict]) -> list[str]:
    """Send uncached transactions to Claude Haiku and return category list."""
    client = anthropic.Anthropic(api_key=os.environ['ANTHROPIC_API_KEY'])

    items = []
    for t in transactions:
        direction = 'CREDIT' if t['money_in'] > 0 else 'DEBIT'
        items.append(
            f"desc: {t['description']} | subcategory: {t.get('subcategory', '')} | {direction}"
        )

    user_msg = 'Categorise these transactions:\n' + '\n'.join(
        f"{i + 1}. {item}" for i, item in enumerate(items)
    )

    response = client.messages.create(
        model='claude-haiku-4-5-20251001',
        max_tokens=1024,
        system=_SYSTEM_PROMPT,
        messages=[{'role': 'user', 'content': user_msg}],
    )

    text = response.content[0].text.strip()
    # Extract JSON array
    match = re.search(r'\[.*\]', text, re.DOTALL)
    if not match:
        raise ValueError(f"Claude returned unexpected output: {text!r}")
    categories = json.loads(match.group())
    if len(categories) != len(transactions):
        raise ValueError(
            f"Expected {len(transactions)} categories, got {len(categories)}"
        )
    return categories


def categorise(transactions: list[dict], batch_size: int = 40) -> list[str]:
    """Return a category string for each transaction.

    Uses rule layer first, then Claude for the rest. Results are cached.
    """
    results = [None] * len(transactions)
    uncached_indices = []
    uncached_txns = []

    for i, txn in enumerate(transactions):
        # Rule layer
        cat = _apply_rules(txn)
        if cat:
            results[i] = cat
            _CACHE[_cache_key(txn)] = cat
            continue

        # Cache lookup
        key = _cache_key(txn)
        if key in _CACHE:
            results[i] = _CACHE[key]
            continue

        uncached_indices.append(i)
        uncached_txns.append(txn)

    # Batch API calls
    if uncached_txns:
        api_key = os.environ.get('ANTHROPIC_API_KEY', '')
        if not api_key or api_key.startswith('sk-ant-...'):
            print(f"  [categorise] No API key – marking {len(uncached_txns)} txns as 'Sundry'")
            for i, txn in zip(uncached_indices, uncached_txns):
                results[i] = 'Sundry'
                _CACHE[_cache_key(txn)] = 'Sundry'
        else:
            for start in range(0, len(uncached_txns), batch_size):
                batch = uncached_txns[start:start + batch_size]
                batch_idx = uncached_indices[start:start + batch_size]
                print(f"  [categorise] Calling Claude for {len(batch)} transactions...")
                cats = _batch_classify(batch)
                for i, txn, cat in zip(batch_idx, batch, cats):
                    results[i] = cat
                    _CACHE[_cache_key(txn)] = cat

    return results

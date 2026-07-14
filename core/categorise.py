"""Transaction categorisation.

Two-layer approach:
 1. Rule layer – fast, zero-cost, handles obvious repeat payees.
 2. Claude Haiku – for anything the rules don't cover.

Results are cached by (description, direction) so repeated payees are not
re-sent to the API.
"""

import json
import os
import re
from pathlib import Path

import anthropic
from dotenv import load_dotenv

load_dotenv()

# ── Category vocabulary (provided by client) ─────────────────────────────────

CATEGORIES = [
    'AOP',
    'Accommodation',
    'Accountancy',
    'Bank charges',
    'Car',
    'Car insurance',
    'Car lease',
    'Charging Car',
    'Cleaning',
    'Company Car',
    'Computer',
    'CPD Grant',
    'DBS',
    'Dinner',
    'Directors Loan Account',
    "Director's Salary",
    'Dividends',
    'Donation',
    'Education Course',
    'Entertainment',
    'Equipment',
    'FODO',
    'Food',
    'GOC',
    'Gym',
    'Heat',
    'HMRC',
    'HMRC CT',
    'HMRC PAYE',
    'HMRC SA',
    'HMRC VAT',
    'Hotel',
    'Income',
    'Insurance',
    'Insurance - AOP',
    'Interest income',
    'Internet',
    'Light and heat',
    'Lunch',
    'Marketing',
    'Mobile phone',
    'Other direct costs',
    'Parking',
    'PCSE',
    'Penalty fee',
    'Petrol',
    'Postage',
    'Professional Fee',
    'Professional fees - College',
    'Professional fees - GOC',
    'Purchase',
    'Refund',
    'Rent',
    'Repairs',
    'Salary-Staff',
    'Sales',
    'Security',
    'Staff benefits',
    'Staff Salary',
    'Stationary',
    'Subscriptions',
    'Sundry',
    'Taxi',
    'Telephone',
    'Train',
    'Transfer',
    'Travel',
    'Water',
    'Website',
    'Work from home',
]

# ── Rule layer ────────────────────────────────────────────────────────────────
# Each rule: (regex pattern, direction, category)
# direction: 'in' | 'out' | 'any'

_RULES: list[tuple[re.Pattern, str, str]] = [
    # Income / Sales
    (re.compile(r'AYAOPTICS|KITE EYEWEAR', re.I),                        'in',  'Income'),
    (re.compile(r'BOOTS OPTICIANS|BOOTS.*OPTICIAN', re.I),               'in',  'Income'),
    (re.compile(r'SPECSAVERS', re.I),                                     'in',  'Income'),
    (re.compile(r'JETPLUS|VISION EXPRESS|ICONIC EYEWE|KUOONA', re.I),   'in',  'Income'),
    (re.compile(r'LOOKING GOOD OPTICIANS', re.I),                         'in',  'Income'),
    (re.compile(r'GOGGLE BOX', re.I),                                     'in',  'Income'),

    # PCSE — NHS payments
    (re.compile(r'PCSE|PRIMARY CARE SUPPORT', re.I),                     'any', 'PCSE'),

    # Professional bodies
    (re.compile(r'ASSOCIATION OF OPTOMETRISTS|AOP\b', re.I),             'any', 'AOP'),
    (re.compile(r'GENERAL OPTICAL|GOC\b', re.I),                         'any', 'GOC'),
    (re.compile(r'THE COLLEGE OF OPT|COLLEGE OF OPT|DD\d+\s+DDR', re.I),'any', 'Professional fees - College'),
    (re.compile(r'FODO\b', re.I),                                         'any', 'FODO'),
    (re.compile(r'CPD\b|CONTINUING PROFESSIONAL', re.I),                 'any', 'CPD Grant'),

    # HMRC
    (re.compile(r'HMRC PAYE|HMRC.*PAY|PAYE', re.I),                     'out', 'HMRC PAYE'),
    (re.compile(r'HMRC.*VAT|VAT\s+RETURN|HMRC.*VT', re.I),              'out', 'HMRC VAT'),
    (re.compile(r'HMRC.*SA\b|SELF ASSESS', re.I),                        'out', 'HMRC SA'),
    (re.compile(r'HMRC.*CT\b|CORP.*TAX|CORPORATION TAX', re.I),         'out', 'HMRC CT'),
    (re.compile(r'\bHMRC\b', re.I),                                      'any', 'HMRC'),

    # Salaries
    (re.compile(r'MISS\s+B\s+HAMID|SALARY\s+STO|DIRECTOR.*SALARY', re.I), 'any', "Director's Salary"),
    (re.compile(r'MRS\s+M\s+HAMID|SEE OPTYX STO', re.I),                'any', 'Staff Salary'),
    (re.compile(r'SALARY|WAGES|PAYROLL', re.I),                          'out', 'Staff Salary'),

    # Directors Loan Account
    (re.compile(r'\bDLA\b|DIRECTOR.*LOAN|LOAN.*DIRECTOR', re.I),        'any', 'Directors Loan Account'),

    # Travel
    (re.compile(r'\bTFL\b|TRAVEL CH|UNDERGROUND|OYSTER', re.I),         'any', 'Travel'),
    (re.compile(r'\bTRAIN\b|SOUTHERN|GOVIA|THAMESLINK|SOUTHEASTERN|AVANTI', re.I), 'any', 'Train'),
    (re.compile(r'\bUBER\b.*(?!EATS)|\bBOLT\b|ADDISON LEE', re.I),     'out', 'Taxi'),
    (re.compile(r'RINGGO|HERTS PARKING|PLACES FOR LONDON|APCOA', re.I), 'out', 'Parking'),
    (re.compile(r'LONDON BOROUGH OF|COUNCIL.*PARKING|NCP\b', re.I),     'out', 'Parking'),
    (re.compile(r'PETROL|SHELL\b|BP\b|ESSO\b|TEXACO|FUEL', re.I),       'out', 'Petrol'),

    # Food & Drink
    (re.compile(r'JOE THE JUICE|BLANK STREET|WATCHHOUSE|CAFFE NERO|STARBUCKS|COSTA\b', re.I), 'out', 'Lunch'),
    (re.compile(r'BOMBAY|UZBEK STREET|PEPES|PRET\b|EAT\b|ITSU\b|WASABI', re.I), 'out', 'Lunch'),
    (re.compile(r'RESTAURANT|DINING|DINNER|NANDO|WAGAMAMA|DISHOOM', re.I), 'out', 'Dinner'),
    (re.compile(r'DELIVEROO|UBER EATS|JUST EAT|FOOD|GROCERY|MORRISONS|TESCO|SAINSBURY|WAITROSE|LIDL|ALDI', re.I), 'out', 'Food'),

    # Bank charges
    (re.compile(r'COMMISSION.*CHARGES|CHARGES.*COMMISSION|COMMISSION FOR PERIOD', re.I), 'out', 'Bank charges'),
    (re.compile(r'BANK CHARGE|MONTHLY FEE|ACCOUNT FEE', re.I),          'out', 'Bank charges'),

    # Utilities
    (re.compile(r'BRITISH GAS|OCTOPUS ENERGY|E\.ON\b|EDF\b|BULB\b|NPOWER|SSE\b', re.I), 'out', 'Heat'),
    (re.compile(r'THAMES WATER|SEVERN TRENT|ANGLIAN WATER|SOUTHERN WATER', re.I), 'out', 'Water'),
    (re.compile(r'ELECTRICITY|GAS BILL|HEAT BILL|LIGHT AND HEAT', re.I), 'out', 'Light and heat'),
    (re.compile(r'VIRGIN MEDIA|SKY\b|BT\b|TALKTALK|PLUSNET|BROADBAND|INTERNET', re.I), 'out', 'Internet'),
    (re.compile(r'O2\b|EE\b|VODAFONE|THREE\b|GIFFGAFF|MOBILE|PHONE BILL', re.I), 'out', 'Mobile phone'),
    (re.compile(r'BT LANDLINE|TELEPHONE|LANDLINE', re.I),               'out', 'Telephone'),

    # Subscriptions / Software
    (re.compile(r'MICROSOFT|ADOBE|GOOGLE.*WORKSPACE|DROPBOX|ZOOM\b|SLACK\b', re.I), 'out', 'Subscriptions'),
    (re.compile(r'APPLE\.COM|NETFLIX|SPOTIFY|AMAZON PRIME|ICLOUD|SUBSCRIPTION', re.I), 'out', 'Subscriptions'),

    # Office / Equipment
    (re.compile(r'RYMAN|STAPLES|VIKING|POST OFFICE|ROYAL MAIL', re.I),  'out', 'Postage'),
    (re.compile(r'AMAZON|ARGOS|JOHN LEWIS|CURRYS|PC WORLD', re.I),      'out', 'Equipment'),
    (re.compile(r'COMPUTER|LAPTOP|MONITOR|PRINTER|SCANNER', re.I),      'out', 'Computer'),

    # Insurance
    (re.compile(r'AOP.*INSUR|INSUR.*AOP', re.I),                        'out', 'Insurance - AOP'),
    (re.compile(r'INSURANCE|INSURE|PROTECT', re.I),                     'out', 'Insurance'),
    (re.compile(r'CAR INSUR|AUTO INSUR|VEHICLE INSUR', re.I),           'out', 'Car insurance'),

    # DBS
    (re.compile(r'\bDBS\b|DISCLOSURE.*BARRING|CRB CHECK', re.I),        'out', 'DBS'),

    # Rent / Accommodation
    (re.compile(r'\bRENT\b|LANDLORD|LEASE PAYMENT', re.I),              'out', 'Rent'),
    (re.compile(r'HOTEL|TRAVELODGE|PREMIER INN|HOLIDAY INN|AIRBNB', re.I), 'out', 'Hotel'),
    (re.compile(r'ACCOMMODATION|B&B\b', re.I),                          'out', 'Accommodation'),

    # Car
    (re.compile(r'CAR LEASE|VEHICLE FINANCE|PCP\b|HP\b.*CAR', re.I),   'out', 'Car lease'),
    (re.compile(r'EV CHARGE|ELECTRIC VEHICLE|CHARGING POINT|CHARGE.*CAR', re.I), 'out', 'Charging Car'),

    # Transfer (self-transfers between accounts)
    (re.compile(r'TRANSFER|INTERNAL|OWN ACCOUNT|TFR\b', re.I),          'any', 'Transfer'),

    # Interest
    (re.compile(r'INTEREST|INTEREST PAID', re.I),                       'in',  'Interest income'),

    # Accountancy / Legal
    (re.compile(r'ACCOUNTANT|ACCOUNTANCY|BOOKKEEP', re.I),              'out', 'Accountancy'),

    # Marketing
    (re.compile(r'MARKETING|ADVERTIS|GOOGLE ADS|FACEBOOK ADS|META ADS', re.I), 'out', 'Marketing'),

    # Website
    (re.compile(r'GODADDY|WIXSITE|SQUARESPACE|DOMAIN|HOSTING|WEBSITE', re.I), 'out', 'Website'),

    # Gym
    (re.compile(r'\bGYM\b|FITNESS|PURE GYM|NUFFIELD|DAVID LLOYD|VIRGIN ACTIVE', re.I), 'out', 'Gym'),

    # Penalty
    (re.compile(r'PENALTY|FINE\b|PCN\b|CONGESTION CHARGE', re.I),      'out', 'Penalty fee'),
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


# ── Claude Haiku categorisation ───────────────────────────────────────────────

_CACHE: dict[tuple[str, str], str] = {}


def _cache_key(txn: dict) -> tuple[str, str]:
    return (txn['description'].upper(), _direction(txn))


_CATEGORY_LIST = ', '.join(f"'{c}'" for c in CATEGORIES)

_SYSTEM_PROMPT = f"""You are a UK accountant's assistant for an optician's practice.
Categorise each bank transaction into exactly one category from this fixed list:

{_CATEGORY_LIST}

Key guidance for this optician's practice:
- AOP = Association of Optometrists membership/fees
- GOC = General Optical Council registration/fees
- FODO = Federation of Ophthalmic and Dispensing Opticians fees
- PCSE = Primary Care Support England (NHS payment processor) — income credits
- DBS = Disclosure and Barring Service (staff background checks)
- CPD Grant = Continuing Professional Development training
- HMRC PAYE = payroll tax payments to HMRC
- HMRC VAT = VAT payments/refunds
- HMRC SA = Self Assessment tax
- HMRC CT = Corporation Tax
- Director's Salary = salary payment to the director/owner
- Staff Salary = wages for other employees
- Salary-Staff = total staff salary costs
- Directors Loan Account = director drawing money in/out of business loan account
- Transfer = money moved between own accounts (not a real expense)
- Income = patient fees, optical sales, dispensing income
- Sales = product sales revenue
- Professional fees - College = College of Optometrists fees
- Professional fees - GOC = GOC professional fees
- Lunch = coffee, sandwiches, light meals during work
- Dinner = restaurant meals, evening dining
- Food = groceries, general food shopping
- Light and heat = combined electricity and gas bills
- Heat = gas/heating only
- Stationary = stationery, office supplies (note: client uses this spelling)
- Subscriptions = software subscriptions, streaming, recurring digital payments
- Work from home = home office expenses
- Sundry = genuinely unclassifiable (use sparingly — prefer a specific category)

Rules:
- Return a JSON array of strings, one per transaction, in the same order.
- Never invent a new category name — use only the exact names listed above.
- If the csv_hint field strongly matches a category, use it as guidance.
- Use 'Sundry' only as a last resort when nothing else fits.
- Return ONLY the JSON array, nothing else."""


def _batch_classify(transactions: list[dict]) -> list[str]:
    """Send uncached transactions to Claude Haiku and return category list."""
    client = anthropic.Anthropic(api_key=os.environ['ANTHROPIC_API_KEY'])

    items = []
    for t in transactions:
        direction = 'CREDIT' if t['money_in'] > 0 else 'DEBIT'
        hint = t.get('csv_category', '') or ''
        items.append(
            f"desc: {t['description']} | type: {t.get('subcategory', '')} | csv_hint: {hint} | {direction}"
        )

    user_msg = 'Categorise these transactions:\n' + '\n'.join(
        f"{i + 1}. {item}" for i, item in enumerate(items)
    )

    response = client.messages.create(
        model='claude-haiku-4-5-20251001',
        max_tokens=2048,
        system=_SYSTEM_PROMPT,
        messages=[{'role': 'user', 'content': user_msg}],
    )

    text = response.content[0].text.strip()
    match = re.search(r'\[.*\]', text, re.DOTALL)
    if not match:
        raise ValueError(f"Claude returned unexpected output: {text!r}")
    categories = json.loads(match.group())

    # Normalise returned values — map old names to new ones just in case
    _REMAP = {
        'directors salary': "Director's Salary",
        'directors loan':   'Directors Loan Account',
        'in/out':           'Transfer',
        'subscription':     'Subscriptions',
        'professional':     'Professional Fee',
        'mother salary':    'Staff Salary',
        'taxes for mother': 'HMRC PAYE',
        'investment':       'Directors Loan Account',
        'unknown':          'Sundry',
    }
    valid = {c.lower(): c for c in CATEGORIES}
    normalised = []
    for cat in categories:
        s = str(cat).strip()
        lc = s.lower()
        if lc in valid:
            normalised.append(valid[lc])
        elif lc in _REMAP:
            normalised.append(_REMAP[lc])
        else:
            normalised.append('Sundry')

    n = len(transactions)
    if len(normalised) > n:
        print(f"  [categorise] Warning: Claude returned {len(normalised)} categories for {n} — trimming.")
        normalised = normalised[:n]
    elif len(normalised) < n:
        print(f"  [categorise] Warning: Claude returned {len(normalised)} categories for {n} — padding.")
        normalised += ['Sundry'] * (n - len(normalised))

    return normalised


def categorise(transactions: list[dict], batch_size: int = 40) -> list[str]:
    """Return a category string for each transaction.

    Uses rule layer first, then Claude for the rest. Results are cached.
    """
    results = [None] * len(transactions)
    uncached_indices = []
    uncached_txns = []

    for i, txn in enumerate(transactions):
        cat = _apply_rules(txn)
        if cat:
            results[i] = cat
            _CACHE[_cache_key(txn)] = cat
            continue

        key = _cache_key(txn)
        if key in _CACHE:
            results[i] = _CACHE[key]
            continue

        uncached_indices.append(i)
        uncached_txns.append(txn)

    if uncached_txns:
        api_key = os.environ.get('ANTHROPIC_API_KEY', '')
        if not api_key or api_key.startswith('sk-ant-...'):
            print(f"  [categorise] No API key — marking {len(uncached_txns)} txns as 'Sundry'")
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

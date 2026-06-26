# Plutus — Client Guide
### How the Bank Statement Processor works (plain English)

---

## Your most important questions answered

---

### "Was the Excel file brand new or an existing one?"

**It is your existing Excel workbook** — the one called `Bank summarised Behesta v1 2025.xlsx`.

That file already had years of historical transactions in it (1,519 rows of old data going back to 2021). The system does **not** create a new file from scratch and does **not** touch any of your old data.

What it does is simple:

```
BEFORE:
  Your Excel workbook
  Row 1:    Header (No, SA, ACC, Date, Subcategory, Memo, Paid in, Paid out...)
  Row 2:    Sep 2022 transaction
  Row 3:    Sep 2022 transaction
  ...
  Row 1520: Last existing transaction (your old data ends here)

AFTER uploading May 2024 statement:
  Row 1:    Header  ← untouched
  Row 2:    Sep 2022 transaction  ← untouched
  ...
  Row 1520: Last existing transaction  ← untouched
  Row 1521: ← NEW → 02/05/2024  Income   Ayaoptics Ltd  £3,025.00
  Row 1522: ← NEW → 01/05/2024  Travel   TFL Travel     £7.90
  Row 1523: ← NEW → 01/05/2024  Lunch    SQ Blank St    £4.40
  ...
  Row 1567: ← NEW → 08/04/2024  Bank charges  Commission  £8.50
```

**All 47 new transactions from May 2024 are added at the bottom. Nothing else changes.**

---

### "What if it's a CSV file?"

CSV and PDF both work **exactly the same way** — you get the same result either way.

Barclays lets you download your statement in different formats. This system accepts all of them:

| Format | How to download from Barclays | Result |
|--------|-------------------------------|--------|
| **CSV** | Online banking → Statements → Download → CSV | Same 47 rows appended |
| **PDF** | Online banking → Statements → Download → PDF | Same 47 rows appended |
| **XLSX** | Online banking → Statements → Download → Excel | Same 47 rows appended |

The system reads whichever format you give it and produces the same output — your master Excel workbook with the new month's transactions added.

---

### "What did the new bit do exactly?"

For each new transaction the system automatically:

1. **Reads the date** and works out the UK financial year
   - e.g. 2 May 2024 → `FY24`, `24/25`

2. **Recognises the payee** and assigns a category
   - TFL → *Travel*
   - Blank Street / Joe the Juice → *Lunch*
   - Ayaoptics / Specsavers → *Income*
   - Miss B Hamid salary → *Directors salary*
   - etc.

3. **Writes the row** into your RAW tab with the correct columns and formulas:
   - Column J (NET) = Paid in minus Paid out (live formula)
   - Column K (Balance UC) = running total that chains from the previous row (live formula)
   - Column L (Check UC) = compares the printed balance against the running total (live formula)

4. **Rebuilds the Analysis pivot** so the summary tab automatically includes the new month's figures — no manual work needed.

---

### "What does the downloaded file contain?"

When you click **Download Excel**, you receive a copy of your master workbook with the new month already appended. It is a standard `.xlsx` file you can open in Excel immediately.

You will see:
- **RAW (2) tab** — all your historical rows plus the new month's rows at the bottom
- **Analysis 24 Raw (2) tab** — the summary pivot, automatically updated to include the new data

---

### "How does the category assignment work?"

The system uses two layers:

**Layer 1 — Instant rules (no internet needed):**
Known payees are recognised immediately at zero cost. For example:
- Any TFL payment → *Travel*
- Any RINGGO / HERTS PARKING / PLACES FOR LONDON → *Parking*
- Ayaoptics or Kite Eyewear income → *Income*
- Miss B Hamid salary standing order → *Directors salary*
- Mrs M Hamid / See Optyx standing order → *Mother Salary*
- Royal Mail / Post Office → *Postage*
- Barclays commission charges → *Bank charges*
- Joe the Juice / Blank Street / Watchhouse / Bombay Street → *Lunch*

**Layer 2 — Claude AI (for anything not recognised by the rules):**
If a transaction doesn't match any rule, it is sent to Claude AI which picks the closest category from the fixed list. Only the description and whether it was a payment or receipt are sent — never any account numbers or personal details.

---

### "What categories does it use?"

Every transaction is placed into exactly one of these categories:

> Accountancy · Bank charges · Car Insurance · Charging · Company Car · DLA · Directors salary · Donation · Entertainment · Equipment · Gym · HMRC · In/Out · Income · Insurance · Interest income · Investment · Lunch · Mobile phone · Mother Salary · Parking · Penalty fee · Petrol · Postage · Professional · Professional fees - College · Refund · Subscription · Sundry · Taxes for mother · Taxi · Train · Travel

If you ever want a category changed for a specific payee (e.g. BOOTS 1132 should be *Sundry* not *Lunch*), that is a one-line change in the code.

---

### "What does the system NOT do?"

- It does **not** modify the original statement file (CSV/PDF/XLSX) you uploaded
- It does **not** delete or change any of your existing historical data
- It does **not** overwrite your master template — it makes a copy and appends to that copy
- It does **not** send your account number, sort code, IBAN or name to any external service

---

### Step-by-step: what happens when you upload a file

```
1. You drag your Barclays statement onto the website
         ↓
2. The system reads every transaction from the file
         ↓
3. Each transaction is checked against the rule list
   → Known payee? → Category assigned instantly
   → Unknown payee? → Sent to Claude AI for categorisation
         ↓
4. UK financial year labels are calculated for each transaction
         ↓
5. All transactions are written into your Excel workbook
   (appended after the last existing row, with live formulas)
         ↓
6. The Analysis pivot is rebuilt to include the new data
         ↓
7. A download button appears → click to save the updated workbook
```

Total time: typically **15–30 seconds** per statement.

---

### Where does the Excel template live?

The master template is stored in the `Samples` folder:

```
Samples/
└── Bank summarised Behesta v1 2025.xlsx   ← this is your template
```

The system always reads from this template and saves the result to the `output` folder. Your template is never modified.

```
output/
└── [processed file].xlsx   ← this is what you download
```

---

### Quick reference — running the system

Open two command prompt windows:

**Window 1:**
```
cd "Plutus Accountant Automation Suite"
venv\Scripts\uvicorn api.server:app --host 127.0.0.1 --port 8000
```

**Window 2:**
```
cd "Plutus Accountant Automation Suite\frontend"
npm run dev
```

Then go to **http://localhost:5173** in your browser.

---

*For any questions or issues, contact your developer.*

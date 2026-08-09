# Plutus Accountant Automation Suite — Complete Setup Guide

This guide takes you from a blank PC to a fully running system, step by step.
No prior technical knowledge is assumed. Follow the steps in order.

**What you are installing:** a local web application that reads bank statements
(CSV or PDF), categorises every transaction with AI, and appends them to your
Excel working-papers file — matching your existing format, formulas and
financial-year labels exactly.

Everything runs **on your own computer**. Bank statements and Excel files never
leave your machine — only transaction descriptions are sent to the AI service
for categorisation (never account numbers, sort codes, or IBANs).

---

## Part 1 — Install the prerequisites (one time only)

You need four things. Install them in this order.

### 1.1 Git (to download the project)

1. Go to <https://git-scm.com/downloads> and download **Git for Windows**.
2. Run the installer. Accept the default options on every screen (keep
   clicking **Next**, then **Install**).
3. Verify: open **Command Prompt** (press `Win + R`, type `cmd`, press Enter)
   and type:
   ```
   git --version
   ```
   You should see something like `git version 2.45.0`. Any version is fine.

### 1.2 Python 3.10 or newer (runs the processing engine)

1. Go to <https://www.python.org/downloads/> and click **Download Python 3.x**.
2. Run the installer. **IMPORTANT: on the first screen, tick the checkbox
   "Add python.exe to PATH"** before clicking Install. This is the single most
   common setup mistake — do not skip it.
3. Verify in a **new** Command Prompt window:
   ```
   python --version
   ```
   You should see `Python 3.10` or higher (e.g. `Python 3.12.4`).

### 1.3 Node.js 18 or newer (runs the web interface)

1. Go to <https://nodejs.org/> and download the **LTS** version.
2. Run the installer with all default options.
3. Verify in a **new** Command Prompt window:
   ```
   node --version
   npm --version
   ```
   You should see e.g. `v20.11.0` and `10.2.4`.

### 1.4 Anthropic API key (powers the AI categorisation)

1. Go to <https://console.anthropic.com/> and create an account (or sign in).
2. Add billing details under **Settings → Billing** (the AI usage costs a few
   pence per statement processed).
3. Go to **Settings → API Keys → Create Key**, give it any name (e.g.
   "Plutus"), and copy the key. It looks like `sk-ant-api03-...`.
4. Keep it somewhere safe for Part 3. **Treat it like a password** — anyone
   with this key can spend on your account.

---

## Part 2 — Download the project

Open **Command Prompt** and run these commands one at a time.

1. Go to the folder where you want the project (e.g. your Documents):
   ```
   cd %USERPROFILE%\Documents
   ```

2. Download (clone) the project:
   ```
   git clone https://github.com/mudasirmujtaba/Plutus-Accountant-Automation-Suite-.git
   ```

3. Enter the project folder:
   ```
   cd Plutus-Accountant-Automation-Suite-
   ```

Keep this Command Prompt window open — Parts 3 and 4 continue here.

---

## Part 3 — Set up the processing engine (backend)

Still in the project folder from Part 2:

1. Create an isolated Python environment (keeps this project's libraries
   separate from anything else on your PC):
   ```
   python -m venv venv
   ```

2. Activate it:
   ```
   venv\Scripts\activate
   ```
   Your prompt should now start with `(venv)`.

3. Install the required libraries (takes 1–3 minutes):
   ```
   pip install -r requirements.txt
   ```

4. Create your configuration file. Copy the example:
   ```
   copy .env.example .env
   ```

5. Open the new `.env` file in Notepad:
   ```
   notepad .env
   ```
   Replace `sk-ant-...` with your real API key from step 1.4, so the file
   contains one line like:
   ```
   ANTHROPIC_API_KEY=sk-ant-api03-XXXXXXXXXXXXXXXXXXXX
   ```
   Save and close Notepad.

   > **Security note:** the `.env` file stays on your computer and is
   > deliberately excluded from Git — never share it or email it.

---

## Part 4 — Set up the web interface (frontend)

1. From the project folder, move into the frontend folder:
   ```
   cd frontend
   ```

2. Install its libraries (takes 1–3 minutes):
   ```
   npm install
   ```

3. Go back to the project root:
   ```
   cd ..
   ```

Setup is now complete. You never need to repeat Parts 1–4 again.

---

## Part 5 — Run the system

### The easy way (recommended)

Double-click **`start.bat`** in the project folder (or run `start.bat` in
Command Prompt). It opens two small windows — one for the engine, one for the
web interface — and then opens your browser at the right address.

Leave both windows open while you work. Closing them stops the system.

### The manual way (if start.bat gives trouble)

Open **two** Command Prompt windows in the project folder.

**Window 1 — the engine:**
```
venv\Scripts\activate
uvicorn api.server:app --port 8000
```
Wait until you see `Application startup complete`.

**Window 2 — the web interface:**
```
cd frontend
npm run dev
```
Wait until you see `Local: http://localhost:5173/`.

Then open your browser at **http://localhost:5173**

---

## Part 6 — Using the system

1. The page shows **two upload boxes**:
   - **Box 1 — Bank Statement**: drop the bank statement file (CSV, PDF or XLSX)
   - **Box 2 — Excel Template Workbook**: drop the client's working-papers
     Excel file (the one with the RAW and Analysis sheets)
2. Click **Process Statement**.
3. Watch the progress: parsing → AI categorisation → writing to Excel.
4. When it finishes, click **Download** — you get the working-papers file with
   all new transactions appended at the bottom, categorised, with the correct
   financial-year labels and formulas, and the Analysis sheet updated.

**Tips for best results**

- CSV statements are preferred over PDF — they contain the payment reference
  field, which improves categorisation accuracy.
- For PDFs, keep the bank's original filename (it contains the statement date,
  which the system uses to determine the year).
- The template must contain the client's existing rows — the system learns each
  client's categories and financial-year convention from them.
- Scanned/photographed PDFs cannot be read — export a CSV from online banking
  instead.

### Command-line alternative (optional, for bulk work)

With the venv activated, you can process a file without the browser:
```
python main.py --input "path\to\statement.csv" --template "path\to\Working Papers.xlsx" --output "path\to\result.xlsx"
```

---

## Part 7 — Teaching the system (the feedback loop)

The AI gets smarter from corrections:

1. Open an output file and correct any wrong category by typing the right one
   in the **column immediately to the right of "UC Category"** on that row.
2. Save the corrected file into the **`Feedbacks`** folder in the project.
3. Run (with the venv activated):
   ```
   python scripts\learn_from_feedback.py
   ```
4. Done — every future run now knows those corrections permanently.

The system also automatically learns from the existing rows of every template
you upload, so each client's own vocabulary is applied without any setup.

---

## Part 8 — Updating to the latest version

When you're told an update is available, open Command Prompt in the project
folder and run:
```
git pull
venv\Scripts\activate
pip install -r requirements.txt
cd frontend && npm install && cd ..
```
Then restart the system (Part 5). Your `.env`, outputs and Feedbacks folder are
untouched by updates.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `python` / `git` / `npm` is "not recognized" | The tool isn't on your PATH. Re-run its installer (for Python, tick **Add to PATH**), then open a **new** Command Prompt. |
| `venv\Scripts\activate` fails with a policy error in PowerShell | Use Command Prompt (`cmd`) instead, or run PowerShell once as Administrator: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |
| Browser shows "This site can't be reached" | Both windows from Part 5 must be running. Check Window 1 shows `Application startup complete` and Window 2 shows the `Local:` address. |
| "Port 8000 already in use" | An old copy is still running. Close all Command Prompt windows and start again. |
| Every transaction comes back "Unknown" | Your API key is missing or wrong. Re-check the `.env` file (Part 3, steps 4–5), then restart. |
| "Could not read any transactions from ... .pdf" | The PDF layout isn't recognised (or it's a scanned image). Export a CSV from online banking instead, and send us the PDF so we can add support. |
| Categories look wrong for a client | Make sure you uploaded that client's own working papers as the template — the system learns from it. Then use the feedback loop (Part 7). |
| Excel shows `#REF!` or odd values in old rows | Those existed in the template before processing — open the original template to confirm. The system never modifies existing rows. |

---

## What's where (project folders)

| Folder / file | Purpose |
|---|---|
| `api/` | The web server (engine) |
| `frontend/` | The browser interface |
| `parsers/` | CSV / PDF / XLSX statement readers |
| `core/` | AI categorisation, Excel writing, year-label learning |
| `scripts/learn_from_feedback.py` | Feeds your corrections back into the AI |
| `Feedbacks/` | Drop corrected output files here |
| `output/` | Processed files created by the system |
| `uploads/` | Temporary storage during processing (auto-cleaned) |
| `.env` | Your API key — private, never shared or committed |

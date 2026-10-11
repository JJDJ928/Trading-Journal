# Rinse Tracker

A local-first web app for tracking a prop-firm rinse system: evaluations, funded
accounts, a trade journal with screenshots, payouts, and the system's real
statistics. Everything stays on your computer. No broker connection and no
credentials.

## Mac app

Rinse Tracker can be installed as a normal Mac app with its own window (no browser).

**Install**

1. On GitHub open **Actions → Build macOS app**, click the latest green run, and download
   **Rinse-Tracker-macOS** under *Artifacts* (it's a zip containing `Rinse-Tracker.dmg`).
2. Open the `.dmg` and drag **Rinse Tracker** into **Applications**.
3. First launch only: the app isn't signed with an Apple developer certificate, so macOS
   blocks it. Open it once, then go to **System Settings → Privacy & Security**, scroll
   down and click **Open Anyway** (on older macOS: right-click the app → **Open**).

The app keeps your data in `~/Library/Application Support/Rinse Tracker`. To move
records from the browser version, use **Backup & Restore**: download a backup there and
restore it in the app.

The build is for Apple Silicon Macs (M1 and newer). To build it yourself on a Mac:
`bash scripts/build_mac.sh` → `dist/Rinse-Tracker.dmg`. To run the window from source:
`pip install -r requirements.txt -r requirements-desktop.txt && python3 desktop.py`.

## Run it in your browser

**One-time setup**

1. Install Python 3.10 or newer from [python.org/downloads](https://www.python.org/downloads/).
   On Windows, tick **"Add python.exe to PATH"** in the installer.
2. Download this project: on GitHub press **Code → Download ZIP** and unzip it
   (or `git clone` it).
3. Open a terminal in the project folder (Windows: open the folder, type `cmd` in
   the address bar and press Enter; Mac: right-click the folder → *New Terminal at Folder*).
4. Install the requirements:

   ```bash
   pip install -r requirements.txt
   ```
   (On Mac use `pip3` if `pip` isn't found.)

**Every time**

```bash
python run.py            # Mac: python3 run.py
```

Your browser opens at http://127.0.0.1:5050. Keep the terminal window open while you
use the app; close it (or press Ctrl+C) to stop.

Your data is kept in `./data/`:

- `data/rinse.db`: SQLite database (accounts, trades, summaries, payouts, coach conversations)
- `data/uploads/`: screenshot image files (the database stores only their names)
- `data/backups/`: automatic safety copies made before any restore

Closing and reopening the app keeps everything. To keep the data somewhere else,
set `RINSE_DATA_DIR=/path/to/folder`. The welcome screen greets you by name; change it
with `RINSE_USER_NAME=YourName`.

### Demo / sample data

```bash
python run.py --demo
```

This runs against a separate `./demo-data/` folder with sample records and shows a
yellow **DEMO DATA** banner. It never reads or writes `./data/`.

## Using it

| Task | How |
|---|---|
| Add an evaluation | **Accounts → + Add account** (or Dashboard quick action) |
| Pass / fail an evaluation | Open the account → **Mark passed** / **Mark failed** |
| Get the funded account | On a passed evaluation → **Create funded account** (links the two, once) |
| Log a trade | **+ Log trade** (sidebar, always visible), or drag screenshots anywhere onto the page |
| Add screenshots | Drop images onto the trade form, paste with Ctrl+V, or click to browse |
| View full-size screenshots | Click a thumbnail (arrow keys to flip through) |
| Record a payout | Funded account → **+ Record payout**, or the **Payouts** page |
| Back up / restore | **Backup & Restore** in the sidebar |
| Review a trade with the coach | **Review with coach** on any trade, or the **Coach** page |

`Ctrl+Enter` saves any open form. `Esc` closes it.

## AI coach

The **Coach** page is a personal trading coach powered by Claude (model
`claude-opus-5-5`). Press **Review with coach** on any trade to go through it
together, screenshots included, or ask general questions about your journal.
Conversations are saved so you can come back to them.

Setup: create an API key at [console.anthropic.com](https://console.anthropic.com/settings/keys)
and paste it on the Coach page (it's stored in `data/anthropic_api_key`, never in
backups), or set the `ANTHROPIC_API_KEY` environment variable. API usage is billed to
your Anthropic account.

Privacy: this is the only feature that sends data off your computer. Starting a
conversation sends a snapshot of your stats, accounts and recent trades (and, for a
trade review, that trade's screenshots) to the Anthropic API. Everything else stays local.

## How the numbers are calculated

- **Evaluations purchased**: every account of type Evaluation.
- **Passed**: evaluations with a pass date (Passed, Passed → Funded, or Closed after passing).
- **Failed**: evaluations with status Failed / Breached.
- **Pass rate**: passed ÷ (passed + failed). Active evaluations, and evaluations
  closed without passing, are not counted as failures.
- **Funded accounts**: accounts of type Funded. Converting an evaluation creates
  one linked funded account; the evaluation is counted once as an evaluation and
  the funded account once as funded. An evaluation can only be converted once.
- **Money spent**: purchase cost of every account (evaluation fees plus any
  activation fee entered for a funded account).
- **Payouts received**: only payouts with status **Paid**, using the *amount
  actually received*. Requested / Approved payouts are shown as pending and not
  counted. Rejected payouts never count.
- **Net cash flow**: payouts received − money spent.
- **Trade P&L** is shown separately as money earned on an account. It is not
  cash, and a profitable funded account is never assumed to have paid out.

Failed accounts are kept (with their trades) so the history and pass rate stay
accurate. Delete is only for records created by mistake.

## Backup and restore

**Download backup** produces a single `.zip` containing a consistent copy of the
database, all screenshots and a manifest. **Restore** checks the file (valid zip,
Rinse Tracker manifest, database integrity, required tables), saves your current
data to `data/backups/pre-restore-<time>.zip`, then swaps the backup in.

## Project structure

```
run.py                     start the app in your browser (--demo, --port, --no-browser)
desktop.py                 start the app in its own window (used by the Mac app)
scripts/build_mac.sh       build "Rinse Tracker.app" and the .dmg (runs on a Mac / GitHub Actions)
rinse_tracker/
  __init__.py              app factory, error handling
  db.py                    schema + migrations (add future changes in migrate())
  validation.py            input parsing with per-field error messages
  images.py                screenshot validation (by file contents) and storage
  accounts.py              accounts, lifecycle rules, evaluation → funded
  trades.py                trade journal + screenshots
  payouts.py               payouts
  stats.py                 dashboard / rinse statistics calculations
  backup.py                backup and restore
  coach.py                 AI coach (Anthropic API), conversations
  sample_data.py           demo seed (refuses to run outside demo mode)
  static/
    index.html, css/app.css
    js/api.js, ui.js, forms.js, app.js (router)
    js/views/              one file per section
tests/                     pytest: calculations, uploads, persistence, backup
```

Each domain is one backend module (API routes + rules) and one frontend view,
so a new feature usually means adding a module and a view without touching the
rest.

## Tests

```bash
python -m pytest -q
```

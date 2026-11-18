"""JSON API for accounts, trades, screenshots and settings."""
import json
import os
import re
import uuid
from datetime import datetime
from decimal import Decimal, InvalidOperation

from flask import Blueprint, current_app, jsonify, request, send_from_directory

from .db import get_db

bp = Blueprint("api", __name__, url_prefix="/api")

MAX_CENTS = 100_000_000_000  # $1 billion sanity cap
MAX_IMAGE_BYTES = 25 * 1024 * 1024
SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,200}$")
IMAGE_TYPES = (
    (b"\x89PNG\r\n\x1a\n", "png", "image/png"),
    (b"\xff\xd8\xff", "jpg", "image/jpeg"),
    (b"GIF87a", "gif", "image/gif"),
    (b"GIF89a", "gif", "image/gif"),
)


class ValidationError(Exception):
    def __init__(self, errors):
        self.errors = errors
        super().__init__("; ".join(errors.values()))


class NotFound(Exception):
    pass


# ---------------------------------------------------------------- input parsing

class Form:
    """Reads fields from a JSON body or form data and collects friendly errors."""

    def __init__(self, data):
        self.data = data or {}
        self.errors = {}

    def text(self, name, label, required=False, max_len=200):
        value = str(self.data.get(name) or "").strip()
        if required and not value:
            self.errors[name] = f"{label} is required."
        elif len(value) > max_len:
            self.errors[name] = f"{label} is too long."
        return value or None

    def choice(self, name, label, options, default=None):
        value = str(self.data.get(name) or default or "").strip().lower()
        if value not in options:
            self.errors[name] = f"Choose a {label.lower()}."
        return value

    def number(self, name, label, required=False, positive=False):
        raw = str(self.data.get(name) if self.data.get(name) is not None else "").strip()
        raw = raw.replace(",", "").replace("$", "").replace(" ", "")
        if not raw:
            if required:
                self.errors[name] = f"{label} is required."
            return None
        try:
            value = Decimal(raw)
            if not value.is_finite():
                raise InvalidOperation
        except InvalidOperation:
            self.errors[name] = f"{label} must be a number."
            return None
        if positive and value <= 0:
            self.errors[name] = f"{label} must be more than 0."
            return None
        return value

    def cents(self, name, label, required=False, allow_negative=False):
        value = self.number(name, label, required)
        if value is None:
            return None
        cents = int((value * 100).quantize(Decimal("1")))
        if cents < 0 and not allow_negative:
            self.errors[name] = f"{label} can't be negative."
        elif abs(cents) > MAX_CENTS:
            self.errors[name] = f"{label} is too large."
        else:
            return cents
        return None

    def datetime(self, name, label):
        raw = str(self.data.get(name) or "").strip()
        for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                return datetime.strptime(raw, fmt).strftime("%Y-%m-%dT%H:%M")
            except ValueError:
                pass
        self.errors[name] = f"{label} is required."
        return None

    def check(self):
        if self.errors:
            raise ValidationError(self.errors)


def body():
    if request.is_json:
        return request.get_json(silent=True) or {}
    return request.form.to_dict()


def as_float(d):
    return None if d is None else float(d)


# ---------------------------------------------------------------- settings

@bp.get("/settings")
def get_settings():
    rows = get_db().execute("SELECT key, value FROM settings").fetchall()
    settings = {"name": "Jordi"}
    settings.update({r["key"]: r["value"] for r in rows})
    return jsonify(settings)


@bp.put("/settings")
def put_settings():
    f = Form(body())
    name = f.text("name", "Your name", required=True, max_len=60)
    f.check()
    db = get_db()
    db.execute("INSERT INTO settings (key, value) VALUES ('name', ?) "
               "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (name,))
    db.commit()
    return get_settings()


# ---------------------------------------------------------------- daily tasks + journal

DAILY_TASKS = ("trading", "reading", "gym")


def day_json(row):
    return {"date": row["date"], "done": json.loads(row["done"] or "[]"), "journal": row["journal"] or "",
            "mood": row["mood"], "energy": row["energy"]}


def check_date(value, label="Date"):
    try:
        return datetime.strptime(str(value or ""), "%Y-%m-%d").strftime("%Y-%m-%d")
    except ValueError:
        raise ValidationError({"date": f"{label} isn't a valid date."})


def scale(value, name, label):
    if value in (None, "", 0, "0"):
        return None
    try:
        n = int(value)
    except (TypeError, ValueError):
        n = 0
    if not 1 <= n <= 5:
        raise ValidationError({name: f"{label} must be 1 to 5."})
    return n


@bp.get("/days")
def list_days():
    rows = get_db().execute("SELECT * FROM days ORDER BY date").fetchall()
    return jsonify([day_json(r) for r in rows])


@bp.put("/days/<date>")
def put_day(date):
    """Update only the fields sent (done, journal, mood, energy); an emptied day is removed."""
    try:
        datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        raise NotFound("That isn't a valid date.")
    data = body()
    db = get_db()
    row = db.execute("SELECT * FROM days WHERE date = ?", (date,)).fetchone()
    cur = day_json(row) if row else {"done": [], "journal": "", "mood": None, "energy": None}
    if "done" in data:
        done = data.get("done") or []
        if not isinstance(done, list):
            raise ValidationError({"done": "Tasks must be a list."})
        cur["done"] = [t for t in DAILY_TASKS if t in done]
    if "journal" in data:
        cur["journal"] = str(data.get("journal") or "").strip()
        if len(cur["journal"]) > 20000:
            raise ValidationError({"journal": "Journal entry is too long."})
    if "mood" in data:
        cur["mood"] = scale(data.get("mood"), "mood", "Mood")
    if "energy" in data:
        cur["energy"] = scale(data.get("energy"), "energy", "Energy")
    if not cur["done"] and not cur["journal"] and cur["mood"] is None and cur["energy"] is None:
        db.execute("DELETE FROM days WHERE date = ?", (date,))
    else:
        db.execute("INSERT INTO days (date, done, journal, mood, energy) VALUES (?, ?, ?, ?, ?) "
                   "ON CONFLICT(date) DO UPDATE SET done = excluded.done, journal = excluded.journal, "
                   "mood = excluded.mood, energy = excluded.energy, updated_at = datetime('now')",
                   (date, json.dumps(cur["done"]), cur["journal"] or None, cur["mood"], cur["energy"]))
    db.commit()
    return jsonify({"date": date, **{k: cur[k] for k in ("done", "journal", "mood", "energy")}})


# ---------------------------------------------------------------- reading

def book_json(row):
    return {"id": row["id"], "title": row["title"], "author": row["author"],
            "total_chapters": row["total_chapters"], "status": row["status"], "finished_on": row["finished_on"]}


def read_book(data):
    f = Form(data)
    total = f.number("total_chapters", "Number of chapters", positive=True)
    values = {
        "title": f.text("title", "Title", required=True, max_len=150),
        "author": f.text("author", "Author", max_len=100),
        "total_chapters": int(total) if total is not None else None,
        "status": f.choice("status", "Status", ("reading", "finished"), "reading"),
        "finished_on": None,
    }
    if values["status"] == "finished":
        raw = data.get("finished_on") or datetime.now().strftime("%Y-%m-%d")
        try:
            values["finished_on"] = check_date(raw, "Finished date")
        except ValidationError as err:
            f.errors["finished_on"] = err.errors["date"]
    f.check()
    return values


def load_book(book_id):
    row = get_db().execute("SELECT * FROM books WHERE id = ?", (book_id,)).fetchone()
    if row is None:
        raise NotFound("That book no longer exists.")
    return row


@bp.get("/books")
def list_books():
    rows = get_db().execute("SELECT * FROM books ORDER BY created_at, id").fetchall()
    return jsonify([book_json(r) for r in rows])


@bp.post("/books")
def create_book():
    v = read_book(body())
    db = get_db()
    cur = db.execute("INSERT INTO books (title, author, total_chapters, status, finished_on) "
                     "VALUES (:title, :author, :total_chapters, :status, :finished_on)", v)
    db.commit()
    return jsonify(book_json(load_book(cur.lastrowid))), 201


@bp.put("/books/<int:book_id>")
def update_book(book_id):
    load_book(book_id)
    v = read_book(body())
    db = get_db()
    db.execute("UPDATE books SET title = :title, author = :author, total_chapters = :total_chapters, "
               "status = :status, finished_on = :finished_on WHERE id = :id", {**v, "id": book_id})
    db.commit()
    return jsonify(book_json(load_book(book_id)))


@bp.delete("/books/<int:book_id>")
def delete_book(book_id):
    load_book(book_id)
    db = get_db()
    db.execute("DELETE FROM books WHERE id = ?", (book_id,))
    db.commit()
    return jsonify({"deleted": True})


def chapter_json(row):
    return {"date": row["date"], "book_id": row["book_id"], "chapter": row["chapter"], "learned": row["learned"] or ""}


@bp.get("/chapters")
def list_chapters():
    rows = get_db().execute("SELECT * FROM chapters ORDER BY date").fetchall()
    return jsonify([chapter_json(r) for r in rows])


@bp.put("/chapters/<date>")
def put_chapter(date):
    """Save the chapter read on a day and what was learned from it; empty notes remove it."""
    date = check_date(date)
    f = Form(body())
    book_id = f.number("book_id", "Book", required=True)
    chapter = f.number("chapter", "Chapter", positive=True)
    learned = f.text("learned", "What you learned", max_len=20000)
    f.check()
    db = get_db()
    load_book(int(book_id))
    if not learned and chapter is None:
        db.execute("DELETE FROM chapters WHERE date = ?", (date,))
        db.commit()
        return jsonify({"date": date, "deleted": True})
    db.execute("INSERT INTO chapters (date, book_id, chapter, learned) VALUES (?, ?, ?, ?) "
               "ON CONFLICT(date) DO UPDATE SET book_id = excluded.book_id, chapter = excluded.chapter, "
               "learned = excluded.learned, updated_at = datetime('now')",
               (date, int(book_id), int(chapter) if chapter is not None else None, learned))
    db.commit()
    return jsonify(chapter_json(db.execute("SELECT * FROM chapters WHERE date = ?", (date,)).fetchone()))


# ---------------------------------------------------------------- wins

def win_json(row):
    return {"id": row["id"], "date": row["date"], "title": row["title"], "category": row["category"],
            "note": row["note"] or "", "photo": f"/api/screenshots/{row['photo']}" if row["photo"] else None}


def read_win(data):
    f = Form(data)
    values = {
        "title": f.text("title", "Title", required=True, max_len=120),
        "category": f.choice("category", "Category", ("trading", "fitness", "reading", "personal"), "personal"),
        "note": f.text("note", "Note", max_len=5000),
    }
    try:
        values["date"] = check_date(data.get("date"))
    except ValidationError as err:
        f.errors["date"] = err.errors["date"]
    f.check()
    return values


def load_win(win_id):
    row = get_db().execute("SELECT * FROM wins WHERE id = ?", (win_id,)).fetchone()
    if row is None:
        raise NotFound("That win no longer exists.")
    return row


@bp.get("/wins")
def list_wins():
    rows = get_db().execute("SELECT * FROM wins ORDER BY date DESC, id DESC").fetchall()
    return jsonify([win_json(r) for r in rows])


def _win_photo():
    images = read_uploads(request.files.getlist("photo"))[:1]
    return save_files(images)


@bp.post("/wins")
def create_win():
    v = read_win(body())
    saved = _win_photo()
    db = get_db()
    try:
        cur = db.execute("INSERT INTO wins (date, title, category, note, photo) VALUES (?, ?, ?, ?, ?)",
                         (v["date"], v["title"], v["category"], v["note"], saved[0]["filename"] if saved else None))
        db.commit()
    except Exception:
        db.rollback()
        delete_files([s["filename"] for s in saved])
        raise
    return jsonify(win_json(load_win(cur.lastrowid))), 201


@bp.put("/wins/<int:win_id>")
def update_win(win_id):
    old = load_win(win_id)
    data = body()
    v = read_win(data)
    saved = _win_photo()
    photo = old["photo"]
    if saved or data.get("remove_photo") in ("1", "true", True):
        photo = saved[0]["filename"] if saved else None
    db = get_db()
    try:
        db.execute("UPDATE wins SET date = ?, title = ?, category = ?, note = ?, photo = ? WHERE id = ?",
                   (v["date"], v["title"], v["category"], v["note"], photo, win_id))
        db.commit()
    except Exception:
        db.rollback()
        delete_files([s["filename"] for s in saved])
        raise
    if old["photo"] and old["photo"] != photo:
        delete_files([old["photo"]])
    return jsonify(win_json(load_win(win_id)))


@bp.delete("/wins/<int:win_id>")
def delete_win(win_id):
    old = load_win(win_id)
    db = get_db()
    db.execute("DELETE FROM wins WHERE id = ?", (win_id,))
    db.commit()
    if old["photo"]:
        delete_files([old["photo"]])
    return jsonify({"deleted": True})


# ---------------------------------------------------------------- accounts

def account_json(row):
    return {
        "id": row["id"], "name": row["name"], "firm": row["firm"], "type": row["type"],
        "status": row["status"], "notes": row["notes"],
        "start_balance": row["start_balance_cents"] / 100,
        "profit_target": None if row["profit_target_cents"] is None else row["profit_target_cents"] / 100,
        "max_drawdown": None if row["max_drawdown_cents"] is None else row["max_drawdown_cents"] / 100,
        "created_at": row["created_at"],
    }


def read_account(data):
    f = Form(data)
    values = {
        "name": f.text("name", "Name", required=True, max_len=80),
        "firm": f.text("firm", "Firm", max_len=80),
        "type": f.choice("type", "Account type", ("evaluation", "funded", "personal"), "funded"),
        "status": f.choice("status", "Status", ("active", "passed", "breached", "closed"), "active"),
        "start_balance_cents": f.cents("start_balance", "Starting balance", required=True),
        "profit_target_cents": f.cents("profit_target", "Profit target"),
        "max_drawdown_cents": f.cents("max_drawdown", "Max drawdown"),
        "notes": f.text("notes", "Notes", max_len=4000),
    }
    f.check()
    return values


def load_account(account_id):
    row = get_db().execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
    if row is None:
        raise NotFound("That account no longer exists.")
    return row


@bp.get("/accounts")
def list_accounts():
    rows = get_db().execute("SELECT * FROM accounts ORDER BY created_at, id").fetchall()
    return jsonify([account_json(r) for r in rows])


@bp.post("/accounts")
def create_account():
    v = read_account(body())
    db = get_db()
    cur = db.execute(
        "INSERT INTO accounts (name, firm, type, status, start_balance_cents, profit_target_cents, "
        "max_drawdown_cents, notes) VALUES (:name, :firm, :type, :status, :start_balance_cents, "
        ":profit_target_cents, :max_drawdown_cents, :notes)", v)
    db.commit()
    return jsonify(account_json(load_account(cur.lastrowid))), 201


@bp.put("/accounts/<int:account_id>")
def update_account(account_id):
    load_account(account_id)
    v = read_account(body())
    db = get_db()
    db.execute(
        "UPDATE accounts SET name = :name, firm = :firm, type = :type, status = :status, "
        "start_balance_cents = :start_balance_cents, profit_target_cents = :profit_target_cents, "
        "max_drawdown_cents = :max_drawdown_cents, notes = :notes, updated_at = datetime('now') "
        "WHERE id = :id", {**v, "id": account_id})
    db.commit()
    return jsonify(account_json(load_account(account_id)))


@bp.delete("/accounts/<int:account_id>")
def delete_account(account_id):
    load_account(account_id)
    db = get_db()
    files = [r["filename"] for r in db.execute(
        "SELECT s.filename FROM screenshots s JOIN trades t ON t.id = s.trade_id WHERE t.account_id = ?",
        (account_id,))]
    db.execute("DELETE FROM accounts WHERE id = ?", (account_id,))
    db.commit()
    delete_files(files)
    return jsonify({"deleted": True})


# ---------------------------------------------------------------- trades

def trade_json(row, shots):
    return {
        "id": row["id"], "account_id": row["account_id"], "traded_at": row["traded_at"],
        "symbol": row["symbol"], "side": row["side"], "contracts": row["contracts"],
        "setup": row["setup"], "entry": row["entry"], "stop": row["stop"], "exit": row["exit"],
        "pnl": row["pnl_cents"] / 100, "notes": row["notes"],
        "tags": json.loads(row["tags"]) if row["tags"] else [],
        "screenshots": [{"id": s["id"], "url": f"/api/screenshots/{s['filename']}",
                         "name": s["original_name"]} for s in shots],
    }


def read_trade(data):
    f = Form(data)
    tags = data.get("tags") or ""
    if isinstance(tags, str):
        tags = [t.strip().lstrip("#") for t in tags.split(",")]
    tags = [str(t).strip()[:40] for t in tags if str(t).strip()][:20]
    account_id = f.number("account_id", "Account", required=True)
    values = {
        "account_id": int(account_id) if account_id is not None else None,
        "traded_at": f.datetime("traded_at", "Date and time"),
        "symbol": (f.text("symbol", "Symbol", required=True, max_len=20) or "").upper(),
        "side": f.choice("side", "Side", ("long", "short")),
        "contracts": as_float(f.number("contracts", "Contracts", positive=True)),
        "setup": f.text("setup", "Setup", max_len=80),
        "entry": as_float(f.number("entry", "Entry")),
        "stop": as_float(f.number("stop", "Stop")),
        "exit": as_float(f.number("exit", "Exit")),
        "pnl_cents": f.cents("pnl", "P&L", required=True, allow_negative=True),
        "notes": f.text("notes", "Notes", max_len=10000),
        "tags": json.dumps(tags) if tags else None,
    }
    if values["account_id"] is not None and get_db().execute(
            "SELECT 1 FROM accounts WHERE id = ?", (values["account_id"],)).fetchone() is None:
        f.errors["account_id"] = "Choose an account."
    f.check()
    return values


def load_trade(trade_id):
    db = get_db()
    row = db.execute("SELECT * FROM trades WHERE id = ?", (trade_id,)).fetchone()
    if row is None:
        raise NotFound("That trade no longer exists.")
    shots = db.execute("SELECT * FROM screenshots WHERE trade_id = ? ORDER BY id", (trade_id,)).fetchall()
    return trade_json(row, shots)


@bp.get("/trades")
def list_trades():
    db = get_db()
    shots = {}
    for s in db.execute("SELECT * FROM screenshots ORDER BY id"):
        shots.setdefault(s["trade_id"], []).append(s)
    rows = db.execute("SELECT * FROM trades ORDER BY traded_at DESC, id DESC").fetchall()
    return jsonify([trade_json(r, shots.get(r["id"], [])) for r in rows])


@bp.post("/trades")
def create_trade():
    v = read_trade(body())
    images = read_uploads(request.files.getlist("screenshots"))
    saved = save_files(images)
    db = get_db()
    try:
        cur = db.execute(
            "INSERT INTO trades (account_id, traded_at, symbol, side, contracts, setup, entry, stop, exit, "
            "pnl_cents, notes, tags) VALUES (:account_id, :traded_at, :symbol, :side, :contracts, :setup, "
            ":entry, :stop, :exit, :pnl_cents, :notes, :tags)", v)
        add_screenshots(db, cur.lastrowid, saved)
        db.commit()
    except Exception:
        db.rollback()
        delete_files([s["filename"] for s in saved])
        raise
    return jsonify(load_trade(cur.lastrowid)), 201


@bp.put("/trades/<int:trade_id>")
def update_trade(trade_id):
    load_trade(trade_id)
    data = body()
    v = read_trade(data)
    images = read_uploads(request.files.getlist("screenshots"))
    remove = [int(x) for x in str(data.get("remove_screenshots") or "").split(",") if x.strip().isdigit()]
    saved = save_files(images)
    db = get_db()
    try:
        db.execute(
            "UPDATE trades SET account_id = :account_id, traded_at = :traded_at, symbol = :symbol, "
            "side = :side, contracts = :contracts, setup = :setup, entry = :entry, stop = :stop, "
            "exit = :exit, pnl_cents = :pnl_cents, notes = :notes, tags = :tags, "
            "updated_at = datetime('now') WHERE id = :id", {**v, "id": trade_id})
        gone = []
        if remove:
            marks = ",".join("?" * len(remove))
            gone = [r["filename"] for r in db.execute(
                f"SELECT filename FROM screenshots WHERE trade_id = ? AND id IN ({marks})", (trade_id, *remove))]
            db.execute(f"DELETE FROM screenshots WHERE trade_id = ? AND id IN ({marks})", (trade_id, *remove))
        add_screenshots(db, trade_id, saved)
        db.commit()
    except Exception:
        db.rollback()
        delete_files([s["filename"] for s in saved])
        raise
    delete_files(gone)
    return jsonify(load_trade(trade_id))


@bp.delete("/trades/<int:trade_id>")
def delete_trade(trade_id):
    load_trade(trade_id)
    db = get_db()
    files = [r["filename"] for r in db.execute("SELECT filename FROM screenshots WHERE trade_id = ?", (trade_id,))]
    db.execute("DELETE FROM trades WHERE id = ?", (trade_id,))
    db.commit()
    delete_files(files)
    return jsonify({"deleted": True})


# ---------------------------------------------------------------- screenshots

def read_uploads(files):
    """Check every file before saving any, so a bad file saves nothing."""
    images = []
    for f in files:
        if not f or not f.filename:
            continue
        data = f.read(MAX_IMAGE_BYTES + 1)
        name = os.path.basename(f.filename)[:200]
        if len(data) > MAX_IMAGE_BYTES:
            raise ValidationError({"screenshots": f"'{name}' is larger than 25 MB."})
        kind = next(((ext, mime) for magic, ext, mime in IMAGE_TYPES if data.startswith(magic)), None)
        if kind is None and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
            kind = ("webp", "image/webp")
        if kind is None:
            raise ValidationError({"screenshots": f"'{name}' isn't a PNG, JPG, GIF or WEBP image."})
        images.append({"data": data, "name": name, "ext": kind[0], "mime": kind[1]})
    return images


def save_files(images):
    folder = current_app.config["UPLOAD_DIR"]
    saved = []
    try:
        for img in images:
            filename = f"{uuid.uuid4().hex}.{img['ext']}"
            with open(os.path.join(folder, filename), "wb") as fh:
                fh.write(img["data"])
            saved.append({"filename": filename, "name": img["name"], "mime": img["mime"]})
    except OSError:
        delete_files([s["filename"] for s in saved])
        raise
    return saved


def add_screenshots(db, trade_id, saved):
    for s in saved:
        db.execute("INSERT INTO screenshots (trade_id, filename, original_name, content_type) VALUES (?, ?, ?, ?)",
                   (trade_id, s["filename"], s["name"], s["mime"]))


def delete_files(names):
    folder = current_app.config["UPLOAD_DIR"]
    for name in names:
        if SAFE_NAME.match(name or ""):
            try:
                os.remove(os.path.join(folder, name))
            except FileNotFoundError:
                pass


@bp.get("/screenshots/<name>")
def screenshot(name):
    if not SAFE_NAME.match(name):
        raise NotFound("Screenshot not found.")
    return send_from_directory(current_app.config["UPLOAD_DIR"], name, max_age=31536000)

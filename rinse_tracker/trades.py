"""Trade journal entries with any number of screenshots."""
from flask import Blueprint, current_app, jsonify, request, send_from_directory

from . import images
from .db import get_db
from .validation import Form, NotFound, ValidationError, from_cents

bp = Blueprint("trades", __name__)

RESULTS = ("win", "loss", "breakeven")

TRADE_SQL = """
SELECT t.*, a.firm, a.account_ref, a.size_cents, a.type AS account_type
FROM trades t JOIN accounts a ON a.id = t.account_id
"""


def _screenshots(conn, trade_ids):
    by_trade = {tid: [] for tid in trade_ids}
    if not trade_ids:
        return by_trade
    marks = ",".join("?" * len(trade_ids))
    rows = conn.execute(f"SELECT * FROM screenshots WHERE trade_id IN ({marks}) ORDER BY id",
                        list(trade_ids))
    for r in rows:
        by_trade[r["trade_id"]].append({
            "id": r["id"], "url": f"/uploads/{r['filename']}",
            "original_name": r["original_name"], "size_bytes": r["size_bytes"],
        })
    return by_trade


def serialize_many(conn, rows):
    rows = [dict(r) for r in rows]
    shots = _screenshots(conn, [r["id"] for r in rows])
    for r in rows:
        r["pnl"] = from_cents(r.pop("pnl_cents"))
        r["account_size"] = from_cents(r.pop("size_cents"))
        r["screenshots"] = shots[r["id"]]
    return rows


def get_trade(conn, trade_id):
    row = conn.execute(TRADE_SQL + " WHERE t.id = ?", (trade_id,)).fetchone()
    if row is None:
        raise NotFound("Trade not found.")
    return serialize_many(conn, [row])[0]


def _read_fields(conn, form, existing=None):
    def pick(field, key, reader):
        if existing is not None and not form.has(field):
            return existing[key]
        return reader()

    account_id = pick("account_id", "account_id",
                      lambda: form.integer("account_id", required=True, label="Account"))
    if account_id is not None and not conn.execute("SELECT 1 FROM accounts WHERE id = ?",
                                                   (account_id,)).fetchone():
        form.error("account_id", "Choose an existing account.")
    return dict(
        account_id=account_id,
        traded_at=pick("traded_at", "traded_at",
                       lambda: form.datetime("traded_at", required=True, label="Date and time")),
        instrument=pick("instrument", "instrument",
                        lambda: (form.text("instrument", max_len=50) or "").upper() or None),
        result=pick("result", "result",
                    lambda: form.choice("result", RESULTS, required=True, label="Result")),
        pnl_cents=pick("pnl", "pnl_cents", lambda: form.money("pnl", allow_negative=True)),
        summary=pick("summary", "summary", lambda: form.text("summary")),
        notes=pick("notes", "notes", lambda: form.text("notes")),
    )


def _incoming(req):
    """Accept either multipart (with screenshots) or a JSON body."""
    if req.mimetype == "multipart/form-data":
        return req.form.to_dict(), req.files.getlist("screenshots")
    return (req.get_json(silent=True) or {}), []


def _insert_screenshots(conn, trade_id, saved):
    for s in saved:
        conn.execute("INSERT INTO screenshots (trade_id, filename, original_name, content_type, "
                     "size_bytes) VALUES (?, ?, ?, ?, ?)",
                     (trade_id, s["filename"], s["original_name"], s["content_type"],
                      s["size_bytes"]))


def create_trade(conn, data, files, upload_dir):
    form = Form(data)
    fields = _read_fields(conn, form)
    form.check()
    pending = images.read_uploads(files)
    saved = images.save_files(upload_dir, pending)
    try:
        cur = conn.execute(
            """INSERT INTO trades (account_id, traded_at, instrument, result, pnl_cents,
                                   summary, notes)
               VALUES (:account_id, :traded_at, :instrument, :result, :pnl_cents,
                       :summary, :notes)""", fields)
        _insert_screenshots(conn, cur.lastrowid, saved)
        conn.commit()
    except Exception:
        conn.rollback()
        images.delete_files(upload_dir, [s["filename"] for s in saved])
        raise
    return cur.lastrowid


def update_trade(conn, trade_id, data, files, upload_dir):
    existing = conn.execute("SELECT * FROM trades WHERE id = ?", (trade_id,)).fetchone()
    if existing is None:
        raise NotFound("Trade not found.")
    form = Form(data)
    fields = _read_fields(conn, form, existing)
    remove_ids = []
    for part in str(data.get("remove_screenshots") or "").split(","):
        if part.strip():
            try:
                remove_ids.append(int(part))
            except ValueError:
                form.error("remove_screenshots", "Invalid screenshot id.")
    form.check()

    pending = images.read_uploads(files)
    saved = images.save_files(upload_dir, pending)
    removed_files = []
    try:
        conn.execute(
            """UPDATE trades SET account_id=:account_id, traded_at=:traded_at,
                   instrument=:instrument, result=:result, pnl_cents=:pnl_cents,
                   summary=:summary, notes=:notes, updated_at=datetime('now')
               WHERE id=:id""", {**fields, "id": trade_id})
        for sid in remove_ids:
            row = conn.execute("SELECT filename FROM screenshots WHERE id = ? AND trade_id = ?",
                               (sid, trade_id)).fetchone()
            if row:
                removed_files.append(row["filename"])
                conn.execute("DELETE FROM screenshots WHERE id = ?", (sid,))
        _insert_screenshots(conn, trade_id, saved)
        conn.commit()
    except Exception:
        conn.rollback()
        images.delete_files(upload_dir, [s["filename"] for s in saved])
        raise
    # Only remove files once the database no longer references them.
    images.delete_files(upload_dir, removed_files)


def delete_trade(conn, trade_id, upload_dir):
    if not conn.execute("SELECT 1 FROM trades WHERE id = ?", (trade_id,)).fetchone():
        raise NotFound("Trade not found.")
    files = [r["filename"] for r in conn.execute(
        "SELECT filename FROM screenshots WHERE trade_id = ?", (trade_id,))]
    conn.execute("DELETE FROM trades WHERE id = ?", (trade_id,))
    conn.commit()
    images.delete_files(upload_dir, files)


# ---------------------------------------------------------------- routes

@bp.get("/api/trades")
def list_trades():
    conn = get_db()
    where, params = [], []
    account_id = request.args.get("account_id", "").strip()
    result = request.args.get("result", "").strip().lower()
    q = request.args.get("q", "").strip()
    if account_id:
        try:
            params.append(int(account_id))
        except ValueError:
            raise ValidationError({"account_id": "Invalid account."})
        where.append("t.account_id = ?")
    if result in RESULTS:
        where.append("t.result = ?")
        params.append(result)
    if q:
        where.append("(t.instrument LIKE ? OR t.summary LIKE ? OR t.notes LIKE ? OR a.firm LIKE ?)")
        params += [f"%{q}%"] * 4
    sql = TRADE_SQL + (" WHERE " + " AND ".join(where) if where else "")
    sql += " ORDER BY t.traded_at DESC, t.id DESC"
    try:
        limit = max(1, min(int(request.args.get("limit", 500)), 5000))
    except ValueError:
        limit = 500
    sql += f" LIMIT {limit}"
    return jsonify(serialize_many(conn, conn.execute(sql, params).fetchall()))


@bp.get("/api/instruments")
def list_instruments():
    rows = get_db().execute(
        "SELECT instrument FROM trades WHERE instrument IS NOT NULL "
        "GROUP BY instrument ORDER BY MAX(traded_at) DESC LIMIT 50")
    return jsonify([r["instrument"] for r in rows])


@bp.post("/api/trades")
def post_trade():
    conn = get_db()
    data, files = _incoming(request)
    trade_id = create_trade(conn, data, files, current_app.config["UPLOAD_DIR"])
    return jsonify(get_trade(conn, trade_id)), 201


@bp.get("/api/trades/<int:trade_id>")
def get_trade_detail(trade_id):
    return jsonify(get_trade(get_db(), trade_id))


@bp.put("/api/trades/<int:trade_id>")
def put_trade(trade_id):
    conn = get_db()
    data, files = _incoming(request)
    update_trade(conn, trade_id, data, files, current_app.config["UPLOAD_DIR"])
    return jsonify(get_trade(conn, trade_id))


@bp.delete("/api/trades/<int:trade_id>")
def remove_trade(trade_id):
    delete_trade(get_db(), trade_id, current_app.config["UPLOAD_DIR"])
    return jsonify({"ok": True})


@bp.delete("/api/screenshots/<int:shot_id>")
def remove_screenshot(shot_id):
    conn = get_db()
    row = conn.execute("SELECT filename FROM screenshots WHERE id = ?", (shot_id,)).fetchone()
    if row is None:
        raise NotFound("Screenshot not found.")
    conn.execute("DELETE FROM screenshots WHERE id = ?", (shot_id,))
    conn.commit()
    images.delete_files(current_app.config["UPLOAD_DIR"], [row["filename"]])
    return jsonify({"ok": True})


@bp.get("/uploads/<path:filename>")
def serve_upload(filename):
    if not images.SAFE_NAME.match(filename):
        raise NotFound("File not found.")
    return send_from_directory(current_app.config["UPLOAD_DIR"], filename, max_age=86400)

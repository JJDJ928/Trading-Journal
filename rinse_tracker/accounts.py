"""Prop-firm accounts: evaluations, funded accounts and their lifecycle.

Lifecycle rules (enforced here, not just in the UI):
  * An evaluation moves between active / passed / failed / closed.
  * A passed evaluation is converted with POST /api/accounts/<id>/fund, which
    creates ONE linked funded account (parent_id) and marks the evaluation
    'funded'. The evaluation is still counted once as an evaluation, and the
    funded account once as a funded account, so nothing is double counted.
  * Funded accounts move between funded / failed / closed.
  * Failed accounts are never removed automatically; history is kept.
"""
from flask import Blueprint, current_app, jsonify, request

from . import images
from .db import get_db
from .validation import Form, NotFound, ValidationError, from_cents, today

bp = Blueprint("accounts", __name__)

TYPES = ("evaluation", "funded")
STATUSES = ("active", "passed", "funded", "failed", "closed")
STATUSES_BY_TYPE = {
    "evaluation": ("active", "passed", "funded", "failed", "closed"),
    "funded": ("funded", "failed", "closed"),
}
ENDED = ("failed", "closed")


def serialize(row):
    data = dict(row)
    data["size"] = from_cents(data.pop("size_cents"))
    data["cost"] = from_cents(data.pop("cost_cents"))
    for key in ("pnl_cents", "payouts_received_cents"):
        if key in data:
            data[key.replace("_cents", "")] = from_cents(data.pop(key) or 0)
    return data


LIST_SQL = """
SELECT a.*,
       (SELECT c.id FROM accounts c WHERE c.parent_id = a.id) AS child_id,
       (SELECT COUNT(*) FROM trades t WHERE t.account_id = a.id) AS trade_count,
       (SELECT COALESCE(SUM(t.pnl_cents), 0) FROM trades t WHERE t.account_id = a.id) AS pnl_cents,
       (SELECT COALESCE(SUM(p.received_cents), 0) FROM payouts p
         WHERE p.account_id = a.id AND p.status = 'paid') AS payouts_received_cents
FROM accounts a
"""


def get_account(conn, account_id):
    row = conn.execute(LIST_SQL + " WHERE a.id = ?", (account_id,)).fetchone()
    if row is None:
        raise NotFound("Account not found.")
    return row


def _apply_lifecycle(form, acct_type, status, pass_date, end_date, purchase_date, has_child):
    """Validate the status for the type and fill in or clear the related dates."""
    if acct_type and status and status not in STATUSES_BY_TYPE[acct_type]:
        allowed = ", ".join(STATUSES_BY_TYPE[acct_type])
        form.error("status", f"A {acct_type} account can only be: {allowed}.")
        return pass_date, end_date

    if acct_type == "evaluation":
        if status == "funded" and not has_child:
            form.error("status", "Use 'Create funded account' on a passed evaluation to mark it funded.")
        if has_child and status != "funded":
            form.error("status", "This evaluation already became a funded account. "
                                 "Track further status changes on the funded account.")
        if status in ("passed", "funded"):
            pass_date = pass_date or today()
        elif status in ("active", "failed"):
            pass_date = None  # never passed; keeps the pass rate honest
        # 'closed' keeps whatever pass date it had (e.g. passed, then never activated)
    else:
        pass_date = None

    if status in ENDED:
        end_date = end_date or today()
    else:
        end_date = None

    for field, value in (("pass_date", pass_date), ("end_date", end_date)):
        if value and purchase_date and value < purchase_date:
            form.error(field, "Cannot be before the purchase date.")
    return pass_date, end_date


def _read_fields(form, existing=None):
    """Read account fields. On update, missing fields keep their existing value."""
    def pick(field, key, reader):
        if existing is not None and not form.has(field):
            return existing[key]
        return reader()

    firm = pick("firm", "firm", lambda: form.text("firm", required=True, max_len=100,
                                                  label="Prop firm"))
    account_ref = pick("account_ref", "account_ref", lambda: form.text("account_ref", max_len=100))
    size_cents = pick("size", "size_cents", lambda: form.money("size", required=True,
                                                               label="Account size"))
    acct_type = pick("type", "type", lambda: form.choice("type", TYPES, required=True,
                                                         label="Account type"))
    cost_cents = pick("cost", "cost_cents", lambda: form.money("cost", label="Cost"))
    purchase_date = pick("purchase_date", "purchase_date",
                         lambda: form.date("purchase_date", required=True, label="Purchase date"))
    default_status = "active" if acct_type == "evaluation" else "funded"
    status = pick("status", "status", lambda: form.choice("status", STATUSES)) or default_status
    pass_date = pick("pass_date", "pass_date", lambda: form.date("pass_date"))
    end_date = pick("end_date", "end_date", lambda: form.date("end_date"))
    notes = pick("notes", "notes", lambda: form.text("notes"))

    if size_cents is not None and size_cents <= 0:
        form.error("size", "Account size must be greater than zero.")

    return dict(firm=firm, account_ref=account_ref, size_cents=size_cents, type=acct_type,
                cost_cents=cost_cents or 0, purchase_date=purchase_date, status=status,
                pass_date=pass_date, end_date=end_date, notes=notes)


def _record_status(conn, account_id, from_status, to_status):
    conn.execute("INSERT INTO account_status_history (account_id, from_status, to_status) "
                 "VALUES (?, ?, ?)", (account_id, from_status, to_status))


def create_account(conn, data):
    form = Form(data)
    fields = _read_fields(form)
    fields["pass_date"], fields["end_date"] = _apply_lifecycle(
        form, fields["type"], fields["status"], fields["pass_date"], fields["end_date"],
        fields["purchase_date"], has_child=False)
    form.check()
    cur = conn.execute(
        """INSERT INTO accounts (firm, account_ref, size_cents, type, cost_cents, purchase_date,
                                 status, pass_date, end_date, notes)
           VALUES (:firm, :account_ref, :size_cents, :type, :cost_cents, :purchase_date,
                   :status, :pass_date, :end_date, :notes)""", fields)
    _record_status(conn, cur.lastrowid, None, fields["status"])
    conn.commit()
    return cur.lastrowid


def update_account(conn, account_id, data):
    existing = get_account(conn, account_id)
    form = Form(data)
    fields = _read_fields(form, existing)

    has_child = existing["child_id"] is not None
    if fields["type"] != existing["type"]:
        has_payouts = conn.execute("SELECT 1 FROM payouts WHERE account_id = ?",
                                   (account_id,)).fetchone()
        if has_child or existing["parent_id"] or has_payouts:
            form.error("type", "Type can't change on an account that is linked or has payouts.")
        elif "status" not in data:
            fields["status"] = "active" if fields["type"] == "evaluation" else "funded"

    fields["pass_date"], fields["end_date"] = _apply_lifecycle(
        form, fields["type"], fields["status"], fields["pass_date"], fields["end_date"],
        fields["purchase_date"], has_child)
    form.check()

    conn.execute(
        """UPDATE accounts SET firm=:firm, account_ref=:account_ref, size_cents=:size_cents,
               type=:type, cost_cents=:cost_cents, purchase_date=:purchase_date, status=:status,
               pass_date=:pass_date, end_date=:end_date, notes=:notes,
               updated_at=datetime('now')
           WHERE id=:id""", {**fields, "id": account_id})
    if fields["status"] != existing["status"]:
        _record_status(conn, account_id, existing["status"], fields["status"])
    conn.commit()


def convert_to_funded(conn, eval_id, data):
    """Create the funded account for a passed evaluation (exactly once)."""
    evaluation = get_account(conn, eval_id)
    if evaluation["type"] != "evaluation":
        raise ValidationError("Only evaluations can be converted to a funded account.")
    if evaluation["child_id"] is not None:
        raise ValidationError("This evaluation already has a funded account.")
    if evaluation["status"] != "passed":
        raise ValidationError("Mark the evaluation as Passed before creating its funded account.")

    form = Form(data)
    pass_date = evaluation["pass_date"] or today()
    start = form.date("purchase_date") or pass_date
    cost = form.money("cost", label="Activation fee") or 0
    account_ref = form.text("account_ref", max_len=100)
    notes = form.text("notes")
    if start < evaluation["purchase_date"]:
        form.error("purchase_date", "Cannot be before the evaluation's purchase date.")
    form.check()

    cur = conn.execute(
        """INSERT INTO accounts (firm, account_ref, size_cents, type, cost_cents, purchase_date,
                                 status, parent_id, notes)
           VALUES (?, ?, ?, 'funded', ?, ?, 'funded', ?, ?)""",
        (evaluation["firm"], account_ref or evaluation["account_ref"], evaluation["size_cents"],
         cost, start, eval_id, notes))
    funded_id = cur.lastrowid
    _record_status(conn, funded_id, None, "funded")
    conn.execute("UPDATE accounts SET status='funded', pass_date=?, updated_at=datetime('now') "
                 "WHERE id=?", (pass_date, eval_id))
    _record_status(conn, eval_id, "passed", "funded")
    conn.commit()
    return funded_id


def delete_account(conn, account_id):
    """Permanently delete an account (for mistakes). Failed accounts should be kept instead."""
    account = get_account(conn, account_id)
    if account["child_id"] is not None:
        raise ValidationError("Delete the linked funded account first.")
    files = [r["filename"] for r in conn.execute(
        "SELECT s.filename FROM screenshots s JOIN trades t ON t.id = s.trade_id "
        "WHERE t.account_id = ?", (account_id,))]
    conn.execute("DELETE FROM accounts WHERE id = ?", (account_id,))
    if account["parent_id"] is not None:
        # The evaluation goes back to plain 'passed' so it can be converted again.
        conn.execute("UPDATE accounts SET status='passed', updated_at=datetime('now') "
                     "WHERE id=?", (account["parent_id"],))
        _record_status(conn, account["parent_id"], "funded", "passed")
    conn.commit()
    images.delete_files(current_app.config["UPLOAD_DIR"], files)


# ---------------------------------------------------------------- routes

@bp.get("/api/accounts")
def list_accounts():
    conn = get_db()
    where, params = [], []
    status = request.args.get("status", "").strip().lower()
    acct_type = request.args.get("type", "").strip().lower()
    q = request.args.get("q", "").strip()
    if status in STATUSES:
        where.append("a.status = ?")
        params.append(status)
    if acct_type in TYPES:
        where.append("a.type = ?")
        params.append(acct_type)
    if q:
        where.append("(a.firm LIKE ? OR a.account_ref LIKE ? OR a.notes LIKE ?)")
        params += [f"%{q}%"] * 3
    sql = LIST_SQL + (" WHERE " + " AND ".join(where) if where else "")
    sql += " ORDER BY a.purchase_date DESC, a.id DESC"
    return jsonify([serialize(r) for r in conn.execute(sql, params)])


@bp.post("/api/accounts")
def post_account():
    conn = get_db()
    new_id = create_account(conn, request.get_json(silent=True))
    return jsonify(serialize(get_account(conn, new_id))), 201


@bp.get("/api/accounts/<int:account_id>")
def get_account_detail(account_id):
    conn = get_db()
    data = serialize(get_account(conn, account_id))
    data["history"] = [dict(r) for r in conn.execute(
        "SELECT from_status, to_status, changed_at FROM account_status_history "
        "WHERE account_id = ? ORDER BY id", (account_id,))]
    for key in ("parent_id", "child_id"):
        linked = data.get(key)
        data[key.replace("_id", "")] = serialize(get_account(conn, linked)) if linked else None
    data["delete_impact"] = {
        "trades": data["trade_count"],
        "payouts": conn.execute("SELECT COUNT(*) FROM payouts WHERE account_id = ?",
                                (account_id,)).fetchone()[0],
    }
    return jsonify(data)


@bp.put("/api/accounts/<int:account_id>")
def put_account(account_id):
    conn = get_db()
    update_account(conn, account_id, request.get_json(silent=True))
    return jsonify(serialize(get_account(conn, account_id)))


@bp.post("/api/accounts/<int:account_id>/fund")
def post_fund(account_id):
    conn = get_db()
    funded_id = convert_to_funded(conn, account_id, request.get_json(silent=True))
    return jsonify(serialize(get_account(conn, funded_id))), 201


@bp.delete("/api/accounts/<int:account_id>")
def remove_account(account_id):
    delete_account(get_db(), account_id)
    return jsonify({"ok": True})

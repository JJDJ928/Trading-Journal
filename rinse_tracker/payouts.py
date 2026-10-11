"""Payouts from funded accounts. Only status 'paid' counts as money received."""
from flask import Blueprint, jsonify, request

from .db import get_db
from .validation import Form, NotFound, ValidationError, from_cents, today

bp = Blueprint("payouts", __name__)

STATUSES = ("requested", "approved", "rejected", "paid")

PAYOUT_SQL = """
SELECT p.*, a.firm, a.account_ref, a.size_cents
FROM payouts p JOIN accounts a ON a.id = p.account_id
"""


def serialize(row):
    data = dict(row)
    data["amount_requested"] = from_cents(data.pop("requested_cents"))
    data["amount_received"] = from_cents(data.pop("received_cents"))
    data["account_size"] = from_cents(data.pop("size_cents"))
    return data


def get_payout(conn, payout_id):
    row = conn.execute(PAYOUT_SQL + " WHERE p.id = ?", (payout_id,)).fetchone()
    if row is None:
        raise NotFound("Payout not found.")
    return row


def _read_fields(conn, data, existing=None):
    form = Form(data)

    def pick(field, key, reader):
        if existing is not None and not form.has(field):
            return existing[key]
        return reader()

    account_id = pick("account_id", "account_id",
                      lambda: form.integer("account_id", required=True, label="Funded account"))
    if account_id is not None:
        acct = conn.execute("SELECT type FROM accounts WHERE id = ?", (account_id,)).fetchone()
        if acct is None:
            form.error("account_id", "Choose an existing account.")
        elif acct["type"] != "funded":
            form.error("account_id", "Payouts can only be recorded on funded accounts.")

    fields = dict(
        account_id=account_id,
        requested_cents=pick("amount_requested", "requested_cents",
                             lambda: form.money("amount_requested", required=True,
                                                label="Amount requested")),
        received_cents=pick("amount_received", "received_cents",
                            lambda: form.money("amount_received")),
        request_date=pick("request_date", "request_date",
                          lambda: form.date("request_date", required=True, label="Request date")),
        payment_date=pick("payment_date", "payment_date", lambda: form.date("payment_date")),
        status=pick("status", "status", lambda: form.choice("status", STATUSES)) or "requested",
        notes=pick("notes", "notes", lambda: form.text("notes")),
    )

    if fields["status"] == "paid":
        if fields["received_cents"] is None and "amount_received" not in form.errors:
            form.error("amount_received", "Enter the amount actually received for a paid payout.")
        fields["payment_date"] = fields["payment_date"] or today()
    elif fields["status"] == "rejected":
        fields["received_cents"] = None
        fields["payment_date"] = None
    if (fields["payment_date"] and fields["request_date"]
            and fields["payment_date"] < fields["request_date"]):
        form.error("payment_date", "Payment date cannot be before the request date.")
    form.check()
    return fields


@bp.get("/api/payouts")
def list_payouts():
    conn = get_db()
    where, params = [], []
    status = request.args.get("status", "").strip().lower()
    account_id = request.args.get("account_id", "").strip()
    if status in STATUSES:
        where.append("p.status = ?")
        params.append(status)
    if account_id:
        try:
            params.append(int(account_id))
        except ValueError:
            raise ValidationError({"account_id": "Invalid account."})
        where.append("p.account_id = ?")
    sql = PAYOUT_SQL + (" WHERE " + " AND ".join(where) if where else "")
    sql += " ORDER BY p.request_date DESC, p.id DESC"
    return jsonify([serialize(r) for r in conn.execute(sql, params)])


@bp.post("/api/payouts")
def post_payout():
    conn = get_db()
    fields = _read_fields(conn, request.get_json(silent=True))
    cur = conn.execute(
        """INSERT INTO payouts (account_id, requested_cents, received_cents, request_date,
                                payment_date, status, notes)
           VALUES (:account_id, :requested_cents, :received_cents, :request_date,
                   :payment_date, :status, :notes)""", fields)
    conn.commit()
    return jsonify(serialize(get_payout(conn, cur.lastrowid))), 201


@bp.put("/api/payouts/<int:payout_id>")
def put_payout(payout_id):
    conn = get_db()
    existing = get_payout(conn, payout_id)
    fields = _read_fields(conn, request.get_json(silent=True), existing)
    conn.execute(
        """UPDATE payouts SET account_id=:account_id, requested_cents=:requested_cents,
               received_cents=:received_cents, request_date=:request_date,
               payment_date=:payment_date, status=:status, notes=:notes,
               updated_at=datetime('now')
           WHERE id=:id""", {**fields, "id": payout_id})
    conn.commit()
    return jsonify(serialize(get_payout(conn, payout_id)))


@bp.delete("/api/payouts/<int:payout_id>")
def remove_payout(payout_id):
    conn = get_db()
    get_payout(conn, payout_id)
    conn.execute("DELETE FROM payouts WHERE id = ?", (payout_id,))
    conn.commit()
    return jsonify({"ok": True})

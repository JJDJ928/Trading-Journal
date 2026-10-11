"""Dashboard and rinse-system statistics, computed from recorded data only.

Definitions:
  * Evaluations purchased  = every account of type 'evaluation'.
  * Passed evaluation      = an evaluation with a pass date (statuses passed,
                             funded, or closed after passing).
  * Failed evaluation      = an evaluation with status failed.
  * Pass rate              = passed / (passed + failed). Active evaluations and
                             evaluations closed without passing are excluded.
  * Fees spent             = purchase cost of every account (evaluation fees plus
                             any activation fees recorded on funded accounts).
  * Payouts received       = payouts with status 'paid', using the amount
                             actually received.
  * Net cash flow          = payouts received - fees spent.
  * Trade P&L is shown separately; it is money earned on an account, not cash
    received, and never counts toward cash flow.
"""
from flask import Blueprint, jsonify

from .db import get_db
from .validation import from_cents

bp = Blueprint("stats", __name__)


def compute_summary(conn):
    acc = conn.execute("""
        SELECT
          COALESCE(SUM(type = 'evaluation'), 0)                              AS evals,
          COALESCE(SUM(type = 'evaluation' AND status = 'active'), 0)        AS evals_active,
          COALESCE(SUM(type = 'evaluation' AND pass_date IS NOT NULL), 0)    AS evals_passed,
          COALESCE(SUM(type = 'evaluation' AND status = 'failed'), 0)        AS evals_failed,
          COALESCE(SUM(type = 'funded'), 0)                                  AS funded,
          COALESCE(SUM(type = 'funded' AND status = 'funded'), 0)            AS funded_active,
          COALESCE(SUM(type = 'funded' AND status = 'failed'), 0)            AS funded_failed,
          COALESCE(SUM(cost_cents), 0)                                       AS fees,
          COALESCE(SUM(CASE WHEN type = 'evaluation' THEN cost_cents END), 0) AS eval_fees
        FROM accounts""").fetchone()
    pay = conn.execute("""
        SELECT
          COALESCE(SUM(status = 'paid'), 0)                                          AS paid_count,
          COALESCE(SUM(CASE WHEN status = 'paid' THEN received_cents END), 0)        AS received,
          COALESCE(SUM(status IN ('requested', 'approved')), 0)                      AS pending_count,
          COALESCE(SUM(CASE WHEN status IN ('requested', 'approved')
                            THEN requested_cents END), 0)                           AS pending
        FROM payouts""").fetchone()
    trd = conn.execute("""
        SELECT COUNT(*) AS n,
               COALESCE(SUM(result = 'win'), 0)        AS wins,
               COALESCE(SUM(result = 'loss'), 0)       AS losses,
               COALESCE(SUM(result = 'breakeven'), 0)  AS breakevens,
               COALESCE(SUM(pnl_cents), 0)             AS pnl
        FROM trades""").fetchone()

    completed = acc["evals_passed"] + acc["evals_failed"]
    return {
        "evaluations_purchased": acc["evals"],
        "evaluations_active": acc["evals_active"],
        "evaluations_passed": acc["evals_passed"],
        "evaluations_failed": acc["evals_failed"],
        "evaluations_completed": completed,
        "pass_rate": (acc["evals_passed"] / completed) if completed else None,
        "funded_accounts": acc["funded"],
        "funded_active": acc["funded_active"],
        "funded_failed": acc["funded_failed"],
        "total_fees": from_cents(acc["fees"]),
        "evaluation_fees": from_cents(acc["eval_fees"]),
        "activation_fees": from_cents(acc["fees"] - acc["eval_fees"]),
        "payouts_paid_count": pay["paid_count"],
        "payouts_received": from_cents(pay["received"]),
        "payouts_pending_count": pay["pending_count"],
        "payouts_pending_amount": from_cents(pay["pending"]),
        "net_cash_flow": from_cents(pay["received"] - acc["fees"]),
        "trades": trd["n"],
        "wins": trd["wins"],
        "losses": trd["losses"],
        "breakevens": trd["breakevens"],
        "trade_pnl_recorded": from_cents(trd["pnl"]),
    }


def per_account(conn):
    rows = conn.execute("""
        SELECT a.id, a.firm, a.account_ref, a.size_cents, a.type, a.status, a.cost_cents,
               a.purchase_date, a.pass_date, a.end_date, a.parent_id,
               (SELECT c.id FROM accounts c WHERE c.parent_id = a.id) AS child_id,
               COUNT(t.id)                          AS trades,
               COALESCE(SUM(t.result = 'win'), 0)   AS wins,
               COALESCE(SUM(t.result = 'loss'), 0)  AS losses,
               COALESCE(SUM(t.pnl_cents), 0)        AS pnl_cents,
               (SELECT COALESCE(SUM(p.received_cents), 0) FROM payouts p
                 WHERE p.account_id = a.id AND p.status = 'paid') AS received_cents
        FROM accounts a LEFT JOIN trades t ON t.account_id = a.id
        GROUP BY a.id
        ORDER BY a.purchase_date DESC, a.id DESC""")
    out = []
    for r in rows:
        d = dict(r)
        d["size"] = from_cents(d.pop("size_cents"))
        cost_cents = d.pop("cost_cents")
        d["cost"] = from_cents(cost_cents)
        d["pnl"] = from_cents(d.pop("pnl_cents"))
        received = d.pop("received_cents")
        d["payouts_received"] = from_cents(received)
        d["net_cash_flow"] = from_cents(received - cost_cents)
        out.append(d)
    return out


@bp.get("/api/stats")
def get_stats():
    conn = get_db()
    return jsonify({"summary": compute_summary(conn), "accounts": per_account(conn)})


@bp.get("/api/dashboard")
def get_dashboard():
    conn = get_db()
    recent = conn.execute("""
        SELECT t.id, t.traded_at, t.instrument, t.result, t.pnl_cents, t.summary,
               a.id AS account_id, a.firm, a.account_ref, a.size_cents,
               (SELECT COUNT(*) FROM screenshots s WHERE s.trade_id = t.id) AS screenshot_count
        FROM trades t JOIN accounts a ON a.id = t.account_id
        ORDER BY t.traded_at DESC, t.id DESC LIMIT 6""").fetchall()
    active = conn.execute("""
        SELECT id, firm, account_ref, size_cents, type, status FROM accounts
        WHERE status IN ('active', 'passed', 'funded') AND NOT (type = 'evaluation' AND status = 'funded')
        ORDER BY type DESC, purchase_date DESC LIMIT 12""").fetchall()

    def money(row, key):
        d = dict(row)
        d[key.replace("_cents", "")] = from_cents(d.pop(key))
        return d

    recent_out = []
    for r in recent:
        d = money(r, "pnl_cents")
        d["account_size"] = from_cents(d.pop("size_cents"))
        recent_out.append(d)
    return jsonify({
        "summary": compute_summary(conn),
        "recent_trades": recent_out,
        "open_accounts": [money(r, "size_cents") for r in active],
    })

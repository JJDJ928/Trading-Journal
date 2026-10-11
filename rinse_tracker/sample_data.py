"""Sample records for trying the app. Only used by `python run.py --demo`,
which runs against a separate ./demo-data folder. Never seeds your real data."""
import io
import struct
import zlib
from datetime import date, timedelta

from werkzeug.datastructures import FileStorage

from . import accounts, db, trades


def _png(width, height, rgb):
    raw = b"".join(b"\x00" + bytes(rgb) * width for _ in range(height))

    def chunk(kind, data):
        return (struct.pack(">I", len(data)) + kind + data
                + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def seed_if_empty(app):
    if not app.config.get("DEMO"):
        raise RuntimeError("Sample data may only be loaded in demo mode.")
    conn = db.connect(app.config["DB_PATH"])
    try:
        if conn.execute("SELECT COUNT(*) FROM accounts").fetchone()[0]:
            return
        d = lambda days: (date.today() - timedelta(days=days)).isoformat()
        e1 = accounts.create_account(conn, {"firm": "Apex", "account_ref": "APX-1001", "size": 50000,
                                            "type": "evaluation", "cost": 167, "purchase_date": d(40)})
        accounts.update_account(conn, e1, {"status": "passed", "pass_date": d(30)})
        f1 = accounts.convert_to_funded(conn, e1, {"cost": 85})
        e2 = accounts.create_account(conn, {"firm": "Apex", "account_ref": "APX-1002", "size": 50000,
                                            "type": "evaluation", "cost": 167, "purchase_date": d(35)})
        accounts.update_account(conn, e2, {"status": "failed", "end_date": d(28)})
        accounts.create_account(conn, {"firm": "Topstep", "size": 100000, "type": "evaluation",
                                       "cost": 149, "purchase_date": d(10)})
        accounts.create_account(conn, {"firm": "MyFundedFutures", "size": 50000, "type": "evaluation",
                                       "cost": 77, "purchase_date": d(3)})

        shot = lambda name, rgb: FileStorage(io.BytesIO(_png(320, 180, rgb)), filename=name)
        upload = app.config["UPLOAD_DIR"]
        for i, (acct, res, pnl, inst, txt) in enumerate([
            (e1, "win", 820, "NQ", "Opening drive long, held to target."),
            (e1, "loss", -310, "NQ", "Chased the breakout. Wait for the retest."),
            (e2, "loss", -1250, "ES", "Revenge trade after news spike. Breached daily limit."),
            (f1, "win", 640, "NQ", "A+ setup, followed plan."),
            (f1, "breakeven", 0, "MNQ", "Moved stop to entry, stopped out flat."),
        ]):
            trades.create_trade(conn, {"account_id": acct, "traded_at": f"{d(25 - i * 5)}T09:4{i}",
                                       "instrument": inst, "result": res, "pnl": pnl, "summary": txt},
                                [shot(f"chart-{i}.png", (30 + i * 40, 60, 90))], upload)

        conn.execute("INSERT INTO payouts (account_id, requested_cents, received_cents, request_date, "
                     "payment_date, status) VALUES (?, 100000, 90000, ?, ?, 'paid')", (f1, d(8), d(5)))
        conn.execute("INSERT INTO payouts (account_id, requested_cents, request_date, status) "
                     "VALUES (?, 50000, ?, 'requested')", (f1, d(1)))
        conn.commit()
    finally:
        conn.close()


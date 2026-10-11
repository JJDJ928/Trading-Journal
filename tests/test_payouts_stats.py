import pytest

from conftest import funded_account, new_account


def test_payout_only_on_funded_accounts(client):
    ev = new_account(client)
    resp = client.post("/api/payouts", json={"account_id": ev["id"], "amount_requested": 500,
                                             "request_date": "2026-02-01"})
    assert resp.status_code == 400 and "account_id" in resp.json["fields"]


def test_paid_requires_received_amount(client):
    f = funded_account(client)
    resp = client.post("/api/payouts", json={"account_id": f["id"], "amount_requested": 1000,
                                             "request_date": "2026-02-01", "status": "paid"})
    assert resp.status_code == 400 and "amount_received" in resp.json["fields"]


def test_empty_stats(client):
    s = client.get("/api/stats").json["summary"]
    assert s["evaluations_purchased"] == 0 and s["pass_rate"] is None
    assert s["net_cash_flow"] == 0 and s["payouts_received"] == 0


def test_rinse_calculations(client):
    # 5 evaluations: 1 passed+funded, 1 passed (not yet funded), 2 failed, 1 still active.
    funded = funded_account(client, cost=85)                          # eval cost 167
    passed = new_account(client, cost="99.99")
    client.put(f"/api/accounts/{passed['id']}", json={"status": "passed"})
    for _ in range(2):
        a = new_account(client, cost=150)
        client.put(f"/api/accounts/{a['id']}", json={"status": "failed"})
    new_account(client, cost=100)                                     # active

    fid = funded["id"]
    def payout(**kw):
        body = {"account_id": fid, "amount_requested": 1000, "request_date": "2026-03-01"}
        body.update(kw)
        assert client.post("/api/payouts", json=body).status_code == 201
    payout(status="paid", amount_received="900.50")
    payout(status="approved", amount_received=1000)   # approved: not counted as received
    payout(status="requested")
    payout(status="rejected", amount_received=1000)   # rejected: never counted

    # Profitable trades on the funded account must NOT count as payouts.
    client.post("/api/trades", json={"account_id": fid, "traded_at": "2026-03-02T09:00",
                                     "result": "win", "pnl": 5000})

    s = client.get("/api/stats").json["summary"]
    assert s["evaluations_purchased"] == 5
    assert s["evaluations_active"] == 1
    assert s["evaluations_passed"] == 2
    assert s["evaluations_failed"] == 2
    assert s["pass_rate"] == pytest.approx(0.5)       # 2 / (2 + 2), active excluded
    assert s["funded_accounts"] == 1                   # converted eval not double counted
    assert s["evaluation_fees"] == pytest.approx(167 + 99.99 + 300 + 100)
    assert s["total_fees"] == pytest.approx(666.99 + 85)
    assert s["payouts_paid_count"] == 1
    assert s["payouts_received"] == pytest.approx(900.50)
    assert s["payouts_pending_amount"] == pytest.approx(2000)
    assert s["net_cash_flow"] == pytest.approx(900.50 - 751.99)
    assert s["trade_pnl_recorded"] == 5000

    per = {a["id"]: a for a in client.get("/api/stats").json["accounts"]}
    assert per[fid]["payouts_received"] == pytest.approx(900.50)
    assert per[fid]["net_cash_flow"] == pytest.approx(815.50)


def test_marking_paid_updates_totals(client):
    f = funded_account(client)
    p = client.post("/api/payouts", json={"account_id": f["id"], "amount_requested": 500,
                                          "request_date": "2026-03-01"}).json
    assert client.get("/api/dashboard").json["summary"]["payouts_received"] == 0
    resp = client.put(f"/api/payouts/{p['id']}", json={"status": "paid", "amount_received": 480})
    assert resp.status_code == 200 and resp.json["payment_date"]
    assert client.get("/api/dashboard").json["summary"]["payouts_received"] == 480
    client.put(f"/api/payouts/{p['id']}", json={"status": "rejected"})
    assert client.get("/api/dashboard").json["summary"]["payouts_received"] == 0


def test_closed_after_pass_still_counts_as_passed(client):
    a = new_account(client)
    client.put(f"/api/accounts/{a['id']}", json={"status": "passed"})
    client.put(f"/api/accounts/{a['id']}", json={"status": "closed"})
    b = new_account(client)
    client.put(f"/api/accounts/{b['id']}", json={"status": "closed"})  # never passed
    s = client.get("/api/stats").json["summary"]
    assert s["evaluations_passed"] == 1 and s["evaluations_failed"] == 0
    assert s["pass_rate"] == 1.0


def test_today_pnl_for_afk_screen(client):
    acct = new_account(client)
    for when, pnl in (("2026-03-02T09:00", 300), ("2026-03-02T14:30", -500), ("2026-03-01T10:00", 900)):
        client.post("/api/trades", json={"account_id": acct["id"], "traded_at": when,
                                         "result": "win" if pnl > 0 else "loss", "pnl": pnl})
    day = client.get("/api/today?date=2026-03-02").json
    assert day == {"date": "2026-03-02", "trades": 2, "pnl": -200}
    assert client.get("/api/today?date=2026-03-03").json["pnl"] == 0
    assert client.get("/api/today?date=nope").status_code == 400

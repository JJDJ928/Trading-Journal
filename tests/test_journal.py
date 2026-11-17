"""Tests for the Trading Journal app (journal/)."""
import io
import os

import pytest

from journal import create_app

from conftest import make_png


@pytest.fixture
def jclient(tmp_path):
    return create_app(str(tmp_path / "journal")).test_client()


def add_account(c, **over):
    body = {"name": "Apex 150K #1", "firm": "Apex", "type": "funded", "start_balance": "150,000",
            "max_drawdown": "5000"}
    body.update(over)
    r = c.post("/api/accounts", json=body)
    assert r.status_code == 201, r.json
    return r.json


def add_trade(c, account_id, **over):
    body = {"account_id": str(account_id), "traded_at": "2026-11-16T09:42", "symbol": "nq", "side": "long",
            "contracts": "2", "setup": "ORB break", "entry": "21,312.50", "stop": "21304", "exit": "21328",
            "pnl": "620", "notes": "Patient entry", "tags": "ORB, #A+ setup"}
    body.update(over)
    r = c.post("/api/trades", data=body, content_type="multipart/form-data")
    assert r.status_code == 201, r.json
    return r.json


def test_pages_and_static_files_load(jclient):
    for path in ("/", "/static/js/app.js", "/static/js/atom.js", "/static/css/app.css",
                 "/static/fonts/inter-variable.woff2"):
        assert jclient.get(path).status_code == 200, path


def test_settings_default_name_and_update(jclient):
    assert jclient.get("/api/settings").json["name"] == "Jordi"
    assert jclient.put("/api/settings", json={"name": "  "}).status_code == 400
    assert jclient.put("/api/settings", json={"name": "J"}).json["name"] == "J"
    assert jclient.get("/api/settings").json["name"] == "J"


def test_account_create_update_and_validation(jclient):
    bad = jclient.post("/api/accounts", json={"name": "", "start_balance": "abc", "type": "x"})
    assert bad.status_code == 400
    assert set(bad.json["fields"]) >= {"name", "start_balance", "type"}

    a = add_account(jclient)
    assert a["start_balance"] == 150000 and a["max_drawdown"] == 5000 and a["status"] == "active"
    r = jclient.put(f"/api/accounts/{a['id']}", json={**a, "start_balance": a["start_balance"], "status": "breached"})
    assert r.status_code == 200 and r.json["status"] == "breached"
    assert jclient.put("/api/accounts/999", json=a).status_code == 404


def test_trade_create_parses_values(jclient):
    a = add_account(jclient)
    t = add_trade(jclient, a["id"])
    assert t["symbol"] == "NQ" and t["entry"] == 21312.5 and t["pnl"] == 620
    assert t["tags"] == ["ORB", "A+ setup"]
    loss = add_trade(jclient, a["id"], pnl="-180.50", side="short")
    assert loss["pnl"] == -180.5
    # same time: newest saved first
    assert [x["id"] for x in jclient.get("/api/trades").json] == [loss["id"], t["id"]]


def test_trade_validation(jclient):
    a = add_account(jclient)
    r = jclient.post("/api/trades", data={"account_id": str(a["id"]), "symbol": "", "side": "up", "pnl": "x",
                                          "traded_at": "nope"}, content_type="multipart/form-data")
    assert r.status_code == 400
    assert set(r.json["fields"]) >= {"symbol", "side", "pnl", "traded_at"}
    r = jclient.post("/api/trades", data={"account_id": "999", "symbol": "ES", "side": "long", "pnl": "1",
                                          "traded_at": "2026-11-16T10:00"}, content_type="multipart/form-data")
    assert r.status_code == 400 and "account_id" in r.json["fields"]


def test_screenshots_upload_serve_remove(jclient, tmp_path):
    a = add_account(jclient)
    t = add_trade(jclient, a["id"], screenshots=[(io.BytesIO(make_png()), "chart.png")])
    assert len(t["screenshots"]) == 1
    url = t["screenshots"][0]["url"]
    assert jclient.get(url).status_code == 200

    bad = jclient.post("/api/trades", data={"account_id": str(a["id"]), "symbol": "ES", "side": "long",
                                            "pnl": "5", "traded_at": "2026-11-16T10:00",
                                            "screenshots": [(io.BytesIO(b"not an image"), "x.txt")]},
                       content_type="multipart/form-data")
    assert bad.status_code == 400 and "screenshots" in bad.json["fields"]

    shot_id = t["screenshots"][0]["id"]
    r = jclient.put(f"/api/trades/{t['id']}", data={**{k: str(v) for k, v in {
        "account_id": a["id"], "traded_at": t["traded_at"], "symbol": "NQ", "side": "long", "pnl": "700"}.items()},
        "remove_screenshots": str(shot_id)}, content_type="multipart/form-data")
    assert r.status_code == 200 and r.json["pnl"] == 700 and r.json["screenshots"] == []
    files = os.listdir(tmp_path / "journal" / "screenshots")
    assert files == []


def test_delete_trade_and_account_cascade(jclient, tmp_path):
    a = add_account(jclient)
    t = add_trade(jclient, a["id"], screenshots=[(io.BytesIO(make_png()), "c.png")])
    add_trade(jclient, a["id"])
    assert jclient.delete(f"/api/trades/{t['id']}").status_code == 200
    assert len(jclient.get("/api/trades").json) == 1
    assert jclient.delete(f"/api/accounts/{a['id']}").status_code == 200
    assert jclient.get("/api/trades").json == []
    assert os.listdir(tmp_path / "journal" / "screenshots") == []


def test_data_survives_restart(tmp_path):
    folder = str(tmp_path / "persist")
    c = create_app(folder).test_client()
    a = add_account(c)
    add_trade(c, a["id"])
    c2 = create_app(folder).test_client()
    assert len(c2.get("/api/accounts").json) == 1 and len(c2.get("/api/trades").json) == 1

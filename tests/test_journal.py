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


def test_daily_tasks_and_journal(jclient):
    assert jclient.get("/api/days").json == []
    r = jclient.put("/api/days/2026-11-16", json={"done": ["gym", "nonsense", "trading"], "journal": " Good day. "})
    assert r.status_code == 200
    assert r.json == {"date": "2026-11-16", "done": ["trading", "gym"], "journal": "Good day.", "mood": None, "energy": None}
    jclient.put("/api/days/2026-11-17", json={"done": ["reading"]})
    assert [d["date"] for d in jclient.get("/api/days").json] == ["2026-11-16", "2026-11-17"]
    # updating replaces, and an emptied day is removed
    jclient.put("/api/days/2026-11-16", json={"done": [], "journal": "Only notes"})
    assert jclient.get("/api/days").json[0] == {"date": "2026-11-16", "done": [], "journal": "Only notes",
                                                 "mood": None, "energy": None}
    jclient.put("/api/days/2026-11-17", json={"done": [], "journal": ""})
    assert len(jclient.get("/api/days").json) == 1
    assert jclient.put("/api/days/not-a-date", json={"done": []}).status_code == 404
    assert jclient.put("/api/days/2026-11-16", json={"done": "gym"}).status_code == 400


def test_mood_energy_partial_updates(jclient):
    jclient.put("/api/days/2026-11-16", json={"done": ["gym"], "journal": "Hi"})
    r = jclient.put("/api/days/2026-11-16", json={"mood": 4})
    assert r.json["mood"] == 4 and r.json["done"] == ["gym"] and r.json["journal"] == "Hi"
    r = jclient.put("/api/days/2026-11-16", json={"energy": "2"})
    assert r.json["energy"] == 2 and r.json["mood"] == 4
    assert jclient.put("/api/days/2026-11-16", json={"mood": 9}).status_code == 400
    # a day with only a mood is kept; clearing everything removes it
    jclient.put("/api/days/2026-11-17", json={"mood": 3})
    assert any(d["date"] == "2026-11-17" for d in jclient.get("/api/days").json)
    jclient.put("/api/days/2026-11-17", json={"mood": None})
    assert not any(d["date"] == "2026-11-17" for d in jclient.get("/api/days").json)


def test_old_database_gets_new_columns(tmp_path):
    import sqlite3
    folder = tmp_path / "old"
    folder.mkdir()
    conn = sqlite3.connect(folder / "journal.db")
    conn.execute("CREATE TABLE days (date TEXT PRIMARY KEY, done TEXT NOT NULL DEFAULT '[]', journal TEXT, "
                 "updated_at TEXT NOT NULL DEFAULT (datetime('now')))")
    conn.execute("INSERT INTO days (date, done, journal) VALUES ('2026-11-10', '[\"gym\"]', 'kept')")
    conn.commit()
    conn.close()
    c = create_app(str(folder)).test_client()
    assert c.get("/api/days").json == [{"date": "2026-11-10", "done": ["gym"], "journal": "kept", "mood": None, "energy": None}]
    assert c.put("/api/days/2026-11-10", json={"mood": 5}).json["mood"] == 5


def test_books_and_chapter_recaps(jclient):
    assert jclient.post("/api/books", json={"title": ""}).status_code == 400
    b = jclient.post("/api/books", json={"title": "Trading in the Zone", "author": "Mark Douglas", "total_chapters": "11"}).json
    assert b["status"] == "reading" and b["total_chapters"] == 11
    r = jclient.put("/api/chapters/2026-11-16", json={"book_id": b["id"], "chapter": 3, "learned": "Think in probabilities."})
    assert r.status_code == 200 and r.json["chapter"] == 3
    jclient.put("/api/chapters/2026-11-17", json={"book_id": b["id"], "chapter": 4, "learned": "Consistency."})
    assert [c["chapter"] for c in jclient.get("/api/chapters").json] == [3, 4]
    # empty recap removes that day
    jclient.put("/api/chapters/2026-11-17", json={"book_id": b["id"], "chapter": "", "learned": ""})
    assert len(jclient.get("/api/chapters").json) == 1
    assert jclient.put("/api/chapters/2026-11-18", json={"book_id": 999, "chapter": 1}).status_code == 404
    done = jclient.put(f"/api/books/{b['id']}", json={**b, "status": "finished", "finished_on": "2026-11-20"}).json
    assert done["status"] == "finished" and done["finished_on"] == "2026-11-20"
    assert jclient.delete(f"/api/books/{b['id']}").status_code == 200
    assert jclient.get("/api/chapters").json == []


def test_wins_with_photo(jclient, tmp_path):
    bad = jclient.post("/api/wins", data={"title": "", "date": "x"}, content_type="multipart/form-data")
    assert bad.status_code == 400 and {"title", "date"} <= set(bad.json["fields"])
    w = jclient.post("/api/wins", data={"title": "First payout", "date": "2026-11-16", "category": "trading",
                                        "note": "$2,000", "photo": [(io.BytesIO(make_png()), "p.png")]},
                     content_type="multipart/form-data").json
    assert w["category"] == "trading" and w["photo"]
    assert jclient.get(w["photo"]).status_code == 200
    r = jclient.put(f"/api/wins/{w['id']}", data={"title": "First payout!", "date": "2026-11-16",
                                                   "category": "trading", "remove_photo": "1"},
                    content_type="multipart/form-data").json
    assert r["title"] == "First payout!" and r["photo"] is None
    assert os.listdir(tmp_path / "journal" / "screenshots") == []
    assert jclient.delete(f"/api/wins/{w['id']}").status_code == 200
    assert jclient.get("/api/wins").json == []

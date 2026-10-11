import os

from conftest import new_account


def post_trade(client, acct_id, files=(), **fields):
    data = {"account_id": str(acct_id), "traded_at": "2026-02-01T09:30", "instrument": "nq",
            "result": "win", "pnl": "250", "summary": "Clean long"}
    data.update(fields)
    if files:
        data["screenshots"] = list(files)
    return client.post("/api/trades", data=data, content_type="multipart/form-data")


def test_trade_with_multiple_screenshots(client, app, png):
    acct = new_account(client)
    resp = post_trade(client, acct["id"], files=[png("a.png"), png("b.png")])
    assert resp.status_code == 201, resp.json
    trade = resp.json
    assert trade["instrument"] == "NQ" and trade["pnl"] == 250
    assert len(trade["screenshots"]) == 2
    for shot in trade["screenshots"]:
        img = client.get(shot["url"])
        assert img.status_code == 200 and img.data.startswith(b"\x89PNG")
    assert len(os.listdir(app.config["UPLOAD_DIR"])) == 2


def test_invalid_image_rejected_and_nothing_saved(client, app, png):
    import io
    acct = new_account(client)
    resp = post_trade(client, acct["id"], files=[png(), (io.BytesIO(b"not an image"), "evil.png")])
    assert resp.status_code == 400
    assert "screenshots" in resp.json["fields"]
    assert os.listdir(app.config["UPLOAD_DIR"]) == []
    assert client.get("/api/trades").json == []


def test_minimal_trade_and_validation(client):
    acct = new_account(client)
    resp = client.post("/api/trades", json={"account_id": acct["id"],
                                            "traded_at": "2026-02-01T10:00", "result": "loss"})
    assert resp.status_code == 201 and resp.json["pnl"] is None
    bad = client.post("/api/trades", json={"account_id": 999, "result": "maybe"})
    assert bad.status_code == 400
    assert {"account_id", "result", "traded_at"} <= set(bad.json["fields"])


def test_edit_remove_and_add_screenshots(client, app, png):
    acct = new_account(client)
    trade = post_trade(client, acct["id"], files=[png("a.png"), png("b.png")]).json
    remove = trade["screenshots"][0]
    resp = client.put(f"/api/trades/{trade['id']}", content_type="multipart/form-data",
                      data={"summary": "Updated", "remove_screenshots": str(remove["id"]),
                            "screenshots": [png("c.png")]})
    assert resp.status_code == 200, resp.json
    assert resp.json["summary"] == "Updated" and resp.json["result"] == "win"
    names = [s["original_name"] for s in resp.json["screenshots"]]
    assert names == ["b.png", "c.png"]
    assert client.get(remove["url"]).status_code == 404
    assert len(os.listdir(app.config["UPLOAD_DIR"])) == 2


def test_delete_trade_removes_files(client, app, png):
    acct = new_account(client)
    trade = post_trade(client, acct["id"], files=[png()]).json
    assert client.delete(f"/api/trades/{trade['id']}").status_code == 200
    assert os.listdir(app.config["UPLOAD_DIR"]) == []
    assert client.delete(f"/api/trades/{trade['id']}").status_code == 404


def test_history_newest_first_and_filters(client):
    a = new_account(client)
    b = new_account(client, firm="Topstep")
    post_trade(client, a["id"], traded_at="2026-02-01T09:00", result="loss", summary="first")
    post_trade(client, a["id"], traded_at="2026-02-03T09:00", summary="third")
    post_trade(client, b["id"], traded_at="2026-02-02T09:00", instrument="ES", summary="second")
    assert [t["summary"] for t in client.get("/api/trades").json] == ["third", "second", "first"]
    assert len(client.get(f"/api/trades?account_id={a['id']}").json) == 2
    assert len(client.get("/api/trades?result=loss").json) == 1
    assert [t["summary"] for t in client.get("/api/trades?q=es").json] == ["second"]


def test_upload_path_traversal_blocked(client):
    assert client.get("/uploads/../rinse.db").status_code == 404

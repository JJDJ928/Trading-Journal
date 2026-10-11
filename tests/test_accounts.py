from conftest import funded_account, new_account


def test_create_account_defaults_and_money_parsing(client):
    acct = new_account(client)
    assert acct["size"] == 50000
    assert acct["cost"] == 167
    assert acct["status"] == "active"
    assert acct["type"] == "evaluation"


def test_create_account_rejects_bad_input(client):
    resp = client.post("/api/accounts", json={"firm": "", "size": "abc", "type": "x",
                                              "cost": "-5", "purchase_date": "nope"})
    assert resp.status_code == 400
    fields = resp.json["fields"]
    assert {"firm", "size", "type", "cost", "purchase_date"} <= set(fields)
    assert client.post("/api/accounts", data="garbage").status_code == 400
    assert client.get("/api/accounts").json == []


def test_status_progression_and_history(client):
    acct = new_account(client)
    resp = client.put(f"/api/accounts/{acct['id']}", json={"status": "passed"})
    assert resp.status_code == 200
    assert resp.json["pass_date"]  # defaults to today
    resp = client.put(f"/api/accounts/{acct['id']}", json={"status": "failed"})
    assert resp.json["pass_date"] is None and resp.json["end_date"]
    detail = client.get(f"/api/accounts/{acct['id']}").json
    assert [h["to_status"] for h in detail["history"]] == ["active", "passed", "failed"]


def test_partial_update_keeps_other_fields(client):
    acct = new_account(client, account_ref="A-1", notes="keep me")
    resp = client.put(f"/api/accounts/{acct['id']}", json={"firm": "Topstep"})
    assert resp.json["firm"] == "Topstep"
    assert resp.json["size"] == 50000 and resp.json["notes"] == "keep me"


def test_funded_status_not_allowed_on_evaluation_manually(client):
    acct = new_account(client)
    resp = client.put(f"/api/accounts/{acct['id']}", json={"status": "funded"})
    assert resp.status_code == 400
    resp = client.post("/api/accounts", json={"firm": "X", "size": 1, "type": "funded",
                                              "purchase_date": "2026-01-01", "status": "active"})
    assert resp.status_code == 400


def test_convert_requires_passed_and_happens_once(client):
    ev = new_account(client)
    assert client.post(f"/api/accounts/{ev['id']}/fund", json={}).status_code == 400
    funded = funded_account(client)
    parent_id = funded["parent_id"]
    assert funded["type"] == "funded" and funded["size"] == 50000
    parent = client.get(f"/api/accounts/{parent_id}").json
    assert parent["status"] == "funded" and parent["child"]["id"] == funded["id"]
    again = client.post(f"/api/accounts/{parent_id}/fund", json={})
    assert again.status_code == 400
    # A converted evaluation's status is locked; the funded account carries on.
    assert client.put(f"/api/accounts/{parent_id}", json={"status": "failed"}).status_code == 400


def test_failed_accounts_are_kept_and_filterable(client):
    a = new_account(client, firm="Apex")
    new_account(client, firm="Topstep")
    client.put(f"/api/accounts/{a['id']}", json={"status": "failed"})
    assert len(client.get("/api/accounts").json) == 2
    failed = client.get("/api/accounts?status=failed").json
    assert [x["id"] for x in failed] == [a["id"]]
    assert len(client.get("/api/accounts?q=top").json) == 1


def test_delete_linked_funded_reverts_parent(client):
    funded = funded_account(client)
    parent_id = funded["parent_id"]
    assert client.delete(f"/api/accounts/{parent_id}").status_code == 400
    assert client.delete(f"/api/accounts/{funded['id']}").status_code == 200
    assert client.get(f"/api/accounts/{parent_id}").json["status"] == "passed"


def test_missing_account_404(client):
    assert client.get("/api/accounts/999").status_code == 404

import io
import os
import zipfile

from rinse_tracker import create_app
from rinse_tracker.sample_data import seed_if_empty
from conftest import new_account
from test_trades import post_trade

import pytest


def test_data_survives_restart(data_dir, png):
    client = create_app(str(data_dir)).test_client()
    acct = new_account(client)
    post_trade(client, acct["id"], files=[png()])
    # A brand new app instance on the same folder sees everything.
    client2 = create_app(str(data_dir)).test_client()
    trades = client2.get("/api/trades").json
    assert len(trades) == 1 and client2.get(trades[0]["screenshots"][0]["url"]).status_code == 200


def test_backup_and_restore_roundtrip(client, app, png):
    acct = new_account(client, firm="Original")
    post_trade(client, acct["id"], files=[png()])
    backup = client.get("/api/backup")
    assert backup.status_code == 200
    with zipfile.ZipFile(io.BytesIO(backup.data)) as zf:
        names = zf.namelist()
    assert "rinse.db" in names and "manifest.json" in names
    assert sum(n.startswith("uploads/") for n in names) == 1

    # Change things after the backup...
    new_account(client, firm="After backup")
    client.delete(f"/api/trades/{client.get('/api/trades').json[0]['id']}")

    resp = client.post("/api/backup/restore", content_type="multipart/form-data",
                       data={"backup": (io.BytesIO(backup.data), "b.zip")})
    assert resp.status_code == 200, resp.json
    assert resp.json["missing_screenshots"] == 0
    assert [a["firm"] for a in client.get("/api/accounts").json] == ["Original"]
    trades = client.get("/api/trades").json
    assert client.get(trades[0]["screenshots"][0]["url"]).status_code == 200
    # The pre-restore state was saved as a safety backup.
    safety = os.listdir(os.path.join(app.config["DATA_DIR"], "backups"))
    assert len(safety) == 1 and safety[0].startswith("pre-restore-")


@pytest.mark.parametrize("payload", [b"not a zip", None])
def test_restore_rejects_invalid_files(client, payload):
    new_account(client)
    if payload is None:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("manifest.json", '{"app": "rinse-tracker"}')
            zf.writestr("rinse.db", b"garbage")
            zf.writestr("uploads/../../evil.txt", b"x")
        payload = buf.getvalue()
    resp = client.post("/api/backup/restore", content_type="multipart/form-data",
                       data={"backup": (io.BytesIO(payload), "x.zip")})
    assert resp.status_code == 400
    assert len(client.get("/api/accounts").json) == 1  # existing data untouched


def test_sample_data_refuses_real_data(app):
    with pytest.raises(RuntimeError):
        seed_if_empty(app)


def test_demo_mode_is_separate(tmp_path):
    demo = create_app(str(tmp_path / "demo"), demo=True)
    seed_if_empty(demo)
    real = create_app(str(tmp_path / "real")).test_client()
    assert real.get("/api/accounts").json == []
    assert real.get("/api/meta").json["demo"] is False
    assert demo.test_client().get("/api/meta").json["demo"] is True

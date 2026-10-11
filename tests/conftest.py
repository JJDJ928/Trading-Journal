import io
import struct
import zlib

import pytest

from rinse_tracker import create_app


def make_png(width=4, height=4):
    raw = b"".join(b"\x00" + b"\x10\x20\x30" * width for _ in range(height))

    def chunk(kind, data):
        return (struct.pack(">I", len(data)) + kind + data
                + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


@pytest.fixture
def data_dir(tmp_path):
    return tmp_path / "data"


@pytest.fixture
def app(data_dir):
    return create_app(str(data_dir))


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def png():
    return lambda name="shot.png": (io.BytesIO(make_png()), name)


def new_account(client, **overrides):
    body = {"firm": "Apex", "size": "50,000", "type": "evaluation", "cost": "167",
            "purchase_date": "2026-01-05"}
    body.update(overrides)
    resp = client.post("/api/accounts", json=body)
    assert resp.status_code == 201, resp.json
    return resp.json


def funded_account(client, cost=0):
    ev = new_account(client)
    client.put(f"/api/accounts/{ev['id']}", json={"status": "passed", "pass_date": "2026-01-20"})
    resp = client.post(f"/api/accounts/{ev['id']}/fund", json={"cost": cost})
    assert resp.status_code == 201, resp.json
    return resp.json

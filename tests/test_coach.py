import anthropic
import httpx2
import pytest

from rinse_tracker import create_app
from conftest import new_account
from test_trades import post_trade


class Block(dict):
    def to_dict(self):
        return dict(self)


class FakeResponse:
    def __init__(self, text, stop_reason="end_turn"):
        self.stop_reason = stop_reason
        self.content = [Block(type="thinking", thinking="", signature="sig"),
                        Block(type="text", text=text)]


class FakeClient:
    def __init__(self):
        self.calls = []
        self.reply = "Good patience on the entry."
        self.error = None
        self.beta = self
        self.messages = self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            err, self.error = self.error, None
            raise err
        return FakeResponse(self.reply)


@pytest.fixture
def fake():
    return FakeClient()


@pytest.fixture
def client(data_dir, fake):
    app = create_app(str(data_dir))
    app.config["COACH_CLIENT_FACTORY"] = lambda: fake
    app.config["OLLAMA_OPENER"] = FakeOllama()
    client = app.test_client()
    client.put("/api/coach/settings", json={"provider": "claude"})
    return client


def test_review_trade_sends_context_and_screenshots(client, fake, png):
    acct = new_account(client)
    trade = post_trade(client, acct["id"], files=[png("a.png"), png("b.png")],
                       summary="Faded the open").json
    resp = client.post("/api/coach/threads", json={"trade_id": trade["id"]})
    assert resp.status_code == 201, resp.json
    thread = resp.json
    assert [m["role"] for m in thread["messages"]] == ["user", "assistant"]
    assert thread["messages"][1]["text"] == "Good patience on the entry."

    call = fake.calls[0]
    assert call["model"] == "claude-opus-5-5"
    assert call["fallbacks"] == "default"
    content = call["messages"][0]["content"]
    images = [b for b in content if b["type"] == "image"]
    assert len(images) == 2 and images[0]["source"]["type"] == "base64"
    text = " ".join(b.get("text", "") for b in content)
    assert "Faded the open" in text and "TRADE TO REVIEW" in text
    assert "Jordi" in call["system"]


def test_follow_up_replays_history_unchanged(client, fake):
    new_account(client)
    thread = client.post("/api/coach/threads", json={"message": "How am I doing?"}).json
    first_call = fake.calls[0]["messages"]
    fake.reply = "Second answer"
    resp = client.post(f"/api/coach/threads/{thread['id']}/messages", json={"message": "And risk?"})
    assert resp.status_code == 200
    sent = fake.calls[1]["messages"]
    assert sent[0] == first_call[0]                       # frozen first turn
    assert sent[1]["content"][0]["type"] == "thinking"    # thinking blocks replayed as returned
    assert sent[2] == {"role": "user", "content": [{"type": "text", "text": "And risk?"}]}
    assert [m["text"] for m in resp.json["messages"]][-1] == "Second answer"


def test_failed_call_saves_nothing(client, fake):
    thread = client.post("/api/coach/threads", json={}).json
    req = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    fake.error = anthropic.APIConnectionError(request=req)
    resp = client.post(f"/api/coach/threads/{thread['id']}/messages", json={"message": "hi"})
    assert resp.status_code == 502 and "internet" in resp.json["error"]
    assert len(client.get(f"/api/coach/threads/{thread['id']}").json["messages"]) == 2


def test_refusal_is_reported(client, fake):
    fake.create = lambda **kw: FakeResponse("", stop_reason="refusal")
    resp = client.post("/api/coach/threads", json={})
    assert resp.status_code == 502
    assert client.get("/api/coach/threads").json == []


def test_validation_and_delete(client, fake):
    assert client.post("/api/coach/threads", json={"trade_id": 999}).status_code == 404
    thread = client.post("/api/coach/threads", json={}).json
    assert client.post(f"/api/coach/threads/{thread['id']}/messages", json={}).status_code == 400
    assert client.delete(f"/api/coach/threads/{thread['id']}").status_code == 200
    assert client.get("/api/coach/threads").json == []


class FakeOllama:
    def __init__(self, models=("gemma3:4b",), running=True):
        self.models, self.running, self.calls = list(models), running, []
        self.reply = "Local coach says: patience paid off."

    def __call__(self, path, payload):
        if not self.running:
            raise ConnectionError("refused")
        if path == "/api/tags":
            return {"models": [{"name": m} for m in self.models]}
        if path == "/api/chat":
            self.calls.append(payload)
            if payload["model"] not in self.models:
                from rinse_tracker.coach_local import LocalError
                raise LocalError(f"model '{payload['model']}' not found")
            return {"message": {"role": "assistant", "content": "<think>hmm</think>" + self.reply}}
        raise AssertionError(path)


@pytest.fixture
def local_client(data_dir):
    app = create_app(str(data_dir))
    ollama = FakeOllama()
    app.config["OLLAMA_OPENER"] = ollama
    return app.test_client(), ollama


def test_local_coach_is_default_and_reviews_with_images(local_client, png):
    client, ollama = local_client
    st = client.get("/api/coach/status").json
    assert st["provider"] == "local" and st["ready"] is True
    acct = new_account(client)
    trade = post_trade(client, acct["id"], files=[png("a.png")], summary="Waited for the retest").json
    thread = client.post("/api/coach/threads", json={"trade_id": trade["id"]}).json
    assert thread["messages"][-1]["text"] == "Local coach says: patience paid off."   # <think> removed
    sent = ollama.calls[0]["messages"]
    assert sent[0]["role"] == "system" and "Jordi" in sent[0]["content"]
    assert "Waited for the retest" in sent[1]["content"] and len(sent[1]["images"]) == 1
    client.post(f"/api/coach/threads/{thread['id']}/messages", json={"message": "And my stop?"})
    follow = ollama.calls[1]["messages"]
    assert [m["role"] for m in follow] == ["system", "user", "assistant", "user"]
    assert follow[2]["content"] == "Local coach says: patience paid off."


def test_local_coach_not_running_or_model_missing(local_client):
    client, ollama = local_client
    ollama.running = False
    st = client.get("/api/coach/status").json
    assert st["ready"] is False and st["local"]["running"] is False
    resp = client.post("/api/coach/threads", json={})
    assert resp.status_code == 502 and "Ollama" in resp.json["error"]
    ollama.running, ollama.models = True, []
    assert client.get("/api/coach/status").json["local"]["installed"] is False
    resp = client.post("/api/coach/threads", json={})
    assert resp.status_code == 502 and "isn't downloaded" in resp.json["error"]
    assert client.get("/api/coach/threads").json == []


def test_coach_settings_validation(local_client):
    client, _ = local_client
    assert client.put("/api/coach/settings", json={"provider": "gpt"}).status_code == 400
    assert client.put("/api/coach/settings", json={"local_model": "bad model!"}).status_code == 400
    st = client.put("/api/coach/settings", json={"local_model": "gemma3:12b"}).json
    assert st["local"]["model"] == "gemma3:12b" and st["local"]["installed"] is False


def test_api_key_saved_outside_backup(client, data_dir, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert client.get("/api/coach/status").json["claude"]["configured"] is False
    assert client.get("/api/coach/status").json["ready"] is False
    assert client.post("/api/coach/key", json={"api_key": "nope"}).status_code == 400
    assert client.post("/api/coach/key", json={"api_key": "sk-ant-test"}).status_code == 200
    assert client.get("/api/coach/status").json["claude"]["source"] == "app"
    assert client.get("/api/coach/status").json["ready"] is True
    import io, zipfile
    names = zipfile.ZipFile(io.BytesIO(client.get("/api/backup").data)).namelist()
    assert not any("api_key" in n for n in names)
    client.delete("/api/coach/key")
    assert client.get("/api/coach/status").json["claude"]["configured"] is False

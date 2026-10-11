"""Free local coach: an AI model running on your own computer through Ollama.

Nothing leaves your computer and there is no cost. Requires the Ollama app
(https://ollama.com/download) to be installed and running; the coach model
itself is downloaded from inside Rinse Tracker (see start_pull).
"""
import json
import re
import threading
import urllib.error
import urllib.request

DEFAULT_URL = "http://127.0.0.1:11434"
DEFAULT_MODEL = "gemma3:4b"     # ~3.3 GB, reads chart screenshots, runs on most laptops
CONTEXT_TOKENS = 16384          # room for the journal snapshot plus a conversation
CHAT_TIMEOUT = 600              # local models can be slow on older machines

_pulls = {}                     # model -> {"status", "completed", "total", "error", "done"}
_pulls_lock = threading.Lock()


class LocalError(Exception):
    pass


def _request(base_url, path, payload=None, timeout=5, opener=None):
    """POST (with payload) or GET a JSON endpoint on the Ollama server."""
    if opener:  # tests inject a fake server here
        return opener(path, payload)
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(base_url + path, data=data,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as err:
        try:
            message = json.loads(err.read()).get("error", "")
        except ValueError:
            message = ""
        raise LocalError(message or f"Ollama returned an error ({err.code}).")
    except (urllib.error.URLError, ConnectionError, TimeoutError) as err:
        raise ConnectionError(str(err))


def status(base_url, model, opener=None):
    try:
        tags = _request(base_url, "/api/tags", timeout=2, opener=opener)
        running = True
        installed = sorted(m.get("name", "") for m in tags.get("models", []))
    except (ConnectionError, LocalError):
        running, installed = False, []
    has_model = any(_same_model(name, model) for name in installed)
    with _pulls_lock:
        pull = dict(_pulls[model]) if model in _pulls else None
    return {"model": model, "running": running, "installed": has_model,
            "installed_models": installed, "pull": pull}


def _same_model(installed_name, wanted):
    # "gemma3" and "gemma3:latest" are the same model.
    norm = lambda n: n if ":" in n else f"{n}:latest"
    return norm(installed_name) == norm(wanted)


def start_pull(base_url, model):
    """Download a model in the background; progress is reported by status()."""
    with _pulls_lock:
        current = _pulls.get(model)
        if current and not current["done"]:
            return
        _pulls[model] = {"status": "starting", "completed": 0, "total": 0, "error": None, "done": False}

    def run():
        req = urllib.request.Request(base_url + "/api/pull",
                                     data=json.dumps({"model": model, "stream": True}).encode(),
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                for line in resp:
                    if not line.strip():
                        continue
                    event = json.loads(line)
                    with _pulls_lock:
                        state = _pulls[model]
                        if event.get("error"):
                            state["error"] = event["error"]
                        state["status"] = event.get("status", state["status"])
                        if event.get("total"):
                            state["total"], state["completed"] = event["total"], event.get("completed", 0)
            error = None
        except Exception as err:  # noqa: BLE001 - report any failure to the page
            error = f"Download failed: {err}"
        with _pulls_lock:
            state = _pulls[model]
            state["error"] = state["error"] or error
            state["done"] = True

    threading.Thread(target=run, daemon=True).start()


def chat(base_url, model, system, messages, opener=None):
    """messages: [{"role", "text", "images": [base64, ...]}]. Returns the reply text."""
    payload = {
        "model": model,
        "stream": False,
        "keep_alive": "15m",
        "options": {"num_ctx": CONTEXT_TOKENS},
        "messages": [{"role": "system", "content": system}] + [
            {"role": m["role"], "content": m["text"], **({"images": m["images"]} if m.get("images") else {})}
            for m in messages
        ],
    }
    try:
        try:
            result = _request(base_url, "/api/chat", payload, timeout=CHAT_TIMEOUT, opener=opener)
        except LocalError as err:
            if "image" not in str(err).lower():
                raise
            # This model can't read images: ask again with the screenshots left out.
            for m in payload["messages"]:
                m.pop("images", None)
            result = _request(base_url, "/api/chat", payload, timeout=CHAT_TIMEOUT, opener=opener)
    except ConnectionError:
        raise LocalError("The local AI isn't running. Open the Ollama app, then try again.")
    except LocalError as err:
        if "not found" in str(err).lower():
            raise LocalError(f"The coach model ({model}) isn't downloaded yet. Download it on the Coach page.")
        raise
    text = (result.get("message") or {}).get("content", "")
    # Some local models wrap their reasoning in <think> tags; keep only the answer.
    return re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()

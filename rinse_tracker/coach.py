"""AI trading coach.

Two engines, chosen on the Coach page (stored in <data dir>/coach_settings.json):
  * "local" (default): a free AI model running on this computer through Ollama
    (coach_local.py). Nothing leaves the computer.
  * "claude": Claude through the Anthropic API, using your API key. The trade
    data in a conversation (and a reviewed trade's screenshots) is sent to the
    Anthropic API; usage is billed to your Anthropic account.

Conversations are append-only. The first user message freezes a snapshot of
your stats and recent trades, and every message is stored exactly as it was
sent or returned (including the model's thinking blocks), so each new request
replays an unchanged history. That keeps the model's earlier reasoning usable
and the prompt cache warm.
"""
import base64
import json
import os

import anthropic
from flask import Blueprint, current_app, jsonify, request

from . import accounts as accounts_mod
from . import coach_local
from .db import get_db
from .stats import compute_summary
from .validation import Form, NotFound

bp = Blueprint("coach", __name__)

MODEL = "claude-opus-5-5"
MAX_TOKENS = 16000
MAX_IMAGES = 8
MAX_IMAGE_BYTES = 5 * 1024 * 1024  # API limit for a base64 image
RECENT_TRADES = 40
KEY_FILE = "anthropic_api_key"     # in the data folder; never included in backups
SETTINGS_FILE = "coach_settings.json"
PROVIDERS = ("local", "claude")

SYSTEM_PROMPT = """You are a personal trading coach for {name}, who trades prop-firm accounts \
using a "rinse" system: buying evaluations, passing them, trading the funded accounts and \
requesting payouts. You review {name}'s own journaled trades with them.

How to coach:
- Ground everything in the journal data and screenshots you are given. If something isn't \
in the data, say so rather than guessing, and ask about it.
- Focus on process and execution: entries, exits, patience, following the plan, risk per \
trade, and behaviour patterns (revenge trading, overtrading, moving stops, cutting winners).
- Keep prop-firm rules in mind: daily loss limits, trailing drawdowns and consistency rules \
are what end accounts, so protecting the account matters more than any single trade.
- When looking at a chart screenshot, describe what you can actually see before drawing \
conclusions.
- Be direct and specific, like a coach who wants them to improve. Point out what went well \
as well as what didn't. End a review with one or two concrete things to work on.
- Keep replies conversational and reasonably short; use short lists when they help.
- Money "earned" on an account is not cash. Only paid payouts are real money received.
- You are not a financial adviser and don't give signals or tell them what to trade next."""


# ---------------------------------------------------------------- settings

def load_settings():
    settings = {"provider": "local", "local_model": coach_local.DEFAULT_MODEL}
    try:
        with open(os.path.join(current_app.config["DATA_DIR"], SETTINGS_FILE)) as fh:
            saved = json.load(fh)
        if saved.get("provider") in PROVIDERS:
            settings["provider"] = saved["provider"]
        if isinstance(saved.get("local_model"), str) and saved["local_model"].strip():
            settings["local_model"] = saved["local_model"].strip()
    except (FileNotFoundError, ValueError):
        pass
    return settings


def save_settings(settings):
    with open(os.path.join(current_app.config["DATA_DIR"], SETTINGS_FILE), "w") as fh:
        json.dump(settings, fh, indent=2)


def _ollama_url():
    return current_app.config.get("OLLAMA_URL", coach_local.DEFAULT_URL)


def _ollama_opener():
    return current_app.config.get("OLLAMA_OPENER")  # tests inject a fake Ollama here


def _call(messages):
    """Send the conversation to the chosen engine; return assistant content blocks."""
    if load_settings()["provider"] == "claude":
        return _call_claude(messages)
    return _call_local(messages)


def _system_prompt():
    return SYSTEM_PROMPT.format(name=current_app.config.get("USER_NAME", "the trader"))


def _call_local(messages):
    simple = []
    for m in messages:
        blocks = m["content"]
        simple.append({
            "role": m["role"],
            "text": "\n\n".join(b["text"] for b in blocks if b.get("type") == "text" and b.get("text")),
            "images": [b["source"]["data"] for b in blocks if b.get("type") == "image" and "source" in b]
            if m["role"] == "user" else [],
        })
    try:
        reply = coach_local.chat(_ollama_url(), load_settings()["local_model"], _system_prompt(),
                                 simple, opener=_ollama_opener())
    except coach_local.LocalError as err:
        raise CoachError(str(err))
    if not reply:
        raise CoachError("The coach returned an empty reply. Try again.")
    return [{"type": "text", "text": reply}]


# ---------------------------------------------------------------- claude

def _key_path():
    return os.path.join(current_app.config["DATA_DIR"], KEY_FILE)


def _saved_key():
    try:
        with open(_key_path()) as fh:
            return fh.read().strip() or None
    except FileNotFoundError:
        return None


def key_source():
    if _saved_key():
        return "app"
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "environment"
    return None


def make_client():
    factory = current_app.config.get("COACH_CLIENT_FACTORY")
    if factory:  # tests inject a fake client here
        return factory()
    key = _saved_key()
    return anthropic.Anthropic(api_key=key) if key else anthropic.Anthropic()


def _call_claude(messages):
    """Send the conversation to Claude and return the assistant content blocks."""
    client = make_client()
    system = _system_prompt()
    params = dict(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=system,
        output_config={"effort": "medium"},
        # If a safety classifier declines, retry on Anthropic's recommended fallback model.
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
    )
    try:
        try:
            response = client.beta.messages.create(messages=messages, **params)
        except anthropic.BadRequestError as err:
            if "signature" not in str(err):
                raise
            # Earlier thinking no longer matches the history (e.g. a reviewed
            # screenshot was deleted). Retry once without the old reasoning.
            response = client.beta.messages.create(messages=_strip_thinking(messages), **params)
    except anthropic.AuthenticationError:
        raise CoachError("Your Anthropic API key was rejected. Check it in the coach settings.")
    except anthropic.PermissionDeniedError:
        raise CoachError("This API key doesn't have access to the coach model.")
    except anthropic.RateLimitError:
        raise CoachError("The coach is rate limited right now. Wait a minute and try again.")
    except anthropic.BadRequestError as err:
        raise CoachError(f"The coach request was rejected: {err.message}")
    except anthropic.APIStatusError as err:
        raise CoachError(f"The Anthropic API returned an error ({err.status_code}). Try again shortly.")
    except anthropic.APIConnectionError:
        raise CoachError("Can't reach the Anthropic API. Check your internet connection.")

    if response.stop_reason == "refusal":
        raise CoachError("The coach declined to answer that. Try rephrasing your question.")
    blocks = [b.to_dict() if hasattr(b, "to_dict") else dict(b) for b in response.content]
    if not _text_of(blocks):
        raise CoachError("The coach returned an empty reply. Try again.")
    return blocks


def _strip_thinking(messages):
    out = []
    for m in messages:
        content = m["content"]
        if m["role"] == "assistant" and isinstance(content, list):
            content = [b for b in content if b.get("type") not in ("thinking", "redacted_thinking")]
        out.append({"role": m["role"], "content": content})
    return out


class CoachError(Exception):
    pass


# ---------------------------------------------------------------- context

def _money(cents):
    return "n/a" if cents is None else f"${cents / 100:,.2f}"


def _trade_line(t):
    acct = f"{t['firm']} {_money(t['size_cents']).replace('.00', '')}"
    if t["account_ref"]:
        acct += f" ({t['account_ref']})"
    parts = [t["traded_at"].replace("T", " "), acct, t["instrument"] or "?", t["result"].upper()]
    if t["pnl_cents"] is not None:
        parts.append(_money(t["pnl_cents"]))
    line = " | ".join(parts)
    if t["summary"]:
        line += f"\n  Summary: {t['summary']}"
    if t["notes"]:
        line += f"\n  Notes: {t['notes']}"
    return line


TRADE_SQL = """SELECT t.*, a.firm, a.account_ref, a.size_cents, a.type AS account_type,
                      a.status AS account_status
               FROM trades t JOIN accounts a ON a.id = t.account_id"""


def journal_snapshot(conn):
    """A frozen text snapshot of the journal for the start of a conversation."""
    s = compute_summary(conn)
    rate = "n/a" if s["pass_rate"] is None else f"{s['pass_rate'] * 100:.0f}%"
    lines = [
        "RINSE SYSTEM SUMMARY",
        f"Evaluations: {s['evaluations_purchased']} purchased, {s['evaluations_active']} active, "
        f"{s['evaluations_passed']} passed, {s['evaluations_failed']} failed (pass rate {rate})",
        f"Funded accounts: {s['funded_accounts']} ({s['funded_active']} active, "
        f"{s['funded_failed']} breached)",
        f"Fees spent: ${s['total_fees']:,.2f} | Payouts received: ${s['payouts_received']:,.2f} "
        f"| Net cash flow: ${s['net_cash_flow']:,.2f}",
        f"Trades logged: {s['trades']} ({s['wins']} W / {s['losses']} L / {s['breakevens']} BE), "
        f"recorded P&L ${s['trade_pnl_recorded']:,.2f}",
        "",
        "ACCOUNTS",
    ]
    for a in conn.execute(accounts_mod.LIST_SQL + " ORDER BY a.purchase_date DESC LIMIT 30"):
        lines.append(f"- {a['firm']} {_money(a['size_cents']).replace('.00', '')}"
                     f"{' (' + a['account_ref'] + ')' if a['account_ref'] else ''}: {a['type']}, "
                     f"status {a['status']}, cost {_money(a['cost_cents'])}, "
                     f"{a['trade_count']} trades, P&L {_money(a['pnl_cents'])}")
    trades = conn.execute(TRADE_SQL + " ORDER BY t.traded_at DESC, t.id DESC LIMIT ?",
                          (RECENT_TRADES,)).fetchall()
    lines += ["", f"RECENT TRADES (newest first, up to {RECENT_TRADES})"]
    lines += [_trade_line(t) for t in trades] or ["(no trades logged yet)"]
    return "\n".join(lines)


def _trade_blocks(conn, trade_id):
    """Text + screenshot references for one trade under review."""
    t = conn.execute(TRADE_SQL + " WHERE t.id = ?", (trade_id,)).fetchone()
    if t is None:
        raise NotFound("Trade not found.")
    shots = conn.execute("SELECT filename, content_type, size_bytes FROM screenshots "
                         "WHERE trade_id = ? ORDER BY id", (trade_id,)).fetchall()
    text = ("TRADE TO REVIEW\n" + _trade_line(t)
            + f"\nAccount type: {t['account_type']}, account status: {t['account_status']}"
            + f"\nScreenshots attached: {min(len(shots), MAX_IMAGES)}")
    blocks = [{"type": "text", "text": text}]
    for s in shots[:MAX_IMAGES]:
        if (s["size_bytes"] or 0) > MAX_IMAGE_BYTES:
            blocks.append({"type": "text", "text": "(One screenshot was too large to send.)"})
        else:
            # Stored as a reference; the bytes are read from disk at send time.
            blocks.append({"type": "image", "screenshot": s["filename"],
                           "media_type": s["content_type"]})
    return t, blocks


def _resolve(content):
    """Turn stored blocks into API blocks (screenshot references -> base64 images)."""
    out = []
    for b in content:
        if b.get("type") == "image" and "screenshot" in b:
            path = os.path.join(current_app.config["UPLOAD_DIR"], b["screenshot"])
            try:
                with open(path, "rb") as fh:
                    data = base64.standard_b64encode(fh.read()).decode()
                out.append({"type": "image", "source": {"type": "base64",
                                                        "media_type": b["media_type"], "data": data}})
            except FileNotFoundError:
                out.append({"type": "text", "text": "(This screenshot has since been deleted.)"})
        else:
            out.append(b)
    return out


def _text_of(blocks):
    return "\n\n".join(b["text"] for b in blocks if b.get("type") == "text" and b.get("text")).strip()


# ---------------------------------------------------------------- threads

def _history(conn, thread_id):
    rows = conn.execute("SELECT role, content FROM coach_messages WHERE thread_id = ? ORDER BY id",
                        (thread_id,))
    return [{"role": r["role"], "content": _resolve(json.loads(r["content"]))} for r in rows]


def _save_turn(conn, thread_id, user_blocks, display, assistant_blocks):
    conn.execute("INSERT INTO coach_messages (thread_id, role, content, display_text) "
                 "VALUES (?, 'user', ?, ?)", (thread_id, json.dumps(user_blocks), display))
    conn.execute("INSERT INTO coach_messages (thread_id, role, content, display_text) "
                 "VALUES (?, 'assistant', ?, ?)",
                 (thread_id, json.dumps(assistant_blocks), _text_of(assistant_blocks)))
    conn.execute("UPDATE coach_threads SET updated_at = datetime('now') WHERE id = ?", (thread_id,))


def thread_detail(conn, thread_id):
    t = conn.execute("SELECT * FROM coach_threads WHERE id = ?", (thread_id,)).fetchone()
    if t is None:
        raise NotFound("Conversation not found.")
    msgs = conn.execute("SELECT id, role, display_text, created_at FROM coach_messages "
                        "WHERE thread_id = ? ORDER BY id", (thread_id,))
    return {**dict(t), "messages": [{"id": m["id"], "role": m["role"], "text": m["display_text"],
                                     "created_at": m["created_at"]} for m in msgs]}


DEFAULT_REVIEW = "Review this trade with me. What did I do well, and what should I work on?"
DEFAULT_CHAT = "Look over my journal and tell me what patterns you see in my trading."


@bp.post("/api/coach/threads")
def start_thread():
    """Start a conversation: a review of one trade, or a general journal review."""
    conn = get_db()
    form = Form(request.get_json(silent=True))
    trade_id = form.integer("trade_id")
    message = form.text("message", max_len=8000)
    form.check()

    blocks = [{"type": "text", "text": "Here is my trading journal as of now.\n\n"
                                       + journal_snapshot(conn)}]
    if trade_id is not None:
        trade, trade_blocks = _trade_blocks(conn, trade_id)
        blocks += trade_blocks
        title = f"Review: {trade['instrument'] or 'trade'} {trade['result']} " \
                f"({trade['traded_at'][:10]})"
    else:
        title = (message or "Journal review")[:60]
    display = message or (DEFAULT_REVIEW if trade_id is not None else DEFAULT_CHAT)
    blocks.append({"type": "text", "text": display})

    reply = _call([{"role": "user", "content": _resolve(blocks)}])
    cur = conn.execute("INSERT INTO coach_threads (title, trade_id) VALUES (?, ?)", (title, trade_id))
    _save_turn(conn, cur.lastrowid, blocks, display, reply)
    conn.commit()
    return jsonify(thread_detail(conn, cur.lastrowid)), 201


@bp.post("/api/coach/threads/<int:thread_id>/messages")
def send_message(thread_id):
    conn = get_db()
    thread_detail(conn, thread_id)  # 404 if missing
    form = Form(request.get_json(silent=True))
    message = form.text("message", required=True, max_len=8000, label="Message")
    form.check()
    blocks = [{"type": "text", "text": message}]
    # Nothing is saved unless the API call succeeds, so a failed send leaves
    # the stored conversation exactly as it was.
    reply = _call(_history(conn, thread_id) + [{"role": "user", "content": blocks}])
    _save_turn(conn, thread_id, blocks, message, reply)
    conn.commit()
    return jsonify(thread_detail(conn, thread_id))


@bp.get("/api/coach/threads")
def list_threads():
    rows = get_db().execute("""
        SELECT t.*, (SELECT COUNT(*) FROM coach_messages m WHERE m.thread_id = t.id) AS message_count
        FROM coach_threads t ORDER BY t.updated_at DESC, t.id DESC""")
    return jsonify([dict(r) for r in rows])


@bp.get("/api/coach/threads/<int:thread_id>")
def get_thread(thread_id):
    return jsonify(thread_detail(get_db(), thread_id))


@bp.delete("/api/coach/threads/<int:thread_id>")
def delete_thread(thread_id):
    conn = get_db()
    thread_detail(conn, thread_id)
    conn.execute("DELETE FROM coach_threads WHERE id = ?", (thread_id,))
    conn.commit()
    return jsonify({"ok": True})


# ---------------------------------------------------------------- settings

@bp.get("/api/coach/status")
def status():
    settings = load_settings()
    local = coach_local.status(_ollama_url(), settings["local_model"], opener=_ollama_opener())
    claude = {"configured": key_source() is not None, "source": key_source(), "model": MODEL}
    ready = (local["running"] and local["installed"]) if settings["provider"] == "local" \
        else claude["configured"]
    return jsonify({"provider": settings["provider"], "ready": ready, "local": local, "claude": claude})


@bp.put("/api/coach/settings")
def put_settings():
    form = Form(request.get_json(silent=True))
    settings = load_settings()
    provider = form.choice("provider", PROVIDERS)
    model = form.text("local_model", max_len=100, label="Model")
    if model and not all(c.isalnum() or c in ".:-_/" for c in model):
        form.error("local_model", "Use a model name like gemma3:4b.")
    form.check()
    settings["provider"] = provider or settings["provider"]
    settings["local_model"] = model or settings["local_model"]
    save_settings(settings)
    return status()


@bp.post("/api/coach/local/pull")
def pull_model():
    """Start downloading the local coach model through Ollama."""
    model = load_settings()["local_model"]
    if not coach_local.status(_ollama_url(), model, opener=_ollama_opener())["running"]:
        raise CoachError("Ollama isn't running. Install it from ollama.com and open it first.")
    if not _ollama_opener():
        coach_local.start_pull(_ollama_url(), model)
    return status()


@bp.post("/api/coach/key")
def save_key():
    form = Form(request.get_json(silent=True))
    key = form.text("api_key", required=True, max_len=500, label="API key")
    if key and not key.startswith("sk-ant-"):
        form.error("api_key", "Anthropic API keys start with sk-ant-.")
    form.check()
    path = _key_path()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as fh:
        fh.write(key)
    return jsonify({"configured": True, "source": "app"})


@bp.delete("/api/coach/key")
def remove_key():
    try:
        os.remove(_key_path())
    except FileNotFoundError:
        pass
    return jsonify({"configured": key_source() is not None, "source": key_source()})


def register_errors(app):
    @app.errorhandler(CoachError)
    def on_coach_error(err):
        return jsonify({"error": str(err)}), 502


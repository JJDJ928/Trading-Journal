// AI coach: conversations with Claude about your journal and individual trades.
import { api } from "../api.js";
import { confirmDialog, esc, fmtDateTime, toast } from "../ui.js";

const SUGGESTIONS = [
  "What patterns do you see in my trading?",
  "Why do my evaluations fail, and what should I change?",
  "Review my last 10 trades and give me a focus for next week.",
  "Am I following good risk management for prop-firm rules?",
];

// Escape first, then apply a small, safe subset of Markdown.
function renderMarkdown(text) {
  const inline = (s) => s
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/(^|[^*])\*([^*\n]+)\*/g, "$1<em>$2</em>");
  const out = [];
  let list = null;
  const closeList = () => { if (list) { out.push(`</${list}>`); list = null; } };
  for (const raw of esc(text).split("\n")) {
    const line = raw.trimEnd();
    let m;
    if ((m = line.match(/^\s*[-*•]\s+(.*)$/))) {
      if (list !== "ul") { closeList(); out.push("<ul>"); list = "ul"; }
      out.push(`<li>${inline(m[1])}</li>`);
    } else if ((m = line.match(/^\s*\d+[.)]\s+(.*)$/))) {
      if (list !== "ol") { closeList(); out.push("<ol>"); list = "ol"; }
      out.push(`<li>${inline(m[1])}</li>`);
    } else if ((m = line.match(/^#{1,6}\s+(.*)$/))) {
      closeList(); out.push(`<h4>${inline(m[1])}</h4>`);
    } else if (!line.trim()) {
      closeList();
    } else {
      closeList(); out.push(`<p>${inline(line)}</p>`);
    }
  }
  closeList();
  return out.join("");
}

const bubble = (m) => m.role === "user"
  ? `<div class="msg user">${esc(m.text)}</div>`
  : `<div class="msg assistant"><div class="who">Coach</div>${renderMarkdown(m.text || "")}</div>`;

/** Start a coach review of one trade (called from trade cards). */
export function reviewTrade(tradeId) {
  location.hash = `#/coach/review/${tradeId}`;
}

export async function render(el, threadId = null, reviewTradeId = null) {
  const [status, threads] = await Promise.all([api.get("/api/coach/status"), api.get("/api/coach/threads")]);
  const thread = threadId ? await api.get(`/api/coach/threads/${threadId}`) : null;

  el.innerHTML = `
    <div class="page-head"><h1>Coach</h1>
      <div class="actions">${status.configured ? `<a class="btn" href="#/coach">+ New conversation</a>` : ""}
        <button class="btn ghost sm" data-act="settings">API key</button></div></div>
    ${status.configured ? `
      <div class="coach">
        <aside class="panel" style="padding:10px">
          <div class="thread-list">${threads.length ? threads.map((t) => `
            <a href="#/coach/${t.id}" class="${String(t.id) === String(threadId) ? "active" : ""}">${esc(t.title)}
              <small>${esc(fmtDateTime(t.updated_at.replace(" ", "T") + "Z"))}</small></a>`).join("")
            : `<p class="muted small" style="margin:6px">No conversations yet.</p>`}</div>
        </aside>
        <section>
          <div class="chat">${thread ? thread.messages.map(bubble).join("") : intro()}</div>
          <form class="composer">
            <textarea name="message" rows="2" placeholder="${thread ? "Reply to your coach…" : "Ask your coach anything about your trading…"}"></textarea>
            <button class="btn primary" type="submit">Send</button>
          </form>
          <p class="privacy">The coach runs on Claude. Your journal snapshot and the screenshots of a reviewed trade are sent to the Anthropic API; nothing else leaves your computer. Ctrl+Enter to send.</p>
        </section>
      </div>` : setupCard()}`;

  el.querySelector("[data-act=settings]").addEventListener("click", () => openKeySettings(status));
  if (!status.configured) return bindSetup(el);

  const chat = el.querySelector(".chat"), form = el.querySelector(".composer"), box = form.elements.message;
  const scrollDown = () => chat.lastElementChild?.scrollIntoView({ block: "end" });

  async function send(text, { tradeId = null } = {}) {
    form.querySelector("button").disabled = box.disabled = true;
    if (!thread) chat.innerHTML = "";
    if (text) chat.insertAdjacentHTML("beforeend", bubble({ role: "user", text }));
    chat.insertAdjacentHTML("beforeend", `<div class="msg assistant pending"><div class="who">Coach</div>${tradeId ? "Looking at your trade and screenshots…" : "Thinking…"}</div>`);
    scrollDown();
    try {
      const result = thread
        ? await api.post(`/api/coach/threads/${thread.id}/messages`, { message: text })
        : await api.post("/api/coach/threads", { message: text || null, trade_id: tradeId });
      // replaceState avoids re-running a review if the user goes back.
      history.replaceState(null, "", `#/coach/${result.id}`);
      window.dispatchEvent(new Event("hashchange"));
    } catch (err) {
      toast(err.message, "error");
      chat.querySelector(".pending")?.remove();
      if (!thread) chat.innerHTML = intro();
      box.value = text || "";
      form.querySelector("button").disabled = box.disabled = false;
    }
  }

  form.addEventListener("submit", (e) => { e.preventDefault(); const t = box.value.trim(); if (t) send(t); });
  box.addEventListener("keydown", (e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); form.requestSubmit(); } });
  chat.addEventListener("click", (e) => {
    const s = e.target.closest("[data-suggest]");
    if (s) send(s.dataset.suggest);
  });
  if (thread) {
    chat.insertAdjacentHTML("afterend", `<div style="margin-top:8px;text-align:right"><button class="btn ghost sm" data-act="delete">Delete conversation</button></div>`);
    el.querySelector("[data-act=delete]").addEventListener("click", async () => {
      if (!await confirmDialog({ title: "Delete conversation?", message: `Delete "${esc(thread.title)}"? Your trades are not affected.` })) return;
      await api.del(`/api/coach/threads/${thread.id}`);
      location.hash = "#/coach";
    });
    scrollDown();
  }
  if (reviewTradeId) send(null, { tradeId: Number(reviewTradeId) });
  else box.focus();
}

function intro() {
  return `<div class="panel">
    <h2>Your trading coach</h2>
    <p class="muted" style="margin-top:0">Ask about your journal, or open any trade and press <strong>Review with coach</strong>
      to go through it together, screenshots included. Each conversation starts from a snapshot of your stats and recent trades.</p>
    <div style="display:flex;flex-wrap:wrap;gap:8px">${SUGGESTIONS.map((s) => `<button class="btn sm" data-suggest="${esc(s)}">${esc(s)}</button>`).join("")}</div>
  </div>`;
}

function setupCard() {
  return `<div class="panel" style="max-width:640px">
    <h2>Set up your coach</h2>
    <p class="muted">The coach uses Claude through the Anthropic API, which needs an API key (usage is billed to your Anthropic account).</p>
    <ol class="muted" style="padding-left:18px">
      <li>Create a key at <a href="https://console.anthropic.com/settings/keys" target="_blank" rel="noopener">console.anthropic.com</a>.</li>
      <li>Paste it below. It's stored only on this computer, in your data folder, and is never included in backups.</li>
    </ol>
    <form data-setup style="display:flex;gap:8px;flex-wrap:wrap">
      <input name="api_key" type="password" placeholder="sk-ant-…" autocomplete="off" style="flex:1;min-width:240px">
      <button class="btn primary" type="submit">Save key</button>
    </form>
    <p class="note">Or start the app with the ANTHROPIC_API_KEY environment variable set.</p>
  </div>`;
}

function bindSetup(el) {
  el.querySelector("[data-setup]").addEventListener("submit", async (e) => {
    e.preventDefault();
    try {
      await api.post("/api/coach/key", { api_key: e.target.elements.api_key.value.trim() });
      toast("API key saved. Your coach is ready.");
      window.dispatchEvent(new Event("data-changed"));
    } catch (err) { toast(err.fields?.api_key || err.message, "error"); }
  });
}

async function openKeySettings(status) {
  if (status.source !== "app") {
    toast(status.source === "environment" ? "Using the ANTHROPIC_API_KEY environment variable." : "Paste a key on this page to set up the coach.");
    return;
  }
  if (!await confirmDialog({ title: "Remove saved API key?", message: "The coach will stop working until you add a key again. Conversations are kept.", confirmLabel: "Remove key" })) return;
  await api.del("/api/coach/key");
  toast("API key removed");
  window.dispatchEvent(new Event("data-changed"));
}

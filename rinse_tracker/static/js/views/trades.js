import { api, qs } from "../api.js";
import { openTradeForm } from "../forms.js";
import { accountOptions, debounce, esc, money, moneyClass } from "../ui.js";
import { bindTradeCards, tradeCards } from "./tradeList.js";

const filters = { account_id: "", result: "", q: "" };

export async function render(el) {
  const accounts = await api.get("/api/accounts");
  if (filters.account_id && !accounts.some((a) => String(a.id) === filters.account_id)) filters.account_id = "";
  el.innerHTML = `
    <div class="page-head"><h1>Trade Journal</h1>
      <div class="actions"><button class="btn primary" data-act="new">+ Log trade</button></div></div>
    <div class="filters">
      <input type="search" name="q" placeholder="Search instrument, summary, notes…" value="${esc(filters.q)}">
      <select name="account_id"><option value="">All accounts</option>${accountOptions(accounts, filters.account_id)}</select>
      <select name="result"><option value="">All results</option>
        ${["win", "loss", "breakeven"].map((r) => `<option value="${r}" ${filters.result === r ? "selected" : ""}>${r[0].toUpperCase() + r.slice(1)}</option>`).join("")}</select>
    </div>
    <div data-results><div class="loading">Loading…</div></div>
    <p class="note">Tip: drag screenshots anywhere onto this page to start a new trade.</p>`;
  const results = el.querySelector("[data-results]");

  async function load() {
    const trades = await api.get(`/api/trades${qs(filters)}`);
    if (!trades.length) {
      const filtered = filters.q || filters.account_id || filters.result;
      results.innerHTML = filtered ? `<div class="empty"><p>No trades match these filters.</p></div>`
        : `<div class="empty"><p>No trades yet. Log a trade and drop in your chart screenshots.</p>
           <button class="btn primary" data-act="new">+ Log trade</button></div>`;
      return;
    }
    const w = trades.filter((t) => t.result === "win").length, l = trades.filter((t) => t.result === "loss").length;
    const pnl = trades.reduce((s, t) => s + (t.pnl || 0), 0);
    results.innerHTML = `
      <p class="muted small">${trades.length} trade${trades.length > 1 ? "s" : ""} · ${w}W ${l}L ${trades.length - w - l}BE ·
        recorded P&amp;L <span class="num ${moneyClass(pnl)}">${money(pnl, { sign: true })}</span></p>
      ${tradeCards(trades)}`;
    const list = results.querySelector(".trade-list");
    bindTradeCards(list, trades);
  }

  const reload = debounce(load, 200);
  el.querySelector(".filters").addEventListener("input", (e) => {
    filters[e.target.name] = e.target.value.trim();
    e.target.name === "q" ? reload() : load();
  });
  el.addEventListener("click", (e) => {
    if (e.target.closest("[data-act=new]")) openTradeForm({ accountId: filters.account_id || null });
  });
  await load();
}

export const dropAccount = () => filters.account_id || null;

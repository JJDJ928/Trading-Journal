import { api, qs } from "../api.js";
import {
  dataChanged, openAccountForm, openFundForm, openPayoutForm, openStatusChange, openTradeForm,
} from "../forms.js";
import {
  accountLabel, confirmDialog, debounce, esc, fmtDate, money, moneyClass, payoutBadge, sizeShort,
  STATUS_LABELS, statusBadge, toast, typeBadge,
} from "../ui.js";
import { stat } from "./dashboard.js";
import { bindTradeCards, tradeCards } from "./tradeList.js";

const filters = { q: "", status: "", type: "" };

export async function renderList(el) {
  el.innerHTML = `
    <div class="page-head"><h1>Accounts</h1>
      <div class="actions"><button class="btn primary" data-act="new">+ Add account</button></div></div>
    <div class="filters">
      <input type="search" name="q" placeholder="Search firm, account ID, notes…" value="${esc(filters.q)}">
      <select name="status"><option value="">All statuses</option>
        ${Object.entries(STATUS_LABELS).map(([k, v]) => `<option value="${k}" ${filters.status === k ? "selected" : ""}>${v}</option>`).join("")}</select>
      <select name="type"><option value="">All types</option>
        <option value="evaluation" ${filters.type === "evaluation" ? "selected" : ""}>Evaluations</option>
        <option value="funded" ${filters.type === "funded" ? "selected" : ""}>Funded</option></select>
    </div>
    <div data-results><div class="loading">Loading…</div></div>`;
  const results = el.querySelector("[data-results]");

  async function load() {
    const list = await api.get(`/api/accounts${qs(filters)}`);
    const filtered = filters.q || filters.status || filters.type;
    if (!list.length) {
      results.innerHTML = filtered
        ? `<div class="empty"><p>No accounts match these filters.</p></div>`
        : `<div class="empty"><p>No accounts yet. Add the first evaluation you purchased.</p><button class="btn primary" data-act="new">+ Add account</button></div>`;
      return;
    }
    results.innerHTML = `
      <p class="muted small">${list.length} account${list.length > 1 ? "s" : ""}</p>
      <div class="table-wrap"><table>
        <thead><tr><th>Account</th><th>Type</th><th>Status</th><th class="right">Size</th><th>Purchased</th>
          <th class="right">Cost</th><th class="right">Trades</th><th class="right">Payouts received</th><th></th></tr></thead>
        <tbody>${list.map((a) => `
          <tr class="clickable" data-href="#/accounts/${a.id}">
            <td><strong>${esc(a.firm)}</strong>${a.account_ref ? ` <span class="muted">· ${esc(a.account_ref)}</span>` : ""}
              ${a.parent_id ? `<span class="faint small"> ← from eval</span>` : ""}</td>
            <td>${typeBadge(a.type)}</td>
            <td>${statusBadge(a)}</td>
            <td class="right num">${sizeShort(a.size)}</td>
            <td class="num">${esc(fmtDate(a.purchase_date))}</td>
            <td class="right num">${money(a.cost)}</td>
            <td class="right num">${a.trade_count}</td>
            <td class="right num ${a.payouts_received ? "pos" : "faint"}">${a.type === "funded" ? money(a.payouts_received) : "—"}</td>
            <td class="right"><button class="btn sm" data-log="${a.id}">Log trade</button></td>
          </tr>`).join("")}</tbody></table></div>`;
  }

  const reload = debounce(load, 200);
  el.querySelector(".filters").addEventListener("input", (e) => {
    filters[e.target.name] = e.target.value.trim();
    e.target.name === "q" ? reload() : load();
  });
  el.addEventListener("click", (e) => {
    if (e.target.closest("[data-act=new]")) return openAccountForm();
    const log = e.target.closest("[data-log]");
    if (log) return openTradeForm({ accountId: log.dataset.log });
    const row = e.target.closest("[data-href]");
    if (row) location.hash = row.dataset.href;
  });
  await load();
}

export async function renderDetail(el, id) {
  const [a, trades, payouts] = await Promise.all([
    api.get(`/api/accounts/${id}`),
    api.get(`/api/trades?account_id=${id}`),
    api.get(`/api/payouts?account_id=${id}`),
  ]);
  const wins = trades.filter((t) => t.result === "win").length;
  const losses = trades.filter((t) => t.result === "loss").length;
  const be = trades.length - wins - losses;
  const isEval = a.type === "evaluation";

  // Next sensible steps for this account, so updating status is one click.
  const actions = [];
  if (isEval && a.status === "active") actions.push(`<button class="btn success" data-status="passed">Mark passed</button>`, `<button class="btn danger" data-status="failed">Mark failed</button>`);
  if (isEval && a.status === "passed") actions.push(`<button class="btn success" data-act="fund">Create funded account</button>`);
  if (!isEval && a.status === "funded") actions.push(`<button class="btn" data-act="payout">+ Record payout</button>`, `<button class="btn danger" data-status="failed">Mark breached</button>`, `<button class="btn" data-status="closed">Close</button>`);

  el.innerHTML = `
    <div class="crumb"><a href="#/accounts">Accounts</a> / ${esc(accountLabel(a))}</div>
    <div class="page-head">
      <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap"><h1>${esc(accountLabel(a))}</h1>${typeBadge(a.type)}${statusBadge(a)}</div>
      <div class="actions">
        <button class="btn primary" data-act="trade">+ Log trade</button>
        ${actions.join("")}
        <button class="btn" data-act="edit">Edit</button>
      </div>
    </div>

    <div class="panel">
      <div class="kv">
        <div><span>Prop firm</span><strong>${esc(a.firm)}</strong></div>
        <div><span>Account size</span><strong class="num">${money(a.size)}</strong></div>
        <div><span>${isEval ? "Evaluation cost" : "Cost / activation fee"}</span><strong class="num">${money(a.cost)}</strong></div>
        <div><span>${isEval ? "Purchased" : "Funded since"}</span><strong>${esc(fmtDate(a.purchase_date))}</strong></div>
        ${isEval ? `<div><span>Pass date</span><strong>${esc(fmtDate(a.pass_date))}</strong></div>` : ""}
        ${a.end_date ? `<div><span>${a.status === "failed" ? "Failed / breached" : "Closed"}</span><strong>${esc(fmtDate(a.end_date))}</strong></div>` : ""}
      </div>
      ${a.parent ? `<div class="linked">Funded from evaluation <a href="#/accounts/${a.parent.id}">${esc(accountLabel(a.parent))}</a> (cost ${money(a.parent.cost)}, passed ${esc(fmtDate(a.parent.pass_date))})</div>` : ""}
      ${a.child ? `<div class="linked">Became funded account <a href="#/accounts/${a.child.id}">${esc(accountLabel(a.child))}</a>: ${statusBadge(a.child)}</div>` : ""}
      ${a.notes ? `<div class="trade-notes" style="margin-top:14px">${esc(a.notes)}</div>` : ""}
    </div>

    <div class="grid cards" style="margin-top:14px">
      ${stat("Trades logged", trades.length, { sub: `${wins}W · ${losses}L · ${be}BE` })}
      ${stat("Recorded trade P&L", money(a.pnl, { sign: true }), { cls: moneyClass(a.pnl), sub: "Earned on account, not cash" })}
      ${!isEval ? stat("Payouts received", money(a.payouts_received), { cls: a.payouts_received ? "pos" : "", sub: "Paid payouts only" }) : ""}
      ${!isEval ? stat("Net for this account", money(a.payouts_received - a.cost - (a.parent?.cost || 0), { sign: true }),
        { cls: moneyClass(a.payouts_received - a.cost - (a.parent?.cost || 0)), sub: a.parent ? "Payouts − eval & activation fees" : "Payouts − cost" }) : ""}
    </div>

    <div class="section-head"><h2>Trade history</h2><span class="muted small">Newest first</span></div>
    <div data-trades>${trades.length ? tradeCards(trades, { showAccount: false })
      : `<div class="empty"><p>No trades on this account yet.</p><button class="btn primary" data-act="trade">+ Log trade</button></div>`}</div>

    ${!isEval || payouts.length ? `
      <div class="section-head"><h2>Payouts</h2>${!isEval ? `<button class="btn sm" data-act="payout">+ Record payout</button>` : ""}</div>
      ${payouts.length ? `<div class="table-wrap"><table>
        <thead><tr><th>Requested</th><th class="right">Amount requested</th><th class="right">Received</th><th>Paid on</th><th>Status</th></tr></thead>
        <tbody>${payouts.map((p) => `<tr>
          <td class="num">${esc(fmtDate(p.request_date))}</td><td class="right num">${money(p.amount_requested)}</td>
          <td class="right num ${p.status === "paid" ? "pos" : "faint"}">${p.status === "paid" ? money(p.amount_received) : "—"}</td>
          <td class="num">${p.status === "paid" ? esc(fmtDate(p.payment_date)) : "—"}</td><td>${payoutBadge(p.status)}</td></tr>`).join("")}
        </tbody></table></div>` : `<div class="empty"><p>No payouts recorded.</p></div>`}` : ""}

    <div class="section-head"><h2>Lifecycle</h2></div>
    <div class="panel"><ul class="timeline">
      <li><span class="when">${esc(a.purchase_date)}</span>${isEval ? "Evaluation purchased" : a.parent ? "Funded account started" : "Funded account purchased"} for ${money(a.cost)}</li>
      ${a.history.filter((x) => x.from_status).map((x) => `<li><span class="when">${esc(x.changed_at.slice(0, 10))}</span>
        <span>${esc(STATUS_LABELS[x.from_status])} → <strong>${esc(STATUS_LABELS[x.to_status])}</strong></span></li>`).join("")}
    </ul><p class="note">Dates are when the status was changed in the app.</p></div>

    <div style="margin-top:30px"><button class="btn danger sm" data-act="delete">Delete account…</button></div>`;

  bindTradeCards(el.querySelector("[data-trades]"), trades);
  el.addEventListener("click", async (e) => {
    const status = e.target.closest("[data-status]")?.dataset.status;
    if (status) return openStatusChange(a, status);
    const act = e.target.closest("[data-act]")?.dataset.act;
    if (act === "trade") openTradeForm({ accountId: a.id });
    else if (act === "edit") openAccountForm(a);
    else if (act === "fund") openFundForm(a);
    else if (act === "payout") openPayoutForm({ accountId: a.id });
    else if (act === "delete") deleteAccount(a);
  });
}

async function deleteAccount(a) {
  if (a.child) {
    toast("Delete the linked funded account first.", "error");
    return;
  }
  const { trades, payouts } = a.delete_impact;
  const lost = [trades && `${trades} trade${trades > 1 ? "s" : ""} (with screenshots)`, payouts && `${payouts} payout${payouts > 1 ? "s" : ""}`].filter(Boolean);
  const ok = await confirmDialog({
    title: "Delete account permanently?",
    message: `Only delete accounts created by mistake. <strong>Failed or breached accounts should be kept</strong>
      (mark them Failed / Breached instead) so your statistics stay accurate.
      ${lost.length ? `<br><br>This also deletes ${lost.join(" and ")}.` : ""}`,
    confirmLabel: "Delete permanently",
  });
  if (!ok) return;
  try {
    await api.del(`/api/accounts/${a.id}`);
    toast("Account deleted");
    location.hash = "#/accounts";
    dataChanged();
  } catch (err) { toast(err.message, "error"); }
}

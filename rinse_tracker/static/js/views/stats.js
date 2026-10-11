import { api } from "../api.js";
import { accountLabel, esc, fmtDate, money, moneyClass, pct, statusBadge, typeBadge } from "../ui.js";
import { stat } from "./dashboard.js";

let typeFilter = "";

export async function render(el) {
  const { summary: s, accounts } = await api.get("/api/stats");
  el.innerHTML = `
    <div class="page-head"><h1>Rinse Statistics</h1></div>

    <h3>Evaluations</h3>
    <div class="grid cards">
      ${stat("Purchased", s.evaluations_purchased, { sub: `${s.evaluations_active} still active` })}
      ${stat("Passed", s.evaluations_passed)}
      ${stat("Failed", s.evaluations_failed)}
      ${stat("Pass rate", pct(s.pass_rate), { feature: true,
        sub: s.evaluations_completed ? `${s.evaluations_passed} of ${s.evaluations_completed} completed evaluations` : "No completed evaluations yet" })}
    </div>

    <h3 style="margin-top:22px">Funded &amp; cash</h3>
    <div class="grid cards">
      ${stat("Funded accounts obtained", s.funded_accounts, { sub: `${s.funded_active} active · ${s.funded_failed} breached` })}
      ${stat("Evaluation fees spent", money(s.total_fees), { sub: s.activation_fees ? `${money(s.evaluation_fees)} evals + ${money(s.activation_fees)} activation` : "" })}
      ${stat("Payouts received", s.payouts_paid_count, { sub: s.payouts_pending_count ? `${s.payouts_pending_count} pending (${money(s.payouts_pending_amount)})` : "" })}
      ${stat("Payout dollars received", money(s.payouts_received), { cls: s.payouts_received ? "pos" : "" })}
      ${stat("Net cash flow after fees", money(s.net_cash_flow, { sign: true }), { cls: moneyClass(s.net_cash_flow), feature: true })}
    </div>
    <p class="note">Pass rate = passed ÷ (passed + failed). Active evaluations, and evaluations closed without passing, are not counted as failures.
      Only payouts marked Paid count as received. Recorded trade P&amp;L (<span class="num ${moneyClass(s.trade_pnl_recorded)}">${money(s.trade_pnl_recorded, { sign: true })}</span>
      across ${s.trades} trades) is not cash and is not included.</p>

    <div class="section-head"><h2>Per-account history</h2>
      <select name="type" style="width:auto">
        <option value="">All accounts</option>
        <option value="evaluation" ${typeFilter === "evaluation" ? "selected" : ""}>Evaluations</option>
        <option value="funded" ${typeFilter === "funded" ? "selected" : ""}>Funded</option>
      </select></div>
    <div data-table></div>`;

  const table = el.querySelector("[data-table]");
  function draw() {
    const rows = accounts.filter((a) => !typeFilter || a.type === typeFilter);
    if (!rows.length) { table.innerHTML = `<div class="empty"><p>No accounts yet.</p></div>`; return; }
    table.innerHTML = `<div class="table-wrap"><table>
      <thead><tr><th>Account</th><th>Type</th><th>Status</th><th>Purchased</th><th>Passed</th><th>Ended</th>
        <th class="right">Trades</th><th class="right">W / L</th><th class="right">Trade P&amp;L</th>
        <th class="right">Cost</th><th class="right">Payouts</th><th class="right">Net cash</th></tr></thead>
      <tbody>${rows.map((a) => `<tr class="clickable" data-href="#/accounts/${a.id}">
        <td><strong>${esc(accountLabel(a))}</strong></td><td>${typeBadge(a.type)}</td><td>${statusBadge(a)}</td>
        <td class="num">${esc(fmtDate(a.purchase_date))}</td><td class="num">${a.pass_date ? esc(fmtDate(a.pass_date)) : "—"}</td>
        <td class="num">${a.end_date ? esc(fmtDate(a.end_date)) : "—"}</td>
        <td class="right num">${a.trades}</td><td class="right num">${a.wins} / ${a.losses}</td>
        <td class="right num ${moneyClass(a.pnl)}">${money(a.pnl, { sign: true })}</td>
        <td class="right num">${money(a.cost)}</td>
        <td class="right num ${a.payouts_received ? "pos" : "faint"}">${money(a.payouts_received)}</td>
        <td class="right num ${moneyClass(a.net_cash_flow)}">${money(a.net_cash_flow, { sign: true })}</td>
      </tr>`).join("")}</tbody></table></div>`;
  }
  el.querySelector("select[name=type]").addEventListener("change", (e) => { typeFilter = e.target.value; draw(); });
  table.addEventListener("click", (e) => { const r = e.target.closest("[data-href]"); if (r) location.hash = r.dataset.href; });
  draw();
}

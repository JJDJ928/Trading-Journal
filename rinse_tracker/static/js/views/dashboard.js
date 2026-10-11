import { api } from "../api.js";
import { openAccountForm, openPayoutForm, openTradeForm } from "../forms.js";
import { accountLabel, esc, fmtDateTime, money, moneyClass, resultBadge, statusBadge } from "../ui.js";

export const stat = (label, value, { sub = "", cls = "", feature = false } = {}) => `
  <div class="stat ${feature ? "feature" : ""}"><div class="label">${label}</div>
  <div class="value ${cls}">${value}</div>${sub ? `<div class="sub">${sub}</div>` : ""}</div>`;

export async function render(el) {
  const { summary: s, recent_trades: recent, open_accounts: open } = await api.get("/api/dashboard");
  el.innerHTML = `
    <div class="page-head"><h1>Dashboard</h1></div>
    <div class="grid cards">
      ${stat("Evaluations purchased", s.evaluations_purchased)}
      ${stat("Active evaluations", s.evaluations_active)}
      ${stat("Evaluations passed", s.evaluations_passed)}
      ${stat("Failed / breached", s.evaluations_failed, { sub: s.funded_failed ? `+ ${s.funded_failed} funded breached` : "" })}
      ${stat("Funded accounts received", s.funded_accounts)}
      ${stat("Payouts received", s.payouts_paid_count, { sub: s.payouts_pending_count ? `${s.payouts_pending_count} pending` : "" })}
      ${stat("Spent on evaluations", money(s.total_fees), { sub: s.activation_fees ? `incl. ${money(s.activation_fees)} activation fees` : "" })}
      ${stat("Payout money received", money(s.payouts_received), { cls: s.payouts_received > 0 ? "pos" : "",
        sub: s.payouts_pending_amount ? `${money(s.payouts_pending_amount)} pending, not counted` : "Paid payouts only" })}
      ${stat("Net cash flow", money(s.net_cash_flow, { sign: true }), { cls: moneyClass(s.net_cash_flow), feature: true, sub: "Payouts received − fees spent" })}
    </div>
    <p class="note">Recorded trade P&amp;L: <span class="num ${moneyClass(s.trade_pnl_recorded)}">${money(s.trade_pnl_recorded, { sign: true })}</span>.
      That's money earned on accounts, not cash. Only paid payouts count as received.</p>

    <div class="quick">
      <button class="btn primary" data-q="trade">+ Log trade</button>
      <button class="btn" data-q="account">+ Add account</button>
      <button class="btn" data-q="payout">+ Record payout</button>
    </div>

    <div class="grid two-col">
      <section class="panel">
        <div class="section-head" style="margin-top:0"><h2>Recent trades</h2><a href="#/trades" class="small">View journal →</a></div>
        ${recent.length ? `<div class="table-wrap" style="border:none"><table><tbody>
          ${recent.map((t) => `<tr class="clickable" data-href="#/accounts/${t.account_id}">
            <td class="muted small num">${esc(fmtDateTime(t.traded_at))}</td>
            <td><strong class="num">${esc(t.instrument || "—")}</strong></td>
            <td>${resultBadge(t.result)}</td>
            <td class="right num ${moneyClass(t.pnl)}">${t.pnl != null ? money(t.pnl, { sign: true }) : ""}</td>
            <td class="muted small">${esc(accountLabel(t))}${t.screenshot_count ? ` · 🖼 ${t.screenshot_count}` : ""}</td>
          </tr>`).join("")}</tbody></table></div>`
          : `<div class="empty"><p>No trades yet.</p><button class="btn primary" data-q="trade">Log your first trade</button></div>`}
      </section>
      <section class="panel">
        <div class="section-head" style="margin-top:0"><h2>Open accounts</h2><a href="#/accounts" class="small">All accounts →</a></div>
        ${open.length ? `<div class="table-wrap" style="border:none"><table><tbody>
          ${open.map((a) => `<tr class="clickable" data-href="#/accounts/${a.id}">
            <td>${esc(accountLabel(a))}</td><td class="right">${statusBadge(a)}</td></tr>`).join("")}
          </tbody></table></div>`
          : `<div class="empty"><p>No open accounts.</p><button class="btn primary" data-q="account">Add an evaluation</button></div>`}
      </section>
    </div>`;

  el.addEventListener("click", (e) => {
    const q = e.target.closest("[data-q]")?.dataset.q;
    if (q === "trade") openTradeForm();
    else if (q === "account") openAccountForm();
    else if (q === "payout") openPayoutForm();
    const row = e.target.closest("[data-href]");
    if (row && !q) location.hash = row.dataset.href;
  });
}

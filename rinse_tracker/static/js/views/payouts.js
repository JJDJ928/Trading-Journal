import { api, qs } from "../api.js";
import { dataChanged, openPayoutForm } from "../forms.js";
import { accountLabel, accountOptions, confirmDialog, esc, fmtDate, money, payoutBadge, toast } from "../ui.js";
import { stat } from "./dashboard.js";

const filters = { status: "", account_id: "" };

export async function render(el) {
  const [funded, all] = await Promise.all([api.get("/api/accounts?type=funded"), api.get("/api/payouts")]);
  const paid = all.filter((p) => p.status === "paid");
  const pending = all.filter((p) => ["requested", "approved"].includes(p.status));
  const received = paid.reduce((s, p) => s + p.amount_received, 0);
  const pendingAmt = pending.reduce((s, p) => s + p.amount_requested, 0);

  el.innerHTML = `
    <div class="page-head"><h1>Payouts</h1>
      <div class="actions"><button class="btn primary" data-act="new">+ Record payout</button></div></div>
    <div class="grid cards">
      ${stat("Total received (all accounts)", money(received), { cls: received ? "pos" : "", sub: `${paid.length} paid payout${paid.length === 1 ? "" : "s"}`, feature: true })}
      ${stat("Pending", money(pendingAmt), { sub: `${pending.length} requested / approved. Not counted until paid` })}
      ${stat("Rejected", all.filter((p) => p.status === "rejected").length)}
    </div>
    <div class="filters" style="margin-top:18px">
      <select name="status"><option value="">All statuses</option>
        ${["requested", "approved", "rejected", "paid"].map((s) => `<option value="${s}" ${filters.status === s ? "selected" : ""}>${s[0].toUpperCase() + s.slice(1)}</option>`).join("")}</select>
      <select name="account_id"><option value="">All funded accounts</option>${accountOptions(funded, filters.account_id)}</select>
    </div>
    <div data-results></div>`;
  const results = el.querySelector("[data-results]");

  async function load() {
    const list = await api.get(`/api/payouts${qs(filters)}`);
    if (!list.length) {
      results.innerHTML = `<div class="empty"><p>${all.length ? "No payouts match these filters." : "No payouts recorded yet."}</p></div>`;
      return;
    }
    results.innerHTML = `<div class="table-wrap"><table>
      <thead><tr><th>Account</th><th>Status</th><th class="right">Requested</th><th class="right">Received</th>
        <th>Request date</th><th>Payment date</th><th>Notes</th><th></th></tr></thead>
      <tbody>${list.map((p) => `<tr data-id="${p.id}">
        <td><a href="#/accounts/${p.account_id}">${esc(accountLabel(p))}</a></td>
        <td>${payoutBadge(p.status)}</td>
        <td class="right num">${money(p.amount_requested)}</td>
        <td class="right num ${p.status === "paid" ? "pos" : "faint"}">${p.status === "paid" ? money(p.amount_received) : "—"}</td>
        <td class="num">${esc(fmtDate(p.request_date))}</td>
        <td class="num">${p.payment_date ? esc(fmtDate(p.payment_date)) : "—"}</td>
        <td class="wrap">${esc(p.notes)}</td>
        <td class="right nowrap"><button class="btn ghost sm" data-act="edit">Edit</button><button class="btn ghost sm" data-act="delete">Delete</button></td>
      </tr>`).join("")}</tbody></table></div>`;
    results.onclick = async (e) => {
      const act = e.target.closest("[data-act]")?.dataset.act;
      const p = list.find((x) => String(x.id) === e.target.closest("tr")?.dataset.id);
      if (!p || !act) return;
      if (act === "edit") openPayoutForm({ payout: p });
      if (act === "delete" && await confirmDialog({ title: "Delete payout?", message: `Delete the ${money(p.amount_requested)} payout requested ${esc(fmtDate(p.request_date))}?` })) {
        try { await api.del(`/api/payouts/${p.id}`); toast("Payout deleted"); dataChanged(); }
        catch (err) { toast(err.message, "error"); }
      }
    };
  }

  el.querySelector(".filters").addEventListener("input", (e) => { filters[e.target.name] = e.target.value; load(); });
  el.querySelector("[data-act=new]").addEventListener("click", () => openPayoutForm({ accountId: filters.account_id || null }));
  await load();
}

// Trade cards, shared by the Trade Journal and the account detail page.
import { api } from "../api.js";
import { dataChanged, openTradeForm } from "../forms.js";
import {
  accountLabel, confirmDialog, esc, fmtDateTime, money, moneyClass, openLightbox, resultBadge, toast,
} from "../ui.js";

export function tradeCards(trades, { showAccount = true } = {}) {
  return `<div class="trade-list">${trades.map((t) => `
    <article class="trade" data-trade="${t.id}">
      <div class="trade-head">
        <span class="muted small num">${esc(fmtDateTime(t.traded_at))}</span>
        <span class="inst">${esc(t.instrument || "—")}</span>
        ${resultBadge(t.result)}
        ${t.pnl != null ? `<span class="num ${moneyClass(t.pnl)}">${money(t.pnl, { sign: true })}</span>` : ""}
        ${showAccount ? `<a class="acct" href="#/accounts/${t.account_id}">${esc(accountLabel(t))}</a>` : ""}
        <span class="spacer"></span>
        <span class="trade-actions">
          <button class="btn ghost sm" data-act="edit">Edit</button>
          <button class="btn ghost sm" data-act="delete">Delete</button>
        </span>
      </div>
      ${t.summary ? `<div class="trade-summary">${esc(t.summary)}</div>` : ""}
      ${t.notes ? `<div class="trade-notes">${esc(t.notes)}</div>` : ""}
      ${t.screenshots.length ? `<div class="thumbs">${t.screenshots.map((s, i) => `
        <button class="thumb" data-shot="${i}" title="${esc(s.original_name)}"><img src="${esc(s.url)}" alt="${esc(s.original_name)}" loading="lazy"></button>`).join("")}</div>` : ""}
    </article>`).join("")}</div>`;
}

export function bindTradeCards(container, trades) {
  const byId = new Map(trades.map((t) => [String(t.id), t]));
  container.addEventListener("click", async (e) => {
    const card = e.target.closest("[data-trade]");
    if (!card) return;
    const trade = byId.get(card.dataset.trade);
    const shot = e.target.closest("[data-shot]");
    if (shot) {
      openLightbox(trade.screenshots.map((s) => ({ url: s.url, name: s.original_name })), Number(shot.dataset.shot));
      return;
    }
    const act = e.target.closest("[data-act]")?.dataset.act;
    if (act === "edit") openTradeForm({ trade });
    if (act === "delete") {
      const n = trade.screenshots.length;
      const ok = await confirmDialog({
        title: "Delete trade?",
        message: `This permanently deletes the ${esc(trade.instrument || "")} trade from ${esc(fmtDateTime(trade.traded_at))}${n ? ` and its ${n} screenshot${n > 1 ? "s" : ""}` : ""}.`,
        confirmLabel: "Delete trade",
      });
      if (!ok) return;
      try {
        await api.del(`/api/trades/${trade.id}`);
        toast("Trade deleted");
        dataChanged();
      } catch (err) { toast(err.message, "error"); }
    }
  });
}

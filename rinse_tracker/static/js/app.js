// Hash router. Each page renders into a fresh element; any save re-renders the
// current page (via "data-changed") so every number stays current.
import { api } from "./api.js";
import { openTradeForm } from "./forms.js";
import { esc, isModalOpen } from "./ui.js";
import * as accounts from "./views/accounts.js";
import * as backup from "./views/backup.js";
import * as dashboard from "./views/dashboard.js";
import * as payouts from "./views/payouts.js";
import * as stats from "./views/stats.js";
import * as trades from "./views/trades.js";

const routes = [
  [/^#?\/?$/, "dashboard", (el) => dashboard.render(el)],
  [/^#\/accounts\/(\d+)$/, "accounts", (el, id) => accounts.renderDetail(el, id)],
  [/^#\/accounts$/, "accounts", (el) => accounts.renderList(el)],
  [/^#\/trades$/, "trades", (el) => trades.render(el)],
  [/^#\/payouts$/, "payouts", (el) => payouts.render(el)],
  [/^#\/stats$/, "stats", (el) => stats.render(el)],
  [/^#\/backup$/, "backup", (el) => backup.render(el)],
];

const view = document.getElementById("view");
let renderSeq = 0;

async function render({ keepScroll = false } = {}) {
  const hash = location.hash || "#/";
  const match = routes.find(([re]) => re.test(hash)) || routes[0];
  const [re, nav, fn] = match;
  const args = hash.match(re)?.slice(1) || [];
  document.querySelectorAll("[data-nav]").forEach((a) => a.classList.toggle("active", a.dataset.nav === nav));

  const seq = ++renderSeq;
  const scroll = window.scrollY;
  const page = document.createElement("div");
  try {
    await fn(page, ...args);
  } catch (err) {
    page.innerHTML = `<div class="empty"><p>${esc(err.status === 404 ? "Not found." : err.message)}</p>
      <a class="btn" href="#/">Back to dashboard</a></div>`;
  }
  if (seq !== renderSeq) return; // a newer navigation won
  view.replaceChildren(page);
  window.scrollTo(0, keepScroll ? scroll : 0);
}

window.addEventListener("hashchange", () => render());
window.addEventListener("data-changed", () => render({ keepScroll: true }));
document.querySelector("[data-quick=trade]").addEventListener("click", () => openTradeForm({ accountId: currentAccount() }));

function currentAccount() {
  const m = location.hash.match(/^#\/accounts\/(\d+)$/);
  if (m) return m[1];
  return location.hash === "#/trades" ? trades.dropAccount() : null;
}

// Drop screenshots anywhere on the page to start a new trade with them attached.
const overlay = document.getElementById("drop-overlay");
let dragDepth = 0;
const hasFiles = (e) => [...(e.dataTransfer?.types || [])].includes("Files");
window.addEventListener("dragenter", (e) => {
  if (!hasFiles(e) || isModalOpen()) return;
  dragDepth++;
  overlay.hidden = false;
});
window.addEventListener("dragleave", () => { if (--dragDepth <= 0) { dragDepth = 0; overlay.hidden = true; } });
window.addEventListener("dragover", (e) => { if (hasFiles(e)) e.preventDefault(); });
window.addEventListener("drop", (e) => {
  e.preventDefault();
  dragDepth = 0;
  overlay.hidden = true;
  if (isModalOpen()) return;
  const files = [...e.dataTransfer.files].filter((f) => f.type.startsWith("image/"));
  if (files.length) openTradeForm({ accountId: currentAccount(), files });
});

api.get("/api/meta").then((m) => { document.getElementById("demo-banner").hidden = !m.demo; }).catch(() => {});
render();

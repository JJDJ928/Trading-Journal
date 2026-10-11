// Shared formatting and UI building blocks: modal, confirm, toast, lightbox.

export function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

const usd = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });
export function money(v, { sign = false } = {}) {
  if (v == null) return "—";
  const s = usd.format(v);
  return sign && v > 0 ? `+${s}` : s;
}
export function moneyClass(v) { return v > 0 ? "pos" : v < 0 ? "neg" : ""; }

export function sizeShort(v) {
  if (v == null) return "";
  if (v >= 1000 && v % 1000 === 0) return `$${v / 1000}K`;
  return usd.format(v).replace(/\.00$/, "");
}

export function fmtDate(iso) {
  if (!iso) return "—";
  const d = new Date(iso.length === 10 ? `${iso}T00:00` : iso);
  return isNaN(d) ? iso : d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}
export function fmtDateTime(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  return isNaN(d) ? iso : d.toLocaleString(undefined, { month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit" });
}
export function todayISO() {
  const d = new Date();
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
}
export function nowLocal() {
  const d = new Date();
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
}
export function pct(v) { return v == null ? "—" : `${(v * 100).toFixed(1)}%`; }

export const STATUS_LABELS = {
  active: "Active Evaluation", passed: "Passed", funded: "Funded",
  failed: "Failed / Breached", closed: "Closed",
};
export const PAYOUT_LABELS = { requested: "Requested", approved: "Approved", rejected: "Rejected", paid: "Paid" };
export const RESULT_LABELS = { win: "Win", loss: "Loss", breakeven: "Breakeven" };

export function statusBadge(a) {
  const label = a.type === "evaluation" && a.status === "funded" ? "Passed → Funded" : STATUS_LABELS[a.status];
  return `<span class="badge ${esc(a.status)}">${esc(label)}</span>`;
}
export function typeBadge(type) {
  return `<span class="badge type">${type === "funded" ? "Funded" : "Evaluation"}</span>`;
}
export function payoutBadge(s) { return `<span class="badge ${esc(s)}">${esc(PAYOUT_LABELS[s])}</span>`; }
export function resultBadge(r) { return `<span class="badge ${esc(r)}">${esc(RESULT_LABELS[r])}</span>`; }

// "Apex $50K · APX-1001" — works on accounts, trades and payouts (account_size).
export function accountLabel(a) {
  const size = sizeShort(a.size ?? a.account_size);
  return `${a.firm} ${size}${a.account_ref ? ` · ${a.account_ref}` : ""}`;
}
export function accountOption(a, selectedId) {
  const tag = a.type === "funded" ? "Funded" : "Eval";
  const sel = String(a.id) === String(selectedId) ? " selected" : "";
  return `<option value="${a.id}"${sel}>${esc(accountLabel(a))} (${tag}, ${esc(STATUS_LABELS[a.status])})</option>`;
}
export const isOpen = (a) => ["active", "passed", "funded"].includes(a.status) && !(a.type === "evaluation" && a.status === "funded");

export function accountOptions(accounts, selectedId) {
  const open = accounts.filter(isOpen), rest = accounts.filter((a) => !isOpen(a));
  let html = "";
  if (open.length) html += `<optgroup label="Open">${open.map((a) => accountOption(a, selectedId)).join("")}</optgroup>`;
  if (rest.length) html += `<optgroup label="Ended / converted">${rest.map((a) => accountOption(a, selectedId)).join("")}</optgroup>`;
  return html;
}

export function h(html) {
  const t = document.createElement("template");
  t.innerHTML = html.trim();
  return t.content.firstElementChild;
}

// ---------------------------------------------------------------- toast
export function toast(message, type = "ok") {
  const el = h(`<div class="toast ${type === "error" ? "error" : ""}">${esc(message)}</div>`);
  const root = document.getElementById("toast-root");
  root.append(el);
  while (root.children.length > 3) root.firstElementChild.remove();
  setTimeout(() => el.remove(), type === "error" ? 6000 : 3000);
}

// ---------------------------------------------------------------- modal
let modalStack = 0;
export function isModalOpen() { return modalStack > 0; }

/**
 * openModal({ title, body, submitLabel, onSubmit(form), wide, danger, footNote })
 * onSubmit may throw an ApiError; its field errors are shown next to inputs.
 * Return value of onSubmit is passed to onDone. The modal closes on success.
 */
export function openModal({ title, body, submitLabel = "Save", onSubmit, wide = false, danger = false, footNote = "", onClose }) {
  const root = h(`
    <div class="modal-backdrop">
      <form class="modal ${wide ? "wide" : ""}" novalidate>
        <div class="modal-head"><h2>${esc(title)}</h2>
          <button type="button" class="btn ghost sm" data-close aria-label="Close">✕</button></div>
        <div class="modal-body"><div class="form-error" hidden></div>${body}</div>
        <div class="modal-foot">
          <span class="left">${footNote}</span>
          <button type="button" class="btn" data-close>Cancel</button>
          ${onSubmit ? `<button type="submit" class="btn ${danger ? "danger solid" : "primary"}">${esc(submitLabel)}</button>` : ""}
        </div>
      </form>
    </div>`);
  const form = root.querySelector("form");
  const errorBox = root.querySelector(".form-error");
  let closed = false;

  function close() {
    if (closed) return;
    closed = true;
    modalStack--;
    document.removeEventListener("keydown", onKey, true);
    root.remove();
    onClose && onClose();
  }
  function onKey(e) {
    if (e.key === "Escape" && !document.querySelector(".lightbox")) { e.preventDefault(); close(); }
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); form.requestSubmit(); }
  }
  root.addEventListener("mousedown", (e) => { if (e.target === root) close(); });
  root.querySelectorAll("[data-close]").forEach((b) => b.addEventListener("click", close));
  document.addEventListener("keydown", onKey, true);

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (!onSubmit) return;
    clearErrors(form);
    errorBox.hidden = true;
    const btn = form.querySelector("button[type=submit]");
    btn.disabled = true;
    try {
      await onSubmit(form);
      close();
    } catch (err) {
      showErrors(form, err.fields || {});
      errorBox.textContent = err.message || "Something went wrong.";
      errorBox.hidden = false;
      const first = form.querySelector(".invalid");
      (first || errorBox).scrollIntoView({ block: "nearest" });
    } finally {
      btn.disabled = false;
    }
  });

  document.getElementById("modal-root").append(root);
  modalStack++;
  const focus = form.querySelector("[autofocus]") || form.querySelector("input, select, textarea");
  focus && focus.focus();
  return { root, form, close };
}

function clearErrors(form) {
  form.querySelectorAll(".invalid").forEach((el) => el.classList.remove("invalid"));
  form.querySelectorAll(".field-error").forEach((el) => el.remove());
}
function showErrors(form, fields) {
  for (const [name, msg] of Object.entries(fields)) {
    const input = form.querySelector(`[name="${name}"]`) || form.querySelector(`[data-field="${name}"]`);
    if (!input) continue;
    const target = input.closest(".segmented") || input;
    target.classList.add("invalid");
    const holder = input.closest("label.field") || target.parentElement;
    holder.append(h(`<div class="field-error">${esc(msg)}</div>`));
  }
}

export function confirmDialog({ title, message, confirmLabel = "Delete", danger = true }) {
  return new Promise((resolve) => {
    let ok = false;
    openModal({
      title, body: `<p style="margin:0">${message}</p>`, submitLabel: confirmLabel, danger,
      onSubmit: async () => { ok = true; },
      onClose: () => resolve(ok),
    });
  });
}

// Read named form fields into a plain object (strings, trimmed).
export function formData(form, names) {
  const out = {};
  for (const n of names) {
    const el = form.elements[n];
    if (!el) continue;
    out[n] = el instanceof RadioNodeList ? el.value : (el.value ?? "").trim();
  }
  return out;
}

// ---------------------------------------------------------------- lightbox
export function openLightbox(images, start = 0) {
  if (!images.length) return;
  let i = start;
  const el = h(`
    <div class="lightbox" role="dialog" aria-label="Screenshot">
      <img alt="">
      <button class="lb-btn close" aria-label="Close">✕</button>
      <button class="lb-btn prev" aria-label="Previous">‹</button>
      <button class="lb-btn next" aria-label="Next">›</button>
      <div class="lb-bar"><span class="count"></span><a target="_blank" rel="noopener">Open full size ↗</a></div>
    </div>`);
  const img = el.querySelector("img"), link = el.querySelector("a"), count = el.querySelector(".count");
  const multi = images.length > 1;
  el.querySelector(".prev").hidden = !multi;
  el.querySelector(".next").hidden = !multi;
  function show() {
    img.src = images[i].url;
    link.href = images[i].url;
    link.hidden = images[i].url.startsWith("blob:");
    count.textContent = `${images[i].name || "Screenshot"}${multi ? `  (${i + 1} / ${images.length})` : ""}`;
  }
  function step(d) { i = (i + d + images.length) % images.length; show(); }
  function close() { document.removeEventListener("keydown", onKey, true); el.remove(); }
  function onKey(e) {
    if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); close(); }
    else if (e.key === "ArrowLeft") step(-1);
    else if (e.key === "ArrowRight") step(1);
  }
  el.addEventListener("click", (e) => {
    if (e.target.closest(".prev")) step(-1);
    else if (e.target.closest(".next")) step(1);
    else if (e.target === el || e.target.closest(".close")) close();
  });
  document.addEventListener("keydown", onKey, true);
  show();
  document.body.append(el);
}

export function debounce(fn, ms = 250) {
  let t;
  return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
}

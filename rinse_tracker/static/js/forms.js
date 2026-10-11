// All create/edit dialogs. Every successful save fires a "data-changed" event,
// which re-renders the current page so totals are always up to date.
import { api } from "./api.js";
import {
  accountLabel, accountOptions, esc, formData, money, nowLocal, openLightbox, openModal,
  STATUS_LABELS, todayISO, toast,
} from "./ui.js";

export function dataChanged() { window.dispatchEvent(new Event("data-changed")); }

const field = (label, input, { full = false, hint = "", optional = false } = {}) => `
  <label class="field ${full ? "full" : ""}"><span>${label}${optional ? " <em>optional</em>" : ""}</span>${input}
  ${hint ? `<div class="hint">${hint}</div>` : ""}</label>`;

// ---------------------------------------------------------------- accounts
const STATUS_BY_TYPE = { evaluation: ["active", "passed", "failed", "closed"], funded: ["funded", "failed", "closed"] };

export async function openAccountForm(account = null) {
  const accounts = await api.get("/api/accounts");
  const firms = [...new Set(accounts.map((a) => a.firm))];
  const a = account || { type: "evaluation", status: "active", purchase_date: todayISO() };
  const linked = account && (account.parent_id || account.child_id);
  const statusOptions = (type, current) => {
    const list = [...STATUS_BY_TYPE[type]];
    if (type === "evaluation" && current === "funded") list.splice(2, 0, "funded");
    return list.map((s) => `<option value="${s}" ${s === current ? "selected" : ""}>${STATUS_LABELS[s]}</option>`).join("");
  };

  const body = `
    <div class="form-grid">
      ${field("Prop firm", `<input name="firm" list="firm-list" value="${esc(a.firm)}" autofocus autocomplete="off" placeholder="e.g. Apex">
        <datalist id="firm-list">${firms.map((f) => `<option value="${esc(f)}">`).join("")}</datalist>`)}
      ${field("Account ID / nickname", `<input name="account_ref" value="${esc(a.account_ref)}" placeholder="e.g. APX-1001">`, { optional: true })}
      ${field("Account size", `<input name="size" inputmode="decimal" list="size-list" value="${a.size ?? ""}" placeholder="50000">
        <datalist id="size-list"><option value="25000"><option value="50000"><option value="100000"><option value="150000"><option value="300000"></datalist>`)}
      ${field("Account type", `<select name="type" ${linked ? "disabled" : ""}>
        <option value="evaluation" ${a.type === "evaluation" ? "selected" : ""}>Evaluation</option>
        <option value="funded" ${a.type === "funded" ? "selected" : ""}>Funded</option></select>`,
        { hint: linked ? "Locked: this account is linked to another account." : "" })}
      ${field(a.type === "funded" ? "Cost / activation fee" : "Evaluation cost", `<input name="cost" inputmode="decimal" value="${a.cost ?? ""}" placeholder="0.00">`)}
      ${field("Purchase date", `<input type="date" name="purchase_date" value="${esc(a.purchase_date)}">`)}
      ${field("Status", `<select name="status" ${account?.child_id ? "disabled" : ""}>${statusOptions(a.type, a.status)}</select>`,
        { hint: account?.child_id ? "Converted to a funded account. Track its status there." : "" })}
      <div data-when="pass">${field("Pass date", `<input type="date" name="pass_date" value="${esc(a.pass_date)}">`)}</div>
      <div data-when="end">${field("End date (failed / closed)", `<input type="date" name="end_date" value="${esc(a.end_date)}">`)}</div>
      ${field("Notes", `<textarea name="notes" rows="2">${esc(a.notes)}</textarea>`, { full: true, optional: true })}
    </div>`;

  const { form } = openModal({
    title: account ? "Edit account" : "New account",
    body,
    submitLabel: account ? "Save changes" : "Add account",
    onSubmit: async (form) => {
      const data = formData(form, ["firm", "account_ref", "size", "type", "cost", "purchase_date", "status", "pass_date", "end_date", "notes"]);
      if (linked) delete data.type;
      if (account?.child_id) delete data.status;
      const saved = account ? await api.put(`/api/accounts/${account.id}`, data) : await api.post("/api/accounts", data);
      toast(account ? "Account updated" : `Added ${accountLabel(saved)}`);
      dataChanged();
    },
  });

  const typeSel = form.elements.type, statusSel = form.elements.status;
  function sync() {
    const type = typeSel.value, status = statusSel.value;
    form.querySelector("[data-when=pass]").hidden = !(type === "evaluation" && ["passed", "funded", "closed"].includes(status));
    form.querySelector("[data-when=end]").hidden = !["failed", "closed"].includes(status);
  }
  typeSel.addEventListener("change", () => {
    statusSel.innerHTML = statusOptions(typeSel.value, typeSel.value === "evaluation" ? "active" : "funded");
    sync();
  });
  statusSel.addEventListener("change", sync);
  sync();
}

// Quick status change with the relevant date (pass date / end date).
export function openStatusChange(account, status) {
  const isPass = status === "passed";
  const label = isPass ? "Pass date" : status === "failed" ? "Breach / fail date" : "Close date";
  const name = isPass ? "pass_date" : "end_date";
  openModal({
    title: `Mark ${accountLabel(account)} as ${STATUS_LABELS[status]}`,
    body: field(label, `<input type="date" name="${name}" value="${todayISO()}" autofocus>`) +
      (status === "failed" ? `<p class="hint">The account and its full trade history are kept.</p>` : ""),
    submitLabel: `Mark ${STATUS_LABELS[status]}`,
    danger: status === "failed",
    onSubmit: async (form) => {
      await api.put(`/api/accounts/${account.id}`, { status, [name]: form.elements[name].value });
      toast(`Marked ${STATUS_LABELS[status]}`);
      dataChanged();
    },
  });
}

export function openFundForm(evaluation) {
  openModal({
    title: "Create funded account",
    body: `
      <p class="muted" style="margin-top:0">Links a new funded account to <strong>${esc(accountLabel(evaluation))}</strong>.
      The evaluation keeps counting once as a passed evaluation; the funded account is counted separately, once.</p>
      <div class="form-grid">
        ${field("Funded start date", `<input type="date" name="purchase_date" value="${esc(evaluation.pass_date || todayISO())}">`)}
        ${field("Activation fee", `<input name="cost" inputmode="decimal" placeholder="0.00" autofocus>`, { optional: true, hint: "Counts toward money spent." })}
        ${field("Funded account ID / nickname", `<input name="account_ref" value="${esc(evaluation.account_ref)}">`, { optional: true })}
        ${field("Notes", `<input name="notes">`, { optional: true })}
      </div>`,
    submitLabel: "Create funded account",
    onSubmit: async (form) => {
      const funded = await api.post(`/api/accounts/${evaluation.id}/fund`, formData(form, ["purchase_date", "cost", "account_ref", "notes"]));
      toast("Funded account created");
      location.hash = `#/accounts/${funded.id}`;
      dataChanged();
    },
  });
}

// ---------------------------------------------------------------- trades
const MAX_IMAGE = 25 * 1024 * 1024;
const LAST_ACCOUNT = "rinse.lastAccount", LAST_INSTRUMENT = "rinse.lastInstrument";
const remember = (k, v) => { try { localStorage.setItem(k, v); } catch { /* storage unavailable */ } };
const recall = (k) => { try { return localStorage.getItem(k); } catch { return null; } };

/** openTradeForm({ trade, accountId, files }) — files: images dropped before the form opened. */
export async function openTradeForm({ trade = null, accountId = null, files = [] } = {}) {
  const [accounts, instruments] = await Promise.all([api.get("/api/accounts"), api.get("/api/instruments")]);
  if (!accounts.length) {
    openModal({ title: "Log trade", body: `<p style="margin:0">Add an account first, then log trades against it.</p>`,
      submitLabel: "Add account", onSubmit: async () => setTimeout(() => openAccountForm(), 0) });
    return;
  }
  const lastAcct = recall(LAST_ACCOUNT);
  const selected = trade?.account_id ?? accountId ??
    (accounts.some((a) => String(a.id) === lastAcct) ? lastAcct : (accounts.find((a) => a.status !== "failed") || accounts[0]).id);
  const t = trade || { traded_at: nowLocal(), instrument: recall(LAST_INSTRUMENT) || "", result: "" };

  const existing = trade ? trade.screenshots.map((s) => ({ ...s, existing: true })) : [];
  const added = [];              // { file, url }
  const removed = new Set();     // ids of existing screenshots to delete on save

  const resultRadio = (v, label) => `<label><input type="radio" name="result" value="${v}" ${t.result === v ? "checked" : ""}><span>${label}</span></label>`;
  const body = `
    <div class="form-grid">
      ${field("Account", `<select name="account_id">${accountOptions(accounts, selected)}</select>`, { full: true })}
      ${field("Date & time", `<input type="datetime-local" name="traded_at" value="${esc(t.traded_at)}">`)}
      ${field("Pair / instrument", `<input name="instrument" list="inst-list" value="${esc(t.instrument)}" placeholder="e.g. NQ, EURUSD" autocomplete="off">
        <datalist id="inst-list">${instruments.map((i) => `<option value="${esc(i)}">`).join("")}</datalist>`)}
      <label class="field"><span>Result</span><div class="segmented" data-field="result">
        ${resultRadio("win", "Win")}${resultRadio("loss", "Loss")}${resultRadio("breakeven", "BE")}</div></label>
      ${field("P&amp;L ($)", `<input name="pnl" inputmode="decimal" value="${t.pnl ?? ""}" placeholder="e.g. 250 or -120">`, { optional: true })}
      <div class="full">
        <div class="dropzone" tabindex="0" data-field="screenshots">
          <strong>Drop screenshots here</strong>, paste with Ctrl+V, or click to browse
          <input type="file" accept="image/*" multiple hidden name="screenshots">
        </div>
        <div class="previews"></div>
      </div>
      ${field("Summary", `<textarea name="summary" rows="4" placeholder="Setup, execution, what to remember…">${esc(t.summary)}</textarea>`, { full: true })}
      <details class="more full" ${t.notes ? "open" : ""}><summary>Notes</summary>
        <textarea name="notes" rows="2">${esc(t.notes)}</textarea></details>
    </div>`;

  const revokeAll = () => added.forEach((a) => URL.revokeObjectURL(a.url));
  const { form, root } = openModal({
    title: trade ? "Edit trade" : "Log trade",
    body, wide: true,
    submitLabel: trade ? "Save changes" : "Save trade",
    footNote: "Ctrl+Enter to save",
    onClose: revokeAll,
    onSubmit: async (form) => {
      const fd = new FormData();
      const data = formData(form, ["account_id", "traded_at", "instrument", "result", "pnl", "summary", "notes"]);
      for (const [k, v] of Object.entries(data)) fd.append(k, v);
      added.forEach((a) => fd.append("screenshots", a.file, a.file.name));
      if (removed.size) fd.append("remove_screenshots", [...removed].join(","));
      const saved = trade ? await api.put(`/api/trades/${trade.id}`, fd) : await api.post("/api/trades", fd);
      remember(LAST_ACCOUNT, data.account_id);
      if (data.instrument) remember(LAST_INSTRUMENT, data.instrument.toUpperCase());
      const n = saved.screenshots.length;
      toast(`${trade ? "Trade updated" : "Trade logged"}${n ? ` with ${n} screenshot${n > 1 ? "s" : ""}` : ""}`);
      dataChanged();
    },
  });

  const zone = form.querySelector(".dropzone"), input = zone.querySelector("input"), previews = form.querySelector(".previews");

  function addFiles(list) {
    for (const file of list) {
      if (!file.type.startsWith("image/")) { toast(`"${file.name}" is not an image`, "error"); continue; }
      if (file.size > MAX_IMAGE) { toast(`"${file.name}" is larger than 25 MB`, "error"); continue; }
      const name = file.name && file.name !== "image.png" ? file.name : `pasted-${Date.now()}.png`;
      const named = file.name === name ? file : new File([file], name, { type: file.type });
      added.push({ file: named, url: URL.createObjectURL(named) });
    }
    renderPreviews();
  }
  function shown() {
    return [
      ...existing.filter((s) => !removed.has(s.id)).map((s) => ({ url: s.url, name: s.original_name, key: `e${s.id}` })),
      ...added.map((a, i) => ({ url: a.url, name: a.file.name, key: `n${i}`, isNew: true })),
    ];
  }
  function renderPreviews() {
    const items = shown();
    previews.innerHTML = items.map((it, i) => `
      <div class="preview"><img src="${esc(it.url)}" alt="${esc(it.name)}" data-i="${i}">
        <button type="button" class="x" data-key="${it.key}" title="Remove screenshot">×</button>
        ${it.isNew ? `<span class="tag">new</span>` : ""}</div>`).join("");
  }
  previews.addEventListener("click", (e) => {
    const x = e.target.closest(".x");
    if (x) {
      const key = x.dataset.key;
      if (key[0] === "e") removed.add(Number(key.slice(1)));
      else { const [a] = added.splice(Number(key.slice(1)), 1); URL.revokeObjectURL(a.url); }
      renderPreviews();
      return;
    }
    const img = e.target.closest("img");
    if (img) openLightbox(shown(), Number(img.dataset.i));
  });

  zone.addEventListener("click", () => input.click());
  zone.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); input.click(); } });
  input.addEventListener("change", () => { addFiles(input.files); input.value = ""; });
  // The whole dialog accepts drops, not just the zone.
  root.addEventListener("dragover", (e) => { e.preventDefault(); e.stopPropagation(); zone.classList.add("over"); });
  root.addEventListener("dragleave", (e) => { if (e.target === root || !root.contains(e.relatedTarget)) zone.classList.remove("over"); });
  root.addEventListener("drop", (e) => {
    e.preventDefault(); e.stopPropagation(); zone.classList.remove("over");
    addFiles(e.dataTransfer.files);
  });
  root.addEventListener("paste", (e) => {
    const imgs = [...(e.clipboardData?.files || [])].filter((f) => f.type.startsWith("image/"));
    if (imgs.length) { e.preventDefault(); addFiles(imgs); }
  });

  addFiles(files);
  renderPreviews();
  if (!trade) (t.instrument ? form.querySelector("[name=result]") : form.elements.instrument).focus();
}

// ---------------------------------------------------------------- payouts
export async function openPayoutForm({ payout = null, accountId = null } = {}) {
  const accounts = (await api.get("/api/accounts?type=funded"));
  if (!accounts.length) {
    openModal({ title: "Record payout", body: `<p style="margin:0">Payouts are recorded on funded accounts.
      Mark an evaluation as passed and create its funded account first, or add a funded account directly.</p>` });
    return;
  }
  const p = payout || { request_date: todayISO(), status: "requested" };
  const selected = p.account_id ?? accountId ?? accounts.find((a) => a.status === "funded")?.id ?? accounts[0].id;
  const statuses = ["requested", "approved", "rejected", "paid"];
  const body = `
    <div class="form-grid">
      ${field("Funded account", `<select name="account_id">${accountOptions(accounts, selected)}</select>`, { full: true })}
      ${field("Amount requested", `<input name="amount_requested" inputmode="decimal" value="${p.amount_requested ?? ""}" placeholder="0.00" autofocus>`)}
      ${field("Status", `<select name="status">${statuses.map((s) => `<option value="${s}" ${s === p.status ? "selected" : ""}>${s[0].toUpperCase() + s.slice(1)}</option>`).join("")}</select>`)}
      ${field("Request date", `<input type="date" name="request_date" value="${esc(p.request_date)}">`)}
      <div data-paid>${field("Payment date", `<input type="date" name="payment_date" value="${esc(p.payment_date)}">`)}</div>
      <div data-paid class="full">${field("Amount actually received", `<input name="amount_received" inputmode="decimal" value="${p.amount_received ?? ""}" placeholder="After fees / split">`,
        { hint: "Only payouts marked Paid count toward money received." })}</div>
      ${field("Notes", `<textarea name="notes" rows="2">${esc(p.notes)}</textarea>`, { full: true, optional: true })}
    </div>`;
  const { form } = openModal({
    title: payout ? "Edit payout" : "Record payout", body,
    submitLabel: payout ? "Save changes" : "Save payout",
    onSubmit: async (form) => {
      const data = formData(form, ["account_id", "amount_requested", "amount_received", "request_date", "payment_date", "status", "notes"]);
      const saved = payout ? await api.put(`/api/payouts/${payout.id}`, data) : await api.post("/api/payouts", data);
      toast(saved.status === "paid" ? `Payout of ${money(saved.amount_received)} recorded as received` : "Payout saved");
      dataChanged();
    },
  });
  const status = form.elements.status;
  const sync = () => form.querySelectorAll("[data-paid]").forEach((el) => { el.hidden = status.value === "rejected"; });
  status.addEventListener("change", () => {
    if (status.value === "paid") {
      if (!form.elements.payment_date.value) form.elements.payment_date.value = todayISO();
      if (!form.elements.amount_received.value) form.elements.amount_received.focus();
    }
    sync();
  });
  sync();
}


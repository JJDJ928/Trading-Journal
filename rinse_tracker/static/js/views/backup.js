import { api } from "../api.js";
import { dataChanged } from "../forms.js";
import { confirmDialog, esc, toast } from "../ui.js";

export async function render(el) {
  const meta = await api.get("/api/meta");
  el.innerHTML = `
    <div class="page-head"><h1>Backup &amp; Restore</h1></div>
    <div class="panel">
      <h2>Download a backup</h2>
      <p class="muted">One .zip file with every account, trade, summary, payout and screenshot.
        Keep copies somewhere safe (cloud drive, USB stick).</p>
      <a class="btn primary" href="/api/backup" download data-act="download">Download backup (.zip)</a>
      <p class="note">Data folder: <span class="num">${esc(meta.data_dir)}</span>${meta.demo ? " (demo data)" : ""}</p>
    </div>
    <div class="panel">
      <h2>Restore from a backup</h2>
      <p class="muted">Replaces <strong>all</strong> current data with the backup. Your current data is saved first to
        <span class="num">backups/pre-restore-….zip</span> in the data folder, so you can undo it.</p>
      <div style="display:flex;gap:10px;flex-wrap:wrap;align-items:center">
        <input type="file" accept=".zip,application/zip" name="backup" style="width:auto;max-width:100%">
        <button class="btn" data-act="restore" disabled>Restore…</button>
      </div>
    </div>`;
  // In the desktop app, save through a native Save dialog instead of a browser download.
  el.querySelector("[data-act=download]").addEventListener("click", async (e) => {
    const bridge = window.pywebview?.api;
    if (!bridge?.save_backup) return;
    e.preventDefault();
    try {
      const res = await bridge.save_backup();
      if (res.saved) toast(`Backup saved to ${res.path}`);
    } catch (err) { toast(`Backup failed: ${err.message || err}`, "error"); }
  });
  const input = el.querySelector("input[type=file]"), btn = el.querySelector("[data-act=restore]");
  input.addEventListener("change", () => { btn.disabled = !input.files.length; });
  btn.addEventListener("click", async () => {
    const file = input.files[0];
    if (!file) return;
    const ok = await confirmDialog({
      title: "Restore this backup?",
      message: `All current data will be replaced with <strong>${esc(file.name)}</strong>. A safety copy of your current data is saved first.`,
      confirmLabel: "Replace my data",
    });
    if (!ok) return;
    btn.disabled = true;
    btn.textContent = "Restoring…";
    try {
      const fd = new FormData();
      fd.append("backup", file);
      const res = await api.post("/api/backup/restore", fd);
      const c = res.restored.counts || {};
      toast(`Restored ${c.accounts ?? "?"} accounts, ${c.trades ?? "?"} trades, ${c.payouts ?? "?"} payouts.`);
      if (res.missing_screenshots) toast(`${res.missing_screenshots} screenshot file(s) were missing from the backup.`, "error");
      dataChanged();
    } catch (err) {
      toast(err.message, "error");
      btn.disabled = false;
      btn.textContent = "Restore…";
    }
  });
}

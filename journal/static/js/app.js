// Trading Journal front end: welcome screen, Home, Trades and Accounts.
(function () {
  "use strict";

  const state = { accounts: [], trades: [], settings: { name: "Jordi" }, days: {}, daily: { month: null, selected: null }, selectedTrade: null, filters: { q: "", account: "", range: "month" }, accountShow: "recent" };
  const view = document.getElementById("view");
  const modalRoot = document.getElementById("modal-root");
  let atom = null; // animation running on the current screen

  // ------------------------------------------------------------------ helpers
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
  const money = (v, sign = false) => {
    if (v == null || isNaN(v)) return "—";
    const abs = Math.abs(v).toLocaleString("en-US", { minimumFractionDigits: Math.abs(v) % 1 ? 2 : 0, maximumFractionDigits: 2 });
    if (sign) return (v > 0 ? "+$" : v < 0 ? "−$" : "$") + abs;
    return (v < 0 ? "−$" : "$") + abs;
  };
  const plural = (n, w) => `${n} ${n === 1 ? w : w === "loss" ? "losses" : w + "s"}`;
  const cls = (v) => (v > 0 ? "up" : v < 0 ? "dn" : "");
  const num = (v) => (v == null ? "—" : Number(v).toLocaleString("en-US", { maximumFractionDigits: 6 }));
  const pct = (v) => (v == null ? "—" : (v * 100).toFixed(1).replace(/\.0$/, "") + "%");
  const parseTime = (s) => new Date(s);
  const startOfDay = (d) => new Date(d.getFullYear(), d.getMonth(), d.getDate());
  const greeting = () => { const h = new Date().getHours(); return h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening"; };
  const localInput = (d) => { const p = (n) => String(n).padStart(2, "0"); return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`; };

  function fmtWhen(s) {
    const d = parseTime(s), today = startOfDay(new Date()), day = startOfDay(d);
    const time = d.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
    const diff = Math.round((today - day) / 86400000);
    if (diff === 0) return `Today ${time}`;
    if (diff === 1) return `Yesterday ${time}`;
    const opts = { month: "short", day: "numeric" };
    if (d.getFullYear() !== today.getFullYear()) opts.year = "numeric";
    return `${d.toLocaleDateString("en-US", opts)} ${time}`;
  }

  async function api(method, url, data) {
    const opts = { method, headers: {} };
    if (data instanceof FormData) opts.body = data;
    else if (data !== undefined) { opts.body = JSON.stringify(data); opts.headers["Content-Type"] = "application/json"; }
    const res = await fetch(url, opts);
    const json = await res.json().catch(() => ({}));
    if (!res.ok) { const err = new Error(json.error || "Something went wrong."); err.fields = json.fields || {}; throw err; }
    return json;
  }

  function toast(msg, bad = false) {
    const t = document.createElement("div");
    t.className = "toast" + (bad ? " bad" : "");
    t.textContent = msg;
    document.body.appendChild(t);
    setTimeout(() => t.remove(), 2700);
  }

  const accountById = (id) => state.accounts.find((a) => a.id === id);
  const accountName = (id) => accountById(id)?.name || "—";

  // R multiple from entry, stop and exit (null when they are missing)
  function rMultiple(t) {
    if (t.entry == null || t.stop == null || t.exit == null) return null;
    const risk = Math.abs(t.entry - t.stop);
    if (!risk) return null;
    return ((t.exit - t.entry) / risk) * (t.side === "long" ? 1 : -1);
  }
  const fmtR = (r) => (r == null ? "—" : (r > 0 ? "+" : r < 0 ? "−" : "") + Math.abs(r).toFixed(1) + "R");

  function stats(trades) {
    const wins = trades.filter((t) => t.pnl > 0), losses = trades.filter((t) => t.pnl < 0);
    const gw = wins.reduce((s, t) => s + t.pnl, 0), gl = -losses.reduce((s, t) => s + t.pnl, 0);
    const rs = trades.map(rMultiple).filter((r) => r != null);
    return {
      n: trades.length, wins: wins.length, losses: losses.length,
      net: trades.reduce((s, t) => s + t.pnl, 0),
      winRate: wins.length + losses.length ? wins.length / (wins.length + losses.length) : null,
      avgWin: wins.length ? gw / wins.length : null,
      avgLoss: losses.length ? -gl / losses.length : null,
      pf: gl ? gw / gl : null,
      avgR: rs.length ? rs.reduce((a, b) => a + b, 0) / rs.length : null,
    };
  }

  function accountStats(a) {
    const trades = state.trades.filter((t) => t.account_id === a.id).sort((x, y) => (x.traded_at < y.traded_at ? -1 : 1));
    let bal = a.start_balance, peak = bal;
    const curve = [0];
    for (const t of trades) { bal += t.pnl; peak = Math.max(peak, bal); curve.push(bal - a.start_balance); }
    const s = stats(trades);
    return { trades, curve, balance: bal, pnl: bal - a.start_balance, ddUsed: peak - bal, ...s };
  }

  function inRange(t, range) {
    if (range === "all") return true;
    const d = parseTime(t.traded_at), now = new Date(), today = startOfDay(now);
    if (range === "today") return d >= today;
    if (range === "week") { const w = new Date(today); w.setDate(w.getDate() - ((w.getDay() + 6) % 7)); return d >= w; }
    if (range === "month") return d >= new Date(now.getFullYear(), now.getMonth(), 1);
    if (range === "30") { const s = new Date(today); s.setDate(s.getDate() - 29); return d >= s; }
    return true;
  }

  function sparkline(points, w = 300, h = 60) {
    if (points.length < 2) points = [0, 0];
    const min = Math.min(...points), max = Math.max(...points);
    const d = points.map((v, i) => (i ? "L" : "M") + ((i / (points.length - 1)) * w).toFixed(1) + " " + (h - 4 - ((v - min) / (max - min || 1)) * (h - 8) - (max === min ? (h - 8) / 2 : 0)).toFixed(1)).join(" ");
    const last = points[points.length - 1];
    const col = last > 0 ? "#2bd98f" : last < 0 ? "#ff5a6e" : "rgba(255,255,255,.4)";
    return `<svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="none"><path d="${d} L${w} ${h} L0 ${h}Z" fill="${col}" fill-opacity=".07"/><path d="${d}" fill="none" stroke="${col}" stroke-width="1.6" vector-effect="non-scaling-stroke"/></svg>`;
  }

  // ------------------------------------------------------------------ data
  async function loadAll() {
    const [accounts, trades, settings, days] = await Promise.all([api("GET", "/api/accounts"), api("GET", "/api/trades"), api("GET", "/api/settings"), api("GET", "/api/days")]);
    Object.assign(state, { accounts, trades, settings, days: Object.fromEntries(days.map((d) => [d.date, d])) });
    document.querySelectorAll("[data-name]").forEach((el) => (el.textContent = settings.name));
  }

  // ------------------------------------------------------------------ router
  function route() {
    const [path, query] = (location.hash.slice(1) || "/").split("?");
    const params = new URLSearchParams(query || "");
    if (atom) { atom.stop(); atom = null; }
    const page = path.replace(/^\//, "") || "home";
    document.querySelectorAll("[data-nav]").forEach((a) => a.classList.toggle("on", a.dataset.nav === page));
    if (page === "trades") {
      if (params.has("account")) { state.filters.account = params.get("account"); state.filters.range = "all"; }
      renderTrades();
    } else if (page === "accounts") renderAccounts();
    else if (page === "daily") renderDaily();
    else renderHome();
    view.scrollTop = 0;
  }
  const rerender = () => route();
  const setTitle = (t) => (document.getElementById("page-title").textContent = t);

  // ------------------------------------------------------------------ home
  function renderHome() {
    setTitle("Overview");
    const now = new Date();
    const monthStart = new Date(now.getFullYear(), now.getMonth(), 1), lastStart = new Date(now.getFullYear(), now.getMonth() - 1, 1);
    const month = state.trades.filter((t) => parseTime(t.traded_at) >= monthStart);
    const last = state.trades.filter((t) => { const d = parseTime(t.traded_at); return d >= lastStart && d < monthStart; });
    const ms = stats(month), ls = stats(last);
    const today = state.trades.filter((t) => inRange(t, "today")), ts = stats(today);
    const active = state.accounts.filter((a) => a.status === "active");
    const funded = active.filter((a) => a.type === "funded").length, evals = active.filter((a) => a.type === "evaluation").length;

    let line;
    if (!state.accounts.length) line = "Let's get you set up. Add your first account, then log your trades.";
    else if (!today.length) line = "No trades yet today. Stay patient and wait for your setup.";
    else line = `You're ${ts.net >= 0 ? "up" : "down"} <span class="${cls(ts.net)}">${money(ts.net, true)}</span> today across ${ts.n} trade${ts.n === 1 ? "" : "s"}.`;

    const recent = state.trades.slice(0, 6);
    view.innerHTML = `
    <section class="dash">
      <div class="kpis">
        <div class="panel kpi"><div class="lbl">Net P&amp;L this month</div><div class="val ${cls(ms.net)}">${money(ms.net, true)}</div><div class="sub">Last month ${money(ls.net, true)}</div></div>
        <div class="panel kpi"><div class="lbl">Win rate this month</div><div class="val">${pct(ms.winRate)}</div><div class="sub">${plural(ms.wins, "win")} · ${plural(ms.losses, "loss")}</div></div>
        <div class="panel kpi"><div class="lbl">Profit factor</div><div class="val">${ms.pf == null ? "—" : ms.pf.toFixed(2)}</div><div class="sub">${ms.avgR == null ? "This month" : "Average " + fmtR(ms.avgR)}</div></div>
        <div class="panel kpi"><div class="lbl">Active accounts</div><div class="val">${active.length}</div><div class="sub">${funded} funded · ${evals} evaluation</div></div>
      </div>
      <div class="panel chart" style="display:flex;flex-direction:column">${equityPanel()}</div>
      <div class="core">
        <canvas id="dash-atom"></canvas>
        <div class="hello">${greeting()}, ${esc(state.settings.name)}</div>
        <div class="line">${line}</div>
        <div class="actions">${state.accounts.length ? `<button class="btn primary" data-act="log">+ Log trade</button>` : `<button class="btn primary" data-act="add-account">+ Add account</button>`}</div>
      </div>
      <div class="panel" style="display:flex;flex-direction:column">
        <div class="ph">Recent trades ${recent.length ? `<a href="#/trades">View all →</a>` : ""}</div>
        ${recent.length ? `<div class="list">${recent.map((t) => `
          <div class="it" data-trade="${t.id}">
            <b>${esc(t.symbol)} <span class="pill ${t.side === "long" ? "l" : "s"}">${t.side.toUpperCase()}</span></b><span class="r ${cls(t.pnl)}">${money(t.pnl, true)}</span>
            <span class="m">${fmtWhen(t.traded_at)} · ${esc(accountName(t.account_id))}</span><span class="m r" style="font-weight:400">${fmtR(rMultiple(t))}</span>
          </div>`).join("")}</div>` : `<div class="empty"><h3>No trades yet</h3><p>Your latest trades will show up here.</p></div>`}
      </div>
    </section>`;
    atom = createAtom(document.getElementById("dash-atom"), { scale: 0.27, centerY: 0.5, density: 0.9, follow: true });
    view.querySelectorAll("[data-trade]").forEach((el) => el.addEventListener("click", () => { state.selectedTrade = Number(el.dataset.trade); state.filters = { q: "", account: "", range: "all" }; location.hash = "#/trades"; }));
  }

  function equityPanel() {
    const start = startOfDay(new Date()); start.setDate(start.getDate() - 29);
    const window30 = state.trades.filter((t) => parseTime(t.traded_at) >= start).sort((a, b) => (a.traded_at < b.traded_at ? -1 : 1));
    if (!window30.length) return `<div class="ph">P&amp;L <span>Last 30 days</span></div><div class="empty"><p>Your P&amp;L curve appears here once you log trades.</p></div>`;
    let cum = 0; const pts = [0, ...window30.map((t) => (cum += t.pnl))];
    const min = Math.min(...pts), max = Math.max(...pts), W = 400, H = 260;
    const xy = pts.map((v, i) => [(i / (pts.length - 1)) * W, H - 12 - ((v - min) / (max - min || 1)) * (H - 24)]);
    const d = xy.map(([x, y], i) => (i ? "L" : "M") + x.toFixed(1) + " " + y.toFixed(1)).join(" ");
    const col = cum >= 0 ? "#2bd98f" : "#ff5a6e";
    const zeroY = H - 12 - ((0 - min) / (max - min || 1)) * (H - 24);
    return `<div class="ph">P&amp;L <span>Last 30 days</span></div>
      <div style="flex:1;min-height:0"><svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">
        <defs><linearGradient id="eq" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="${col}" stop-opacity=".22"/><stop offset="1" stop-color="${col}" stop-opacity="0"/></linearGradient></defs>
        <line x1="0" y1="${zeroY}" x2="${W}" y2="${zeroY}" stroke="rgba(255,255,255,.08)" stroke-dasharray="3 4" vector-effect="non-scaling-stroke"/>
        <path d="${d} L${W} ${H} L0 ${H}Z" fill="url(#eq)"/>
        <path d="${d}" fill="none" stroke="${col}" stroke-width="2" vector-effect="non-scaling-stroke"/>
      </svg></div>
      <div class="chart-labels"><span>${start.toLocaleDateString("en-US", { month: "short", day: "numeric" })} · $0</span><span class="${cls(cum)}" style="font-weight:600">${money(cum, true)}</span></div>`;
  }

  // ------------------------------------------------------------------ trades
  function filteredTrades() {
    const f = state.filters, q = f.q.trim().toLowerCase();
    return state.trades.filter((t) => {
      if (f.account && String(t.account_id) !== String(f.account)) return false;
      if (!inRange(t, f.range)) return false;
      if (q) {
        const hay = [t.symbol, t.setup, t.notes, t.side, accountName(t.account_id), ...(t.tags || [])].join(" ").toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });
  }

  function renderTrades() {
    setTitle("Trades");
    if (!state.accounts.length) {
      view.innerHTML = `<section class="page"><div class="panel" style="flex:1"><div class="empty"><h3>Add an account first</h3><p>Every trade belongs to an account. Add one, then start logging trades.</p><button class="btn primary" data-act="add-account">+ Add account</button></div></div></section>`;
      return;
    }
    const f = state.filters;
    view.innerHTML = `
    <section class="page">
      <div class="toolbar">
        <label class="field search">⌕&nbsp;<input id="q" placeholder="Search symbol, setup, notes, tags" value="${esc(f.q)}"></label>
        <label class="field"><span class="k">Account</span><select id="f-account"><option value="">All</option>${state.accounts.map((a) => `<option value="${a.id}" ${String(a.id) === String(f.account) ? "selected" : ""}>${esc(a.name)}</option>`).join("")}</select></label>
        <label class="field"><span class="k">Date</span><select id="f-range">${[["today", "Today"], ["week", "This week"], ["month", "This month"], ["30", "Last 30 days"], ["all", "All time"]].map(([v, l]) => `<option value="${v}" ${f.range === v ? "selected" : ""}>${l}</option>`).join("")}</select></label>
        <div class="grow"></div>
        <button class="btn primary" data-act="log">+ Log trade</button>
      </div>
      <div class="stats" id="trade-stats"></div>
      <div class="split">
        <div class="panel table-panel" id="trade-table"></div>
        <div class="panel detail" id="trade-detail"></div>
      </div>
    </section>`;
    const q = document.getElementById("q");
    q.addEventListener("input", () => { f.q = q.value; fillTrades(); });
    document.getElementById("f-account").addEventListener("change", (e) => { f.account = e.target.value; fillTrades(); });
    document.getElementById("f-range").addEventListener("change", (e) => { f.range = e.target.value; fillTrades(); });
    fillTrades();
  }

  function fillTrades() {
    const list = filteredTrades(), s = stats(list);
    document.getElementById("trade-stats").innerHTML = `
      <div class="panel kpi"><div class="lbl">Net P&amp;L</div><div class="val ${cls(s.net)}">${money(s.net, true)}</div><div class="sub">${s.n} trade${s.n === 1 ? "" : "s"}</div></div>
      <div class="panel kpi"><div class="lbl">Win rate</div><div class="val">${pct(s.winRate)}</div><div class="sub">${plural(s.wins, "win")} · ${plural(s.losses, "loss")}</div></div>
      <div class="panel kpi"><div class="lbl">Avg win</div><div class="val ${s.avgWin ? "up" : ""}">${s.avgWin == null ? "—" : money(s.avgWin, true)}</div><div class="sub">Profit factor ${s.pf == null ? "—" : s.pf.toFixed(2)}</div></div>
      <div class="panel kpi"><div class="lbl">Avg loss</div><div class="val ${s.avgLoss ? "dn" : ""}">${s.avgLoss == null ? "—" : money(s.avgLoss, true)}</div><div class="sub">Average ${fmtR(s.avgR)}</div></div>`;
    const table = document.getElementById("trade-table");
    if (!list.length) {
      table.innerHTML = `<div class="empty"><h3>${state.trades.length ? "No trades match" : "No trades yet"}</h3><p>${state.trades.length ? "Try a different search, account or date range." : "Log your first trade to start your journal."}</p>${state.trades.length ? "" : `<button class="btn primary" data-act="log">+ Log trade</button>`}</div>`;
      state.selectedTrade = null;
    } else {
      if (!list.some((t) => t.id === state.selectedTrade)) state.selectedTrade = list[0].id;
      table.innerHTML = `<table class="tbl"><thead><tr><th>Date</th><th>Symbol</th><th>Side</th><th>Setup</th><th>Account</th><th class="r">R</th><th class="r">P&amp;L</th></tr></thead><tbody>
        ${list.map((t) => `<tr data-id="${t.id}" class="${t.id === state.selectedTrade ? "sel" : ""}">
          <td class="m">${fmtWhen(t.traded_at)}</td><td style="font-weight:600">${esc(t.symbol)}</td>
          <td><span class="pill ${t.side === "long" ? "l" : "s"}">${t.side.toUpperCase()}</span></td>
          <td>${esc(t.setup || "—")}</td><td class="m">${esc(accountName(t.account_id))}</td>
          <td class="r m">${fmtR(rMultiple(t))}</td>
          <td class="r ${cls(t.pnl)}" style="font-weight:600">${money(t.pnl, true)}</td></tr>`).join("")}
      </tbody></table>`;
      table.querySelectorAll("tbody tr").forEach((tr) => tr.addEventListener("click", () => {
        state.selectedTrade = Number(tr.dataset.id);
        table.querySelectorAll("tr.sel").forEach((x) => x.classList.remove("sel"));
        tr.classList.add("sel");
        fillDetail();
      }));
    }
    fillDetail();
  }

  function fillDetail() {
    const el = document.getElementById("trade-detail");
    const t = state.trades.find((x) => x.id === state.selectedTrade);
    if (!t) { el.innerHTML = `<div class="empty"><p>Select a trade to see its details.</p></div>`; return; }
    const r = rMultiple(t), d = parseTime(t.traded_at);
    const shots = t.screenshots || [];
    el.innerHTML = `
      <div class="head">
        <div><div class="sym">${esc(t.symbol)} <span class="pill ${t.side === "long" ? "l" : "s"}" style="vertical-align:middle">${t.side.toUpperCase()}</span></div>
          <div class="muted" style="font-size:13px;margin-top:2px">${d.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric", year: "numeric" })}, ${d.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" })}${t.setup ? " · " + esc(t.setup) : ""}</div></div>
        <div class="pnl ${cls(t.pnl)}">${money(t.pnl, true)}</div>
      </div>
      ${shots.length ? `<div class="shot" id="main-shot"><img src="${shots[0].url}" alt="Chart screenshot"></div>
        ${shots.length > 1 ? `<div class="thumbs">${shots.map((s, i) => `<img src="${s.url}" data-i="${i}" class="${i ? "" : "on"}" alt="">`).join("")}</div>` : ""}`
        : `<div class="shot none">No screenshot. Edit the trade to add one.</div>`}
      <div class="kv">
        <div><div class="k">Entry</div><div class="v">${num(t.entry)}</div></div>
        <div><div class="k">Stop</div><div class="v">${num(t.stop)}</div></div>
        <div><div class="k">Exit</div><div class="v">${num(t.exit)}</div></div>
        <div><div class="k">Contracts</div><div class="v">${num(t.contracts)}</div></div>
        <div><div class="k">R multiple</div><div class="v ${cls(r || 0)}">${fmtR(r)}</div></div>
        <div><div class="k">Account</div><div class="v">${esc(accountName(t.account_id))}</div></div>
      </div>
      ${t.notes ? `<div class="notes">${esc(t.notes)}</div>` : ""}
      ${t.tags?.length ? `<div class="tags">${t.tags.map((x) => `<span>${esc(x)}</span>`).join("")}</div>` : ""}
      <div class="btns"><button class="btn small" data-edit>Edit</button><button class="btn small danger" data-del>Delete</button></div>`;
    let current = 0;
    el.querySelector("#main-shot")?.addEventListener("click", () => openViewer(shots[current].url));
    el.querySelectorAll(".thumbs img").forEach((img) => img.addEventListener("click", () => {
      current = Number(img.dataset.i);
      el.querySelector("#main-shot img").src = shots[current].url;
      el.querySelectorAll(".thumbs img").forEach((x) => x.classList.toggle("on", x === img));
    }));
    el.querySelector("[data-edit]").addEventListener("click", () => tradeForm(t));
    el.querySelector("[data-del]").addEventListener("click", () => confirmBox("Delete this trade?", `${esc(t.symbol)} ${t.side} · ${money(t.pnl, true)}. This can't be undone.`, "Delete trade", async () => {
      await api("DELETE", `/api/trades/${t.id}`);
      state.trades = state.trades.filter((x) => x.id !== t.id);
      toast("Trade deleted");
      rerender();
    }));
  }

  function openViewer(url) {
    const v = document.createElement("div");
    v.className = "viewer";
    v.innerHTML = `<img src="${url}" alt="">`;
    v.addEventListener("click", () => v.remove());
    document.body.appendChild(v);
  }

  // ------------------------------------------------------------------ accounts
  function renderAccounts() {
    setTitle("Accounts");
    const show = state.accountShow;
    const list = state.accounts.filter((a) => show === "all" || (show === "active" ? a.status === "active" : a.status !== "closed"))
      .map((a) => ({ a, s: accountStats(a) }));
    const active = state.accounts.filter((a) => a.status === "active").map((a) => accountStats(a));
    const totalPnl = state.accounts.reduce((sum, a) => sum + accountStats(a).pnl, 0);
    view.innerHTML = `
    <section class="page">
      <div class="toolbar">
        <label class="field"><span class="k">Show</span><select id="show">${[["recent", "All except closed"], ["active", "Active only"], ["all", "Everything"]].map(([v, l]) => `<option value="${v}" ${show === v ? "selected" : ""}>${l}</option>`).join("")}</select></label>
        ${state.accounts.length ? `<div class="summary-line"><b>${active.length}</b> active &nbsp;·&nbsp; <b>${money(active.reduce((s, x) => s + x.balance, 0))}</b> combined &nbsp;·&nbsp; <b class="${cls(totalPnl)}">${money(totalPnl, true)}</b> total P&amp;L</div>` : ""}
        <div class="grow"></div>
        <button class="btn primary" data-act="add-account">+ Add account</button>
      </div>
      ${list.length ? `<div class="cards">${list.map(({ a, s }) => accountCard(a, s)).join("")}</div>`
        : `<div class="panel" style="flex:1"><div class="empty"><h3>${state.accounts.length ? "Nothing to show" : "No accounts yet"}</h3><p>${state.accounts.length ? "Change the filter to see your other accounts." : "Add your evaluation, funded or personal accounts so you can log trades to them."}</p>${state.accounts.length ? "" : `<button class="btn primary" data-act="add-account">+ Add account</button>`}</div></div>`}
    </section>`;
    document.getElementById("show").addEventListener("change", (e) => { state.accountShow = e.target.value; renderAccounts(); });
    view.querySelectorAll(".acct").forEach((card) => card.addEventListener("click", (e) => {
      const a = accountById(Number(card.dataset.id));
      if (e.target.closest("[data-edit]")) return accountForm(a);
      location.hash = `#/trades?account=${a.id}`;
    }));
  }

  function accountCard(a, s) {
    const pill = a.status === "passed" ? "l" : a.status === "breached" ? "s" : "n";
    const typeLabel = { evaluation: "Evaluation", funded: "Funded", personal: "Personal" }[a.type];
    let prog = "";
    if (a.type === "evaluation" && a.profit_target && a.status !== "breached") {
      const p = Math.max(0, Math.min(1, s.pnl / a.profit_target));
      prog = progress("Profit target", `${money(Math.max(0, s.pnl))} of ${money(a.profit_target)}`, p, a.status === "passed" || p >= 1 ? "var(--green)" : "");
    } else if (a.max_drawdown) {
      const left = Math.max(0, a.max_drawdown - s.ddUsed);
      prog = a.status === "breached"
        ? progress("Drawdown used", `${money(Math.min(s.ddUsed, a.max_drawdown))} of ${money(a.max_drawdown)}`, 1, "var(--red)")
        : progress("Drawdown left", `${money(left)} of ${money(a.max_drawdown)}`, left / a.max_drawdown, left / a.max_drawdown < 0.25 ? "var(--red)" : "");
    }
    return `
    <div class="panel acct ${a.status === "breached" || a.status === "closed" ? "dead" : ""}" data-id="${a.id}">
      <div class="row1">
        <div><div class="name">${esc(a.name)}</div><div class="firm">${a.firm ? esc(a.firm) + " · " : ""}${typeLabel}</div></div>
        <div class="right"><button class="btn small edit" data-edit>Edit</button><span class="pill ${pill}">${a.status.toUpperCase()}</span></div>
      </div>
      <div class="bal"><span class="big">${money(s.balance)}</span><span class="pnl ${cls(s.pnl)}">${money(s.pnl, true)}</span></div>
      <div class="spark">${sparkline(s.curve)}</div>
      ${prog}
      <div class="prog" style="margin-top:14px"><span>${s.n} trade${s.n === 1 ? "" : "s"}${s.winRate == null ? "" : " · " + pct(s.winRate) + " win rate"}</span><span>View trades →</span></div>
    </div>`;
  }
  const progress = (label, value, frac, color) =>
    `<div class="prog"><span>${label}</span><span>${value}</span></div><div class="barline"><i style="width:${(Math.max(0, Math.min(1, frac)) * 100).toFixed(1)}%;${color ? "background:" + color : ""}"></i></div>`;


  // ------------------------------------------------------------------ daily tasks + journal
  const TASKS = { trading: "Trading", reading: "Read 20+ pages", gym: "Gym 1+ hour" };
  const ymd = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  const fromYmd = (s) => { const [y, m, d] = s.split("-").map(Number); return new Date(y, m - 1, d); };

  // Days the US stock market is closed (NYSE holiday rules), as { "YYYY-MM-DD": "Name" }.
  const holidayCache = {};
  function marketHolidays(year) {
    if (holidayCache[year]) return holidayCache[year];
    const out = {};
    const nth = (month, weekday, n) => { const d = new Date(year, month, 1); d.setDate(1 + ((weekday - d.getDay() + 7) % 7) + (n - 1) * 7); return d; };
    const last = (month, weekday) => { const d = new Date(year, month + 1, 0); d.setDate(d.getDate() - ((d.getDay() - weekday + 7) % 7)); return d; };
    const fixed = (month, day, name) => {
      const d = new Date(year, month, day);
      if (d.getDay() === 6) d.setDate(d.getDate() - 1);       // Saturday: closed the Friday before
      else if (d.getDay() === 0) d.setDate(d.getDate() + 1);  // Sunday: closed the Monday after
      if (d.getFullYear() === year) out[ymd(d)] = name;       // (a Saturday New Year's Day is not observed)
    };
    // Easter Sunday (Gregorian), for Good Friday
    const a = year % 19, b = Math.floor(year / 100), c = year % 100, d = Math.floor(b / 4), e = b % 4, f = Math.floor((b + 8) / 25);
    const g = Math.floor((b - f + 1) / 3), h = (19 * a + b - d - g + 15) % 30, i = Math.floor(c / 4), k = c % 4;
    const l = (32 + 2 * e + 2 * i - h - k) % 7, m = Math.floor((a + 11 * h + 22 * l) / 451);
    const easter = new Date(year, Math.floor((h + l - 7 * m + 114) / 31) - 1, ((h + l - 7 * m + 114) % 31) + 1);
    const goodFriday = new Date(easter); goodFriday.setDate(easter.getDate() - 2);

    fixed(0, 1, "New Year's Day");
    out[ymd(nth(0, 1, 3))] = "Martin Luther King Jr. Day";
    out[ymd(nth(1, 1, 3))] = "Presidents' Day";
    out[ymd(goodFriday)] = "Good Friday";
    out[ymd(last(4, 1))] = "Memorial Day";
    fixed(5, 19, "Juneteenth");
    fixed(6, 4, "Independence Day");
    out[ymd(nth(8, 1, 1))] = "Labor Day";
    out[ymd(nth(10, 4, 4))] = "Thanksgiving";
    fixed(11, 25, "Christmas Day");
    return (holidayCache[year] = out);
  }
  const holidayName = (date) => marketHolidays(date.getFullYear())[ymd(date)] || null;
  // Weekdays: trading + reading + gym. Weekends and market holidays: no trading.
  function tasksFor(date) {
    const weekend = date.getDay() === 0 || date.getDay() === 6;
    return weekend || holidayName(date) ? ["reading", "gym"] : ["trading", "reading", "gym"];
  }
  const dayDone = (key) => state.days[key]?.done || [];
  const dayComplete = (date) => { const done = dayDone(ymd(date)); return tasksFor(date).every((t) => done.includes(t)); };

  function dailyStreak() {
    const d = startOfDay(new Date());
    if (!dayComplete(d)) d.setDate(d.getDate() - 1); // today still in progress doesn't break the streak
    let n = 0;
    while (dayComplete(d)) { n++; d.setDate(d.getDate() - 1); }
    return n;
  }

  function renderDaily() {
    setTitle("Daily");
    const today = startOfDay(new Date());
    if (!state.daily.month) state.daily.month = new Date(today.getFullYear(), today.getMonth(), 1);
    if (!state.daily.selected) state.daily.selected = ymd(today);
    view.innerHTML = `
    <section class="page">
      <div class="toolbar">
        <button class="btn" data-month="-1" aria-label="Previous month">‹</button>
        <div class="month-name" id="month-name"></div>
        <button class="btn" data-month="1" aria-label="Next month">›</button>
        <button class="btn" data-month="0">Today</button>
        <div class="grow"></div>
      </div>
      <div class="stats" id="daily-stats"></div>
      <div class="split daily-split">
        <div class="panel"><div class="cal" id="cal"></div></div>
        <div class="panel detail" id="day-panel"></div>
      </div>
    </section>`;
    view.querySelectorAll("[data-month]").forEach((b) => b.addEventListener("click", () => {
      const step = Number(b.dataset.month), m = state.daily.month;
      if (step === 0) { state.daily.month = new Date(today.getFullYear(), today.getMonth(), 1); state.daily.selected = ymd(today); paintDay(); }
      else state.daily.month = new Date(m.getFullYear(), m.getMonth() + step, 1);
      paintCalendar(); paintDailyStats();
    }));
    paintCalendar(); paintDailyStats(); paintDay();
  }

  function paintDailyStats() {
    const el = document.getElementById("daily-stats");
    if (!el) return;
    const m = state.daily.month, today = startOfDay(new Date());
    const counts = { trading: [0, 0], reading: [0, 0], gym: [0, 0] };
    for (const d = new Date(m); d.getMonth() === m.getMonth() && d <= today; d.setDate(d.getDate() + 1)) {
      const done = dayDone(ymd(d));
      for (const t of tasksFor(d)) { counts[t][1]++; if (done.includes(t)) counts[t][0]++; }
    }
    const streak = dailyStreak();
    const tile = (label, [n, of]) => `<div class="panel kpi"><div class="lbl">${label}</div><div class="val">${n}<span class="of"> / ${of}</span></div>
      <div class="barline"><i style="width:${of ? (n / of) * 100 : 0}%"></i></div></div>`;
    el.innerHTML = `
      <div class="panel kpi"><div class="lbl">Current streak</div><div class="val ${streak ? "up" : ""}">${streak}<span class="of"> day${streak === 1 ? "" : "s"}</span></div><div class="sub">Days with every task done</div></div>
      ${tile("Trading days", counts.trading)}${tile("Reading days", counts.reading)}${tile("Gym days", counts.gym)}`;
  }

  function paintCalendar() {
    const el = document.getElementById("cal");
    if (!el) return;
    const m = state.daily.month, today = startOfDay(new Date()), todayKey = ymd(today);
    document.getElementById("month-name").textContent = m.toLocaleDateString("en-US", { month: "long", year: "numeric" });
    const first = new Date(m); first.setDate(1 - ((m.getDay() + 6) % 7)); // start on Monday
    let html = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map((d) => `<div class="dow">${d}</div>`).join("");
    for (let i = 0; i < 42; i++) {
      const d = new Date(first); d.setDate(first.getDate() + i);
      if (i >= 35 && d.getMonth() !== m.getMonth()) break; // skip an empty sixth week
      const key = ymd(d), tasks = tasksFor(d), done = dayDone(key), hol = holidayName(d);
      const complete = tasks.every((t) => done.includes(t)), past = d < today;
      const classes = ["day", d.getMonth() !== m.getMonth() ? "out" : "", key === todayKey ? "today" : "", key === state.daily.selected ? "sel" : "",
        complete ? "complete" : past && d.getMonth() === m.getMonth() ? "missed" : "", d > today ? "future" : ""].join(" ");
      html += `<div class="${classes}" data-day="${key}">
        <div class="n">${d.getDate()}${state.days[key]?.journal ? `<span class="pen" title="Has a journal entry">✎</span>` : ""}</div>
        ${hol ? `<div class="hol">${esc(hol)}</div>` : ""}
        <div class="dots">${tasks.map((t) => `<i class="${done.includes(t) ? "on" : ""}" title="${TASKS[t]}"></i>`).join("")}</div>
      </div>`;
    }
    el.innerHTML = html;
    el.querySelectorAll("[data-day]").forEach((c) => c.addEventListener("click", () => { state.daily.selected = c.dataset.day; paintCalendar(); paintDay(); }));
  }

  let journalTimer = null;
  function paintDay() {
    const el = document.getElementById("day-panel");
    if (!el) return;
    clearTimeout(journalTimer);
    const key = state.daily.selected, date = fromYmd(key), today = startOfDay(new Date());
    const tasks = tasksFor(date), hol = holidayName(date), future = date > today;
    const weekend = date.getDay() === 0 || date.getDay() === 6;
    const entry = state.days[key] || { done: [], journal: "" };
    el.innerHTML = `
      <div class="head"><div>
        <div class="sym">${date.toLocaleDateString("en-US", { weekday: "long" })}</div>
        <div class="muted" style="font-size:13px;margin-top:2px">${date.toLocaleDateString("en-US", { month: "long", day: "numeric", year: "numeric" })}${hol ? ` · ${esc(hol)}, market closed` : weekend ? " · Weekend" : ""}</div>
      </div><div class="day-count" id="day-count"></div></div>
      <div class="checks">${tasks.map((t) => `
        <label class="check ${future ? "off" : ""}"><input type="checkbox" data-task="${t}" ${entry.done.includes(t) ? "checked" : ""} ${future ? "disabled" : ""}><span class="box"></span><span>${TASKS[t]}</span></label>`).join("")}
      </div>
      <div class="ph" style="margin:6px 0 -8px">Journal <span id="journal-status"></span></div>
      <textarea id="day-journal" class="day-journal" placeholder="${future ? "This day hasn't happened yet." : "How did today go? What did you read, how was the gym, how did you feel?"}" ${future ? "disabled" : ""}>${esc(entry.journal)}</textarea>`;
    const count = () => { const n = tasks.filter((t) => dayDone(key).includes(t)).length; const c = document.getElementById("day-count"); c.textContent = `${n} / ${tasks.length}`; c.classList.toggle("up", n === tasks.length); };
    count();
    const area = el.querySelector("#day-journal"), status = el.querySelector("#journal-status");
    const save = async () => {
      clearTimeout(journalTimer);
      const done = [...el.querySelectorAll("[data-task]:checked")].map((c) => c.dataset.task);
      try {
        const saved = await api("PUT", `/api/days/${key}`, { done, journal: area.value });
        if (saved.done.length || saved.journal) state.days[key] = saved; else delete state.days[key];
        status.textContent = "Saved";
        count(); paintCalendar(); paintDailyStats();
      } catch (err) { status.textContent = ""; toast(err.message, true); }
    };
    el.querySelectorAll("[data-task]").forEach((c) => c.addEventListener("change", save));
    area.addEventListener("input", () => { status.textContent = "Saving…"; clearTimeout(journalTimer); journalTimer = setTimeout(save, 700); });
    area.addEventListener("blur", () => { if (status.textContent === "Saving…") save(); });
  }

  // ------------------------------------------------------------------ modals
  function openModal(html, width) {
    modalRoot.innerHTML = `<div class="scrim"><div class="modal" ${width ? `style="width:${width}px"` : ""}>${html}</div></div>`;
    const scrim = modalRoot.firstElementChild;
    const close = () => { modalRoot.innerHTML = ""; document.removeEventListener("keydown", onKey); document.removeEventListener("paste", onPasteProxy); };
    const onKey = (e) => { if (e.key === "Escape") close(); };
    let pasteHandler = null;
    const onPasteProxy = (e) => pasteHandler && pasteHandler(e);
    document.addEventListener("keydown", onKey);
    document.addEventListener("paste", onPasteProxy);
    scrim.addEventListener("mousedown", (e) => { if (e.target === scrim) close(); });
    scrim.querySelectorAll("[data-close]").forEach((b) => b.addEventListener("click", close));
    return { el: scrim.querySelector(".modal"), close, onPaste: (fn) => (pasteHandler = fn) };
  }

  function showErrors(el, err) {
    el.querySelectorAll(".f").forEach((f) => { f.classList.remove("bad"); f.querySelector(".err")?.remove(); });
    let shown = false;
    for (const [name, msg] of Object.entries(err.fields || {})) {
      const input = el.querySelector(`[name="${name}"]`) || el.querySelector(`[data-field="${name}"]`);
      const f = input?.closest(".f");
      if (f) { f.classList.add("bad"); f.insertAdjacentHTML("beforeend", `<div class="err">${esc(msg)}</div>`); shown = true; }
    }
    const box = el.querySelector(".form-error");
    box.textContent = shown ? "" : err.message;
  }

  function confirmBox(title, text, okLabel, onOk) {
    const m = openModal(`<h2>${title}</h2><p>${text}</p><div class="form-error"></div><div class="actions"><button class="btn" data-close>Cancel</button><button class="btn primary danger" style="background:var(--red);border-color:var(--red);color:#000" data-ok>${okLabel}</button></div>`);
    m.el.classList.add("confirm");
    m.el.querySelector("[data-ok]").addEventListener("click", async (e) => {
      e.target.disabled = true;
      try { await onOk(); m.close(); } catch (err) { m.el.querySelector(".form-error").textContent = err.message; e.target.disabled = false; }
    });
  }

  function tradeForm(t) {
    const editing = !!t;
    const lastAccount = (() => { try { return localStorage.getItem("lastAccount"); } catch { return null; } })();
    const usable = state.accounts.filter((a) => a.status !== "closed" || (t && a.id === t.account_id));
    const accountId = t?.account_id ?? (usable.find((a) => String(a.id) === lastAccount && a.status === "active") || usable.find((a) => a.status === "active") || usable[0])?.id;
    const symbols = [...new Set(state.trades.map((x) => x.symbol))].slice(0, 30);
    const setups = [...new Set(state.trades.map((x) => x.setup).filter(Boolean))].slice(0, 30);
    let side = t?.side || "long";
    const newFiles = [], removed = new Set();
    const m = openModal(`
      <h2>${editing ? "Edit trade" : "Log a trade"} <small data-close>✕</small></h2>
      <form class="form" autocomplete="off">
        <div class="f w2"><label>Account</label><select name="account_id">${usable.map((a) => `<option value="${a.id}" ${a.id === accountId ? "selected" : ""}>${esc(a.name)}${a.status !== "active" ? " (" + a.status + ")" : ""}</option>`).join("")}</select></div>
        <div class="f w2"><label>Date &amp; time</label><input type="datetime-local" name="traded_at" value="${t?.traded_at || localInput(new Date())}"></div>
        <div class="f"><label>Symbol</label><input name="symbol" list="dl-symbols" placeholder="NQ" value="${esc(t?.symbol || "")}"></div>
        <div class="f"><label>Side</label><div class="seg" data-field="side"><span data-side="long">Long</span><span data-side="short">Short</span></div></div>
        <div class="f"><label>Contracts</label><input name="contracts" inputmode="decimal" placeholder="1" value="${t?.contracts ?? ""}"></div>
        <div class="f"><label>Setup</label><input name="setup" list="dl-setups" placeholder="ORB break" value="${esc(t?.setup || "")}"></div>
        <div class="f"><label>Entry</label><input name="entry" inputmode="decimal" placeholder="Price" value="${t?.entry ?? ""}"></div>
        <div class="f"><label>Stop</label><input name="stop" inputmode="decimal" placeholder="Price" value="${t?.stop ?? ""}"></div>
        <div class="f"><label>Exit</label><input name="exit" inputmode="decimal" placeholder="Price" value="${t?.exit ?? ""}"></div>
        <div class="f"><label>P&amp;L ($)</label><input name="pnl" inputmode="decimal" placeholder="e.g. 390 or -180" value="${t ? t.pnl : ""}"></div>
        <div class="f w4"><label>Notes</label><textarea name="notes" placeholder="Why did you take it? What did you do well, and what would you change?">${esc(t?.notes || "")}</textarea></div>
        <div class="f w4"><label>Tags</label><input name="tags" placeholder="A+ setup, followed plan, FOMO" value="${esc((t?.tags || []).join(", "))}"></div>
        <div class="f w4" data-field="screenshots"><label>Screenshots</label>
          <div class="shots-row" id="shots"></div>
          <div class="drop" id="drop">Drop chart screenshots here, paste them, or click to upload</div>
          <input type="file" id="file" accept="image/png,image/jpeg,image/gif,image/webp" multiple hidden>
        </div>
        <datalist id="dl-symbols">${symbols.map((s) => `<option value="${esc(s)}">`).join("")}</datalist>
        <datalist id="dl-setups">${setups.map((s) => `<option value="${esc(s)}">`).join("")}</datalist>
      </form>
      <div class="form-error"></div>
      <div class="actions"><button class="btn" data-close>Cancel</button><button class="btn primary" data-save>${editing ? "Save changes" : "Save trade"}</button></div>`, 680);
    const el = m.el;
    const segs = el.querySelectorAll("[data-side]");
    const paintSide = () => segs.forEach((s) => { s.className = s.dataset.side === side ? `on ${side === "long" ? "l" : "s"}` : ""; });
    segs.forEach((s) => s.addEventListener("click", () => { side = s.dataset.side; paintSide(); }));
    paintSide();

    const shotsEl = el.querySelector("#shots");
    const paintShots = () => {
      const existing = (t?.screenshots || []).filter((s) => !removed.has(s.id));
      shotsEl.innerHTML = existing.map((s) => `<div class="s"><img src="${s.url}" alt=""><button type="button" data-rm="${s.id}">✕</button></div>`).join("")
        + newFiles.map((f, i) => `<div class="s"><img src="${URL.createObjectURL(f)}" alt=""><button type="button" data-rmnew="${i}">✕</button></div>`).join("");
      shotsEl.querySelectorAll("[data-rm]").forEach((b) => b.addEventListener("click", () => { removed.add(Number(b.dataset.rm)); paintShots(); }));
      shotsEl.querySelectorAll("[data-rmnew]").forEach((b) => b.addEventListener("click", () => { newFiles.splice(Number(b.dataset.rmnew), 1); paintShots(); }));
    };
    const addFiles = (files) => { for (const f of files) if (f.type.startsWith("image/")) newFiles.push(f); paintShots(); };
    paintShots();
    const drop = el.querySelector("#drop"), file = el.querySelector("#file");
    drop.addEventListener("click", () => file.click());
    file.addEventListener("change", () => { addFiles(file.files); file.value = ""; });
    drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("over"); });
    drop.addEventListener("dragleave", () => drop.classList.remove("over"));
    drop.addEventListener("drop", (e) => { e.preventDefault(); drop.classList.remove("over"); addFiles(e.dataTransfer.files); });
    m.onPaste((e) => { const files = [...(e.clipboardData?.files || [])]; if (files.length) { e.preventDefault(); addFiles(files); } });

    const save = el.querySelector("[data-save]");
    const submit = async () => {
      const fd = new FormData(el.querySelector("form"));
      fd.set("side", side);
      newFiles.forEach((f) => fd.append("screenshots", f, f.name || "screenshot.png"));
      if (removed.size) fd.set("remove_screenshots", [...removed].join(","));
      save.disabled = true;
      try {
        const saved = await api(editing ? "PUT" : "POST", editing ? `/api/trades/${t.id}` : "/api/trades", fd);
        try { localStorage.setItem("lastAccount", String(saved.account_id)); } catch { /* storage unavailable */ }
        state.trades = state.trades.filter((x) => x.id !== saved.id).concat(saved).sort((a, b) => (a.traded_at < b.traded_at ? 1 : a.traded_at > b.traded_at ? -1 : b.id - a.id));
        state.selectedTrade = saved.id;
        m.close();
        toast(editing ? "Trade updated" : "Trade saved");
        if (!editing && !location.hash.startsWith("#/trades")) location.hash = "#/trades";
        else rerender();
      } catch (err) { showErrors(el, err); save.disabled = false; }
    };
    save.addEventListener("click", submit);
    el.querySelector("form").addEventListener("submit", (e) => { e.preventDefault(); submit(); });
    el.querySelector(editing ? "[name=pnl]" : "[name=symbol]").focus();
  }

  function accountForm(a) {
    const editing = !!a;
    let type = a?.type || "funded";
    const m = openModal(`
      <h2>${editing ? "Edit account" : "Add account"} <small data-close>✕</small></h2>
      <form class="form" autocomplete="off">
        <div class="f w4"><label>Name</label><input name="name" placeholder="Apex 150K #1" value="${esc(a?.name || "")}"></div>
        <div class="f w2"><label>Firm or broker</label><input name="firm" placeholder="Apex Trader Funding" value="${esc(a?.firm || "")}"></div>
        <div class="f w2"><label>Type</label><div class="seg" data-field="type"><span data-type="evaluation">Evaluation</span><span data-type="funded">Funded</span><span data-type="personal">Personal</span></div></div>
        <div class="f w2"><label>Starting balance ($)</label><input name="start_balance" inputmode="decimal" placeholder="150,000" value="${a?.start_balance ?? ""}"></div>
        <div class="f w2"><label>Status</label><select name="status">${["active", "passed", "breached", "closed"].map((s) => `<option value="${s}" ${(a?.status || "active") === s ? "selected" : ""}>${s[0].toUpperCase() + s.slice(1)}</option>`).join("")}</select></div>
        <div class="f w2"><label>Profit target ($)</label><input name="profit_target" inputmode="decimal" placeholder="Optional" value="${a?.profit_target ?? ""}"></div>
        <div class="f w2"><label>Max drawdown ($)</label><input name="max_drawdown" inputmode="decimal" placeholder="Optional" value="${a?.max_drawdown ?? ""}"></div>
        <div class="f w4"><label>Notes</label><textarea name="notes" placeholder="Rules for this account, anything to remember">${esc(a?.notes || "")}</textarea></div>
      </form>
      <div class="form-error"></div>
      <div class="actions">${editing ? `<button class="btn danger" data-del>Delete</button>` : ""}<div class="grow"></div><button class="btn" data-close>Cancel</button><button class="btn primary" data-save>${editing ? "Save changes" : "Save account"}</button></div>`, 580);
    const el = m.el;
    const segs = el.querySelectorAll("[data-type]");
    const paint = () => segs.forEach((s) => s.classList.toggle("on", s.dataset.type === type));
    segs.forEach((s) => s.addEventListener("click", () => { type = s.dataset.type; paint(); }));
    paint();
    const save = el.querySelector("[data-save]");
    const submit = async () => {
      const data = Object.fromEntries(new FormData(el.querySelector("form")));
      data.type = type;
      save.disabled = true;
      try {
        const saved = await api(editing ? "PUT" : "POST", editing ? `/api/accounts/${a.id}` : "/api/accounts", data);
        state.accounts = state.accounts.filter((x) => x.id !== saved.id).concat(saved).sort((x, y) => x.id - y.id);
        m.close();
        toast(editing ? "Account updated" : "Account added");
        rerender();
      } catch (err) { showErrors(el, err); save.disabled = false; }
    };
    save.addEventListener("click", submit);
    el.querySelector("form").addEventListener("submit", (e) => { e.preventDefault(); submit(); });
    el.querySelector("[data-del]")?.addEventListener("click", () => {
      const n = state.trades.filter((t) => t.account_id === a.id).length;
      m.close();
      confirmBox("Delete this account?", `${esc(a.name)} and its ${n} trade${n === 1 ? "" : "s"} will be deleted. This can't be undone.`, "Delete account", async () => {
        await api("DELETE", `/api/accounts/${a.id}`);
        state.accounts = state.accounts.filter((x) => x.id !== a.id);
        state.trades = state.trades.filter((t) => t.account_id !== a.id);
        if (String(state.filters.account) === String(a.id)) state.filters.account = "";
        toast("Account deleted");
        rerender();
      });
    });
    el.querySelector("[name=name]").focus();
  }

  function settingsForm() {
    const m = openModal(`
      <h2>Settings <small data-close>✕</small></h2>
      <form class="form"><div class="f w4"><label>Your name</label><input name="name" value="${esc(state.settings.name)}"><div class="hint">Used in your greeting.</div></div></form>
      <div class="form-error"></div>
      <div class="actions"><button class="btn" data-close>Cancel</button><button class="btn primary" data-save>Save</button></div>`, 460);
    const submit = async () => {
      try {
        state.settings = await api("PUT", "/api/settings", Object.fromEntries(new FormData(m.el.querySelector("form"))));
        document.querySelectorAll("[data-name]").forEach((el) => (el.textContent = state.settings.name));
        m.close(); toast("Saved"); rerender();
      } catch (err) { showErrors(m.el, err); }
    };
    m.el.querySelector("[data-save]").addEventListener("click", submit);
    m.el.querySelector("form").addEventListener("submit", (e) => { e.preventDefault(); submit(); });
  }

  // ------------------------------------------------------------------ global actions + boot
  document.addEventListener("click", (e) => {
    const act = e.target.closest("[data-act]")?.dataset.act || e.target.closest("[data-action]")?.dataset.action;
    if (act === "log") tradeForm();
    else if (act === "add-account") accountForm();
    else if (act === "settings") settingsForm();
  });
  document.addEventListener("keydown", (e) => {
    if (modalRoot.innerHTML || e.target.matches("input, textarea, select")) return;
    if (e.key === "n" && state.accounts.length) { e.preventDefault(); tradeForm(); }
  });

  function tick() {
    const d = new Date();
    document.getElementById("clock").textContent = d.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
    document.getElementById("date").textContent = d.toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric" });
  }

  function welcome() {
    const w = document.getElementById("welcome");
    w.querySelector("[data-greeting]").textContent = greeting();
    const a = createAtom(document.getElementById("welcome-atom"), { scale: 0.2, centerY: 0.4 });
    const leave = () => {
      w.classList.add("leaving");
      setTimeout(() => { a.stop(); w.remove(); }, 800);
      document.removeEventListener("keydown", leave);
    };
    w.addEventListener("click", leave);
    document.addEventListener("keydown", leave);
  }

  async function boot() {
    tick(); setInterval(tick, 10000);
    welcome();
    try { await loadAll(); } catch (err) { toast("Couldn't load your journal: " + err.message, true); }
    window.addEventListener("hashchange", route);
    route();
  }
  boot();
})();

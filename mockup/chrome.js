// Shared side menu + top bar for the mockup pages.
// A page marks its slot with <div id="chrome" data-page="trades"></div> wrapping its content.
(function () {
  const page = document.body.dataset.page;
  const nav = [
    ["dashboard", "dashboard.html", "HOME", '<rect x="3" y="3" width="7" height="9"/><rect x="14" y="3" width="7" height="5"/><rect x="14" y="12" width="7" height="9"/><rect x="3" y="16" width="7" height="5"/>'],
    ["trades", "trades.html", "TRADES", '<path d="M4 4h12l4 4v12H4z"/><path d="M8 10h8M8 14h8M8 18h5"/>'],
    ["accounts", "accounts.html", "ACCOUNTS", '<rect x="3" y="6" width="18" height="13" rx="1"/><path d="M3 10h18M7 15h4"/><path d="M7 6V4h10v2"/>'],
  ];
  const svg = (p) => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6">${p}</svg>`;
  const rail = `
  <aside class="rail">
    <svg class="logo" viewBox="0 0 48 48" fill="none" stroke="#ffffff" stroke-width="1.6">
      <circle cx="24" cy="24" r="21" opacity=".5"/><circle cx="24" cy="24" r="14"/><circle cx="24" cy="24" r="6" fill="#ffffff" fill-opacity=".35"/>
      <path d="M24 3v7M24 38v7M3 24h7M38 24h7" />
    </svg>
    ${nav.map(([id, href, label, icon]) => `<a class="${id === page ? "on" : ""}" href="${href}" title="${label}">${svg(icon)}<span>${label}</span></a>`).join("")}
    <div class="spacer"></div>
    <a href="#" title="Settings">${svg('<circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M5 5l2 2M17 17l2 2M5 19l2-2M17 7l2-2"/>')}</a>
  </aside>`;
  const header = `
    <header class="top">
      <div class="title">TRADING TERMINAL<small>// v4.2</small></div>
      <div class="ticker">
        <span><b>NQ</b><em class="up">21,384.25 ▲ 0.84%</em></span>
        <span><b>ES</b><em class="up">6,042.50 ▲ 0.41%</em></span>
        <span><b>YM</b><em class="dn">43,912 ▼ 0.12%</em></span>
        <span><b>GC</b><em class="up">2,688.4 ▲ 0.27%</em></span>
        <span><b>CL</b><em class="dn">68.91 ▼ 1.03%</em></span>
        <span><b>BTC</b><em class="up">91,240 ▲ 2.18%</em></span>
        <span><b>VIX</b><em class="dn">14.82 ▼ 3.4%</em></span>
      </div>
      <div style="font-family:var(--mono);font-size:11px;color:var(--muted)"><span class="status-dot"></span>ALL SYSTEMS NOMINAL</div>
      <div class="clock"><span id="clock">--:--:--</span><small id="date">---</small></div>
    </header>`;
  const content = document.getElementById("content");
  const app = document.createElement("div");
  app.className = "app";
  app.innerHTML = rail + `<div class="main">${header}</div>`;
  content.replaceWith(app);
  app.querySelector(".main").appendChild(content);

  const pad = (n) => String(n).padStart(2, "0");
  function tick() {
    const d = new Date();
    document.getElementById("clock").textContent = `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
    document.getElementById("date").textContent = d.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric", year: "numeric" }).toUpperCase();
  }
  tick(); setInterval(tick, 1000);

  // show the modal when the page is opened with ?modal (for previews) or when a [data-open] button is clicked
  const scrim = document.querySelector(".scrim");
  if (scrim) {
    scrim.hidden = !location.search.includes("modal");
    document.addEventListener("click", (e) => {
      if (e.target.closest("[data-open]")) scrim.hidden = false;
      else if (e.target === scrim || e.target.closest("[data-close]")) scrim.hidden = true;
    });
  }
})();

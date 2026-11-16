// Shared side menu + top bar for the mockup pages.
// A page sets <body data-page="..." data-title="..."> and wraps its content in <section id="content">.
(function () {
  const page = document.body.dataset.page;
  const title = document.body.dataset.title || "";
  const nav = [
    ["dashboard", "dashboard.html", "Home", '<path d="M4 11l8-7 8 7v9H4z"/><path d="M10 20v-5h4v5"/>'],
    ["trades", "trades.html", "Trades", '<path d="M5 4h10l4 4v12H5z"/><path d="M9 11h6M9 15h6"/>'],
    ["accounts", "accounts.html", "Accounts", '<rect x="3" y="6" width="18" height="13" rx="2"/><path d="M3 10h18"/>'],
  ];
  const svg = (p) => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">${p}</svg>`;
  const rail = `
  <aside class="rail">
    <svg class="logo" viewBox="0 0 32 32" fill="none" stroke="#fff" stroke-width="1.4">
      <circle cx="16" cy="16" r="13" stroke-opacity=".35"/>
      <circle cx="16" cy="16" r="7.5"/>
      <circle cx="16" cy="16" r="2.6" fill="#fff" stroke="none"/>
      <circle cx="25.2" cy="6.8" r="2" fill="#fff" stroke="none"/>
    </svg>
    ${nav.map(([id, href, label, icon]) => `<a class="${id === page ? "on" : ""}" href="${href}">${svg(icon)}<span>${label}</span></a>`).join("")}
    <div class="spacer"></div>
    <a href="#">${svg('<circle cx="12" cy="12" r="3"/><path d="M12 3v2M12 19v2M3 12h2M19 12h2M5.6 5.6l1.4 1.4M17 17l1.4 1.4M5.6 18.4L7 17M17 7l1.4-1.4"/>')}</a>
  </aside>`;
  const header = `
    <header class="top">
      <h1>${title}</h1>
      <div class="grow"></div>
      <div class="clock"><span id="clock">--:--</span><small id="date">---</small></div>
    </header>`;
  const content = document.getElementById("content");
  const app = document.createElement("div");
  app.className = "app";
  app.innerHTML = rail + `<div class="main">${header}</div>`;
  content.replaceWith(app);
  app.querySelector(".main").appendChild(content);

  function tick() {
    const d = new Date();
    document.getElementById("clock").textContent = d.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
    document.getElementById("date").textContent = d.toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric" });
  }
  tick(); setInterval(tick, 10000);

  // modal: open with ?modal (for previews) or any [data-open] button
  const scrim = document.querySelector(".scrim");
  if (scrim) {
    scrim.hidden = !location.search.includes("modal");
    document.addEventListener("click", (e) => {
      if (e.target.closest("[data-open]")) scrim.hidden = false;
      else if (e.target === scrim || e.target.closest("[data-close]")) scrim.hidden = true;
    });
  }
})();

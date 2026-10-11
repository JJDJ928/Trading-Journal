// AFK screen: a slowly turning galaxy with the time and a greeting.
//
// Opens after IDLE_MINUTES without mouse or keyboard input, or from the
// "AFK" button in the sidebar. Any key, click or real mouse movement closes it.
//
// To build on it: add elements inside `.afk-content` in buildScreen(), and
// update them in tick() (called once a second while the screen is open).

const IDLE_MINUTES = 5;
const STAR_COUNT = 2400;   // stars in the galaxy's spiral arms
const DUST_COUNT = 350;    // faint background stars
const ARMS = 3;

let screen = null, canvas = null, ctx = null;
let open = false, frame = 0, clockTimer = 0, idleTimer = 0;
let stars = [], dust = [], startTime = 0, userName = "";
const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

export function initAfk({ name, canOpen = () => true }) {
  userName = name || "";
  buildScreen();
  const resetIdle = () => {
    clearTimeout(idleTimer);
    idleTimer = setTimeout(() => { if (canOpen()) openAfk(); else resetIdle(); }, IDLE_MINUTES * 60_000);
  };
  for (const ev of ["mousemove", "mousedown", "keydown", "wheel", "touchstart"]) {
    window.addEventListener(ev, () => { if (!open) resetIdle(); }, { passive: true });
  }
  resetIdle();
}

export function openAfk() {
  if (open) return;
  open = true;
  resize();
  screen.hidden = false;
  requestAnimationFrame(() => screen.classList.add("visible"));
  startTime = performance.now() - Math.random() * 60_000;
  tick();
  clockTimer = setInterval(tick, 1000);
  frame = requestAnimationFrame(draw);
  // Ignore the input that opened it; close on the next deliberate one.
  setTimeout(() => {
    let moved = 0, last = null;
    screen.onmousemove = (e) => {
      if (last) moved += Math.abs(e.clientX - last.x) + Math.abs(e.clientY - last.y);
      last = { x: e.clientX, y: e.clientY };
      if (moved > 40) closeAfk();
    };
    screen.onmousedown = closeAfk;
    screen.ontouchstart = closeAfk;
    window.addEventListener("keydown", onKey, true);
  }, 400);
}

function onKey(e) {
  e.preventDefault();
  e.stopPropagation();
  closeAfk();
}

export function closeAfk() {
  if (!open) return;
  open = false;
  screen.onmousemove = screen.onmousedown = screen.ontouchstart = null;
  window.removeEventListener("keydown", onKey, true);
  clearInterval(clockTimer);
  screen.classList.remove("visible");
  setTimeout(() => {
    if (!open) { screen.hidden = true; cancelAnimationFrame(frame); }
  }, 600);
  window.dispatchEvent(new Event("mousemove")); // restart the idle countdown
}

// ---------------------------------------------------------------- markup

function buildScreen() {
  screen = document.createElement("div");
  screen.className = "afk";
  screen.hidden = true;
  screen.innerHTML = `
    <canvas></canvas>
    <div class="afk-content">
      <div class="afk-time"></div>
      <div class="afk-date"></div>
      <div class="afk-hello">Hello ${escapeHtml(userName)}</div>
    </div>
    <div class="afk-hint">Move the mouse or press any key to return</div>`;
  document.body.append(screen);
  canvas = screen.querySelector("canvas");
  ctx = canvas.getContext("2d");
  window.addEventListener("resize", () => { if (open) resize(); });
}

function tick() {
  const now = new Date();
  screen.querySelector(".afk-time").textContent = now.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  screen.querySelector(".afk-date").textContent = now.toLocaleDateString([], { weekday: "long", month: "long", day: "numeric" });
}

// ---------------------------------------------------------------- galaxy

function resize() {
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  canvas.width = innerWidth * dpr;
  canvas.height = innerHeight * dpr;
  canvas.style.width = `${innerWidth}px`;
  canvas.style.height = `${innerHeight}px`;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  makeStars();
}

function makeStars() {
  const radius = Math.hypot(innerWidth, innerHeight) * 0.42;
  stars = Array.from({ length: STAR_COUNT }, () => {
    const r = Math.pow(Math.random(), 1.7) * radius;          // denser toward the core
    const arm = Math.floor(Math.random() * ARMS);
    const spread = (Math.random() - 0.5) * (0.5 + (1 - r / radius) * 0.9);
    const tint = Math.random();
    return {
      r,
      a: (arm / ARMS) * Math.PI * 2 + (r / radius) * 4.2 + spread,
      size: Math.random() < 0.06 ? 1.6 + Math.random() * 1.2 : 0.4 + Math.random() * 1.1,
      // mostly grey-white, a few cool blue/violet stars
      color: tint < 0.75 ? [215, 215, 225] : tint < 0.9 ? [160, 180, 255] : [200, 160, 255],
      alpha: 0.35 + Math.random() * 0.65,
      twinkle: Math.random() * Math.PI * 2,
    };
  });
  dust = Array.from({ length: DUST_COUNT }, () => ({
    x: Math.random() * innerWidth, y: Math.random() * innerHeight,
    size: Math.random() * 0.9 + 0.2, alpha: Math.random() * 0.5 + 0.1, twinkle: Math.random() * 6,
  }));
}

function draw(now) {
  const t = reducedMotion ? 0 : (now - startTime) / 1000;
  const w = innerWidth, h = innerHeight, cx = w / 2, cy = h / 2;
  ctx.fillStyle = "#030304";
  ctx.fillRect(0, 0, w, h);

  // Slowly drifting nebula clouds.
  const clouds = [
    [cx + Math.cos(t * 0.010) * w * 0.18, cy + Math.sin(t * 0.013) * h * 0.12, w * 0.55, "60, 60, 90", 0.16],
    [cx + Math.cos(t * 0.008 + 2) * w * 0.22, cy + Math.sin(t * 0.011 + 1) * h * 0.18, w * 0.45, "90, 60, 110", 0.10],
    [cx, cy, w * 0.30, "170, 170, 200", 0.13],
    [cx, cy, w * 0.07, "235, 235, 245", 0.18],   // bright core
  ];
  for (const [x, y, rad, rgb, a] of clouds) {
    const g = ctx.createRadialGradient(x, y, 0, x, y, rad);
    g.addColorStop(0, `rgba(${rgb}, ${a})`);
    g.addColorStop(1, `rgba(${rgb}, 0)`);
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, w, h);
  }

  for (const d of dust) {
    ctx.globalAlpha = d.alpha * (0.6 + 0.4 * Math.sin(t * 0.8 + d.twinkle));
    ctx.fillStyle = "#cfcfd8";
    ctx.fillRect(d.x, d.y, d.size, d.size);
  }

  // The galaxy, tilted, with inner stars orbiting faster than outer ones.
  const tilt = 0.55, spin = -0.35;
  for (const s of stars) {
    const a = s.a + t * (0.02 + 0.3 / (s.r + 60));  // near-rigid spin keeps the arms intact
    const x0 = Math.cos(a) * s.r, y0 = Math.sin(a) * s.r * tilt;
    const x = cx + x0 * Math.cos(spin) - y0 * Math.sin(spin);
    const y = cy + x0 * Math.sin(spin) + y0 * Math.cos(spin);
    ctx.globalAlpha = s.alpha * (0.75 + 0.25 * Math.sin(t * 1.5 + s.twinkle));
    ctx.fillStyle = `rgb(${s.color[0]}, ${s.color[1]}, ${s.color[2]})`;
    ctx.beginPath();
    ctx.arc(x, y, s.size, 0, Math.PI * 2);
    ctx.fill();
  }
  ctx.globalAlpha = 1;
  if (open && !reducedMotion) frame = requestAnimationFrame(draw);
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

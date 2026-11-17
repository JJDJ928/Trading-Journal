// A living, breathing "atom" AI drawn on a canvas.
// Usage: createAtom(canvasElement, { scale: 0.24, centerY: 0.4, interactive: true })
(function () {
  const TAU = Math.PI * 2;
  const rnd = (a, b) => a + Math.random() * (b - a);

  function fibSphere(n) {
    const out = [], g = Math.PI * (3 - Math.sqrt(5));
    for (let i = 0; i < n; i++) {
      const y = 1 - (i / (n - 1)) * 2, r = Math.sqrt(1 - y * y), t = g * i;
      out.push([Math.cos(t) * r, y, Math.sin(t) * r]);
    }
    return out;
  }

  // smooth, slowly evolving field used to make the surface ripple organically
  function field(x, y, z, t) {
    return (
      Math.sin(x * 2.1 + t * 0.35) * Math.sin(y * 1.7 - t * 0.27) * 0.55 +
      Math.sin(z * 2.6 + y * 1.3 + t * 0.22) * 0.3 +
      Math.sin((x + z) * 3.4 - t * 0.41) * 0.15
    );
  }

  window.createAtom = function (canvas, opts = {}) {
    const o = Object.assign({ scale: 0.26, centerY: 0.5, interactive: true, density: 1 }, opts);
    const ctx = canvas.getContext("2d");
    let W = 0, H = 0, R = 0;

    function size() {
      const dpr = window.devicePixelRatio || 1, b = canvas.getBoundingClientRect();
      W = b.width; H = b.height;
      canvas.width = W * dpr; canvas.height = H * dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      R = Math.min(W, H) * o.scale;
    }
    size(); addEventListener("resize", size);
    let running = true;

    // layers: outer membrane, inner shell, nucleus
    const pts = [];
    fibSphere(Math.round(420 * o.density)).forEach(([x, y, z]) =>
      pts.push({ x, y, z, base: 1, layer: 0, ph: Math.random() * TAU, sz: rnd(0.8, 1.6) }));
    fibSphere(Math.round(140 * o.density)).forEach(([x, y, z]) =>
      pts.push({ x, y, z, base: 0.58, layer: 1, ph: Math.random() * TAU, sz: rnd(0.7, 1.3) }));
    for (let i = 0; i < 70 * o.density; i++) {
      const u = rnd(-1, 1), t = rnd(0, TAU), s = Math.sqrt(1 - u * u), r = Math.cbrt(Math.random()) * 0.22;
      pts.push({ x: s * Math.cos(t), y: u, z: s * Math.sin(t), base: r, layer: 2, ph: Math.random() * TAU, sz: rnd(0.8, 1.8) });
    }

    // drifting dust around it
    const dust = Array.from({ length: 90 }, () => ({
      a: rnd(0, TAU), b: rnd(-1, 1), r: rnd(1.5, 3.2), sp: rnd(0.005, 0.02), sz: rnd(0.4, 1.2), ph: rnd(0, TAU),
    }));

    const orbits = [
      { tx: 1.15, tz: 0.35, sp: 0.22, r: 1.32 },
      { tx: -0.7, tz: 1.05, sp: -0.17, r: 1.42 },
      { tx: 0.25, tz: -1.1, sp: 0.27, r: 1.25 },
    ];

    const signals = []; // pulses travelling along connections
    let links = [];

    let mx = 0, my = 0, tmx = 0, tmy = 0;
    const onMove = (e) => { tmx = e.clientX / innerWidth - 0.5; tmy = e.clientY / innerHeight - 0.5; };
    if (o.interactive) addEventListener("mousemove", onMove);

    function rot(x, y, z, ay, ax) {
      const cy = Math.cos(ay), sy = Math.sin(ay);
      [x, z] = [x * cy - z * sy, x * sy + z * cy];
      const cx = Math.cos(ax), sx = Math.sin(ax);
      [y, z] = [y * cx - z * sx, y * sx + z * cx];
      return [x, y, z];
    }
    function orbitPt(ob, a) {
      let x = Math.cos(a) * ob.r, y = 0, z = Math.sin(a) * ob.r;
      [y, z] = [y * Math.cos(ob.tx) - z * Math.sin(ob.tx), y * Math.sin(ob.tx) + z * Math.cos(ob.tx)];
      [x, y] = [x * Math.cos(ob.tz) - y * Math.sin(ob.tz), x * Math.sin(ob.tz) + y * Math.cos(ob.tz)];
      return [x, y, z];
    }

    let last = 0, spawnT = 0;
    function frame(ms) {
      const t = ms / 1000, dt = Math.min(0.05, t - last || 0.016); last = t;
      mx += (tmx - mx) * 0.03; my += (tmy - my) * 0.03;

      ctx.clearRect(0, 0, W, H);
      const cx = W / 2, cy = H * o.centerY;
      // slow breathing: ~7 second cycle, with a softer second harmonic
      const breath = 1 + Math.sin(t * 0.9) * 0.045 + Math.sin(t * 0.45 + 1) * 0.02;
      const ay = t * 0.07 + mx * 0.5, ax = 0.32 + Math.sin(t * 0.13) * 0.12 + my * 0.35;
      const persp = 2.8;
      const proj = (x, y, z) => { const k = persp / (persp + z); return [cx + x * R * k, cy + y * R * k, z, k]; };

      // aura that swells with the breath
      const aura = ctx.createRadialGradient(cx, cy, 0, cx, cy, R * 1.9 * breath);
      aura.addColorStop(0, "rgba(255,255,255,0.10)");
      aura.addColorStop(0.45, "rgba(255,255,255,0.035)");
      aura.addColorStop(1, "rgba(255,255,255,0)");
      ctx.fillStyle = aura; ctx.fillRect(0, 0, W, H);

      // HUD rings (very faint, slow)
      ctx.save(); ctx.translate(cx, cy);
      ctx.strokeStyle = "rgba(255,255,255,0.10)"; ctx.lineWidth = 1;
      ctx.beginPath(); ctx.arc(0, 0, R * 1.62, 0, TAU); ctx.stroke();
      ctx.rotate(t * 0.03);
      for (let i = 0; i < 120; i++) {
        const a = (i / 120) * TAU, l = i % 10 === 0 ? 9 : 4;
        ctx.strokeStyle = `rgba(255,255,255,${i % 10 === 0 ? 0.35 : 0.12})`;
        ctx.beginPath(); ctx.moveTo(Math.cos(a) * R * 1.68, Math.sin(a) * R * 1.68);
        ctx.lineTo(Math.cos(a) * (R * 1.68 + l), Math.sin(a) * (R * 1.68 + l)); ctx.stroke();
      }
      ctx.rotate(-t * 0.07);
      ctx.strokeStyle = "rgba(255,255,255,0.22)"; ctx.lineWidth = 1.5;
      for (let i = 0; i < 3; i++) { ctx.beginPath(); ctx.arc(0, 0, R * 1.8, i * TAU / 3, i * TAU / 3 + 0.6); ctx.stroke(); }
      ctx.restore();

      // dust
      for (const d of dust) {
        d.a += d.sp * dt;
        const [x, y, z] = rot(Math.cos(d.a) * d.r * Math.sqrt(1 - d.b * d.b), d.b * d.r * 0.7, Math.sin(d.a) * d.r * Math.sqrt(1 - d.b * d.b), ay * 0.5, ax);
        const [sx, sy, , k] = proj(x * 0.75, y * 0.75, z * 0.4);
        ctx.fillStyle = `rgba(255,255,255,${(0.15 + 0.15 * Math.sin(t * 0.8 + d.ph)) * k})`;
        ctx.beginPath(); ctx.arc(sx, sy, d.sz, 0, TAU); ctx.fill();
      }

      // project points with organic surface ripple
      const P = pts.map((p) => {
        const f = p.layer === 2 ? 0.25 : p.layer === 1 ? 0.6 : 1;
        const n = field(p.x, p.y, p.z, t) * 0.09 * f;
        const r = p.base * (breath + n) * (p.layer === 1 ? 1 + Math.sin(t * 0.9 + 1.2) * 0.04 : 1);
        const spin = p.layer === 1 ? -t * 0.11 : p.layer === 2 ? t * 0.2 : 0;
        const [x, y, z] = rot(p.x * r, p.y * r, p.z * r, ay + spin, ax);
        const [sx, sy, zz, k] = proj(x, y, z);
        return { sx, sy, z: zz, k, p };
      });

      // connections
      links = [];
      const maxD = R * 0.21, maxD2 = maxD * maxD;
      ctx.lineWidth = 0.55;
      for (let i = 0; i < P.length; i++) {
        const a = P[i];
        for (let j = i + 1; j < P.length; j++) {
          const b = P[j];
          if (a.p.layer !== b.p.layer && !(a.p.layer === 2 || b.p.layer === 2)) continue;
          const dx = a.sx - b.sx, dy = a.sy - b.sy, d2 = dx * dx + dy * dy;
          if (d2 < maxD2) {
            const depth = Math.max(0.15, (1.6 - (a.z + b.z) / 2) / 2.6);
            const al = (1 - d2 / maxD2) * 0.34 * depth * (a.p.layer === 2 ? 0.7 : 1);
            ctx.strokeStyle = `rgba(255,255,255,${al})`;
            ctx.beginPath(); ctx.moveTo(a.sx, a.sy); ctx.lineTo(b.sx, b.sy); ctx.stroke();
            if (al > 0.12) links.push([i, j]);
          }
        }
      }

      // neural signals: occasional bright pulses running along links
      spawnT -= dt;
      if (spawnT <= 0 && links.length) {
        const [i, j] = links[(Math.random() * links.length) | 0];
        signals.push({ i, j, u: 0, sp: rnd(0.5, 1.1), hops: (Math.random() * 4) | 0 });
        spawnT = rnd(0.05, 0.22);
      }
      for (let s = signals.length - 1; s >= 0; s--) {
        const g = signals[s]; g.u += g.sp * dt;
        const a = P[g.i], b = P[g.j];
        if (!a || !b) { signals.splice(s, 1); continue; }
        const x = a.sx + (b.sx - a.sx) * g.u, y = a.sy + (b.sy - a.sy) * g.u;
        ctx.strokeStyle = "rgba(255,255,255,0.55)"; ctx.lineWidth = 1;
        ctx.beginPath(); ctx.moveTo(a.sx, a.sy); ctx.lineTo(x, y); ctx.stroke();
        const sg = ctx.createRadialGradient(x, y, 0, x, y, 6);
        sg.addColorStop(0, "rgba(255,255,255,0.95)"); sg.addColorStop(1, "rgba(255,255,255,0)");
        ctx.fillStyle = sg; ctx.beginPath(); ctx.arc(x, y, 6, 0, TAU); ctx.fill();
        if (g.u >= 1) {
          const next = g.hops > 0 && links.find((l) => l[0] === g.j || l[1] === g.j);
          if (next) { g.i = g.j; g.j = next[0] === g.j ? next[1] : next[0]; g.u = 0; g.hops--; }
          else signals.splice(s, 1);
        }
      }

      // points, twinkling slowly
      for (const q of P) {
        const depth = Math.max(0.1, (1.6 - q.z) / 2.6);
        const tw = 0.75 + 0.25 * Math.sin(t * 1.1 + q.p.ph);
        ctx.fillStyle = `rgba(255,255,255,${(0.25 + depth * 0.75) * tw})`;
        ctx.beginPath(); ctx.arc(q.sx, q.sy, q.p.sz * (0.6 + depth * 0.8) * (R / 230), 0, TAU); ctx.fill();
      }

      // nucleus heartbeat glow (double beat each breath)
      const beat = Math.pow(Math.max(0, Math.sin(t * 0.9)), 6) * 0.35 + 0.55;
      const core = ctx.createRadialGradient(cx, cy, 0, cx, cy, R * 0.42);
      core.addColorStop(0, `rgba(255,255,255,${0.6 * beat})`);
      core.addColorStop(0.35, `rgba(255,255,255,${0.18 * beat})`);
      core.addColorStop(1, "rgba(255,255,255,0)");
      ctx.fillStyle = core; ctx.beginPath(); ctx.arc(cx, cy, R * 0.42, 0, TAU); ctx.fill();

      // electron orbits with comet trails
      orbits.forEach((ob, i) => {
        ctx.strokeStyle = "rgba(255,255,255,0.11)"; ctx.lineWidth = 1;
        ctx.beginPath();
        for (let s = 0; s <= 140; s++) {
          const [x, y, z] = rot(...orbitPt(ob, (s / 140) * TAU).map((v) => v * breath), ay, ax);
          const [sx, sy] = proj(x, y, z);
          s ? ctx.lineTo(sx, sy) : ctx.moveTo(sx, sy);
        }
        ctx.stroke();
        const a0 = t * ob.sp + i * 2.1;
        for (let k = 22; k >= 0; k--) {
          const [x, y, z] = rot(...orbitPt(ob, a0 - Math.sign(ob.sp) * k * 0.025).map((v) => v * breath), ay, ax);
          const [sx, sy, , kk] = proj(x, y, z);
          ctx.fillStyle = `rgba(255,255,255,${(1 - k / 22) * 0.5})`;
          ctx.beginPath(); ctx.arc(sx, sy, (1 - k / 22) * 2.4 * kk, 0, TAU); ctx.fill();
        }
        const [x, y, z] = rot(...orbitPt(ob, a0).map((v) => v * breath), ay, ax);
        const [ex, ey] = proj(x, y, z);
        const eg = ctx.createRadialGradient(ex, ey, 0, ex, ey, 14);
        eg.addColorStop(0, "rgba(255,255,255,1)"); eg.addColorStop(0.3, "rgba(255,255,255,0.5)"); eg.addColorStop(1, "rgba(255,255,255,0)");
        ctx.fillStyle = eg; ctx.beginPath(); ctx.arc(ex, ey, 14, 0, TAU); ctx.fill();
      });

      if (running) requestAnimationFrame(frame);
    }
    requestAnimationFrame(frame);
    return {
      stop() {
        running = false;
        removeEventListener("resize", size);
        removeEventListener("mousemove", onMove);
      },
    };
  };
})();

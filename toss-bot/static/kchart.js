/* kchart.js — 증권사 앱 같은 캔들 차트 (외부 라이브러리 없음)
 *
 *  손가락: 좌우로 끌기 = 이동(관성) · 두 손가락 = 확대/축소 · 길게 누르거나 탭 = 십자선(누른 채 움직이면 따라감) · 다시 탭 = 끄기
 *  마우스: 끌기 = 이동 · 휠 = 확대/축소 · 올려 두기 = 십자선
 *  일/주/월봉 · 이평선 5/20/60/120 · 볼린저(20,2) · 거래량+20일 평균 · RSI(14) · 화면 안 최고/최저 · 현재가 선 · 공시 표시
 *
 *  new KChart(el, {d, o, h, l, c, v}, {markers: [{date: "2026-10-02", tag: "자사주", title: "..."}], us: false})
 */
(function () {
  const UP = "#f04452", DN = "#3d8bfd", GRID = "#1f2b38", AXT = "#6b7c90", TXT = "#e8eef5", BG = "#17212b";
  const MA = [[5, "#ffd166"], [20, "#ef8bff"], [60, "#4fd1c5"], [120, "#a0aec0"]];
  const AXW = 62, DATEH = 20, GAP = 8;

  // ── 지표 ─────────────────────────────────────────
  function sma(a, n) {
    const out = new Array(a.length).fill(null); let s = 0;
    for (let i = 0; i < a.length; i++) { s += a[i]; if (i >= n) s -= a[i - n]; if (i >= n - 1) out[i] = s / n; }
    return out;
  }
  function boll(c, n = 20, k = 2) {
    const m = sma(c, n), up = new Array(c.length).fill(null), lo = up.slice();
    for (let i = n - 1; i < c.length; i++) {
      let v = 0; for (let j = i - n + 1; j <= i; j++) v += (c[j] - m[i]) ** 2;
      const sd = Math.sqrt(v / n); up[i] = m[i] + k * sd; lo[i] = m[i] - k * sd;
    }
    return {m, up, lo};
  }
  function rsi(c, n = 14) {                          // 와일더 방식 (증권사 기본)
    const out = new Array(c.length).fill(null); let ag = 0, al = 0;
    for (let i = 1; i < c.length; i++) {
      const d = c[i] - c[i - 1], g = Math.max(d, 0), l = Math.max(-d, 0);
      if (i <= n) { ag += g / n; al += l / n; if (i === n) out[i] = al === 0 ? 100 : 100 - 100 / (1 + ag / al); }
      else { ag = (ag * (n - 1) + g) / n; al = (al * (n - 1) + l) / n; out[i] = al === 0 ? 100 : 100 - 100 / (1 + ag / al); }
    }
    return out;
  }
  // 일봉 → 주봉/월봉
  function aggregate(D, tf) {
    if (tf === "D") return D;
    const key = s => {
      if (tf === "M") return s.slice(0, 6);
      const dt = new Date(+s.slice(0, 4), +s.slice(4, 6) - 1, +s.slice(6, 8)), day = (dt.getDay() + 6) % 7;
      const mon = new Date(dt - day * 864e5); return `${mon.getFullYear()}${mon.getMonth()}${mon.getDate()}`;
    };
    const R = {d: [], o: [], h: [], l: [], c: [], v: []}; let k0 = null;
    for (let i = 0; i < D.d.length; i++) {
      const k = key(D.d[i]);
      if (k !== k0) { R.d.push(D.d[i]); R.o.push(D.o[i]); R.h.push(D.h[i]); R.l.push(D.l[i]); R.c.push(D.c[i]); R.v.push(D.v[i]); k0 = k; }
      else { const j = R.d.length - 1; R.h[j] = Math.max(R.h[j], D.h[i]); R.l[j] = Math.min(R.l[j], D.l[i]); R.c[j] = D.c[i]; R.v[j] += D.v[i]; }
    }
    return R;
  }

  const fmt = (v, us, d) => v == null ? "-" : us ? Number(v).toLocaleString("en-US", {minimumFractionDigits: d ?? 2, maximumFractionDigits: d ?? 2})
    : Math.round(v).toLocaleString("ko-KR");
  const fvol = v => v >= 1e8 ? (v / 1e8).toFixed(1) + "억" : v >= 1e4 ? (v / 1e4).toFixed(v >= 1e6 ? 0 : 1) + "만" : Math.round(v).toLocaleString();
  const dstr = s => `${s.slice(2, 4)}.${s.slice(4, 6)}.${s.slice(6, 8)}`;

  class KChart {
    constructor(root, raw, opt = {}) {
      this.root = root; this.us = !!opt.us; this.markers = opt.markers || [];
      this.state = Object.assign({tf: "D", rng: "6M", ma: true, bb: true}, opt.state || {});
      this.onState = opt.onState || (() => {});
      // 깨진 봉 제거
      const D = {d: [], o: [], h: [], l: [], c: [], v: []};
      for (let i = 0; i < raw.d.length; i++) if (raw.c[i] != null && raw.h[i] != null && raw.l[i] != null) {
        D.d.push(raw.d[i]); D.c.push(raw.c[i]); D.o.push(raw.o[i] ?? raw.c[i]); D.h.push(raw.h[i]); D.l.push(raw.l[i]); D.v.push(raw.v[i] || 0);
      }
      this.daily = D;
      root.innerHTML = `
        <div class="kc-bar"><div class="kc-seg" data-g="tf">${[["D", "일"], ["W", "주"], ["M", "월"]].map(([k, l]) => `<button data-v="${k}">${l}</button>`).join("")}</div>
          <div class="kc-seg" data-g="rng">${["3M", "6M", "1Y", "3Y", "ALL"].map(k => `<button data-v="${k}">${{"3M": "3개월", "6M": "6개월", "1Y": "1년", "3Y": "3년", ALL: "전체"}[k]}</button>`).join("")}</div></div>
        <div class="kc-bar" style="margin-top:6px"><button class="kc-tg" data-t="ma">이평선</button><button class="kc-tg" data-t="bb">볼린저</button>
          <span style="flex:1"></span><button class="kc-tg kc-fs" title="크게 보기">⛶ 크게</button></div>
        <div class="kc-info"></div>
        <div class="kc-wrap"><canvas></canvas></div>
        <div class="kc-help">← 끌어서 이동 · 두 손가락 확대 · 길게 눌러 십자선 →</div>`;
      this.cv = root.querySelector("canvas"); this.ctx = this.cv.getContext("2d"); this.info = root.querySelector(".kc-info");
      root.querySelectorAll(".kc-seg button").forEach(b => b.onclick = () => {
        const g = b.parentNode.dataset.g; this.state[g] = b.dataset.v;
        if (g === "tf") this.build(); else this.fitRange(); this.syncUI(); this.onState(this.state); this.draw();
      });
      root.querySelectorAll(".kc-tg[data-t]").forEach(b => b.onclick = () => { this.state[b.dataset.t] = !this.state[b.dataset.t]; this.syncUI(); this.onState(this.state); this.draw(); });
      root.querySelector(".kc-fs").onclick = () => this.fullscreen();
      this.cross = null; this.bind();
      this.build(); this.syncUI();
      this.ro = new ResizeObserver(() => this.resize()); this.ro.observe(root.querySelector(".kc-wrap"));
      this.resize();
    }
    destroy() { this.ro && this.ro.disconnect(); cancelAnimationFrame(this.anim); if (this.fs) this.fullscreen(); }

    syncUI() {
      this.root.querySelectorAll(".kc-seg button").forEach(b => b.classList.toggle("act", this.state[b.parentNode.dataset.g] === b.dataset.v));
      this.root.querySelectorAll(".kc-tg[data-t]").forEach(b => b.classList.toggle("act", !!this.state[b.dataset.t]));
    }
    build() {
      const B = this.B = aggregate(this.daily, this.state.tf), c = B.c;
      B.ma = MA.map(([n]) => sma(c, n)); B.bb = boll(c); B.rsi = rsi(c); B.vma = sma(B.v, 20); B.N = c.length;
      // 공시 표시: 해당 날짜가 들어간 봉에 붙임
      B.mk = {};
      for (const m of this.markers) {
        const ds = String(m.date || "").replace(/-/g, ""); if (ds.length !== 8) continue;
        let i = B.d.length - 1; while (i > 0 && B.d[i] > ds) i--;
        if (B.d[i] && B.d[i] <= ds && (i === B.d.length - 1 || B.d[i + 1] > ds)) (B.mk[i] = B.mk[i] || []).push(m);
      }
      this.fitRange();
    }
    fitRange() {
      const per = {D: {"3M": 63, "6M": 125, "1Y": 250, "3Y": 750}, W: {"3M": 13, "6M": 26, "1Y": 52, "3Y": 156}, M: {"3M": 12, "6M": 18, "1Y": 24, "3Y": 36}}[this.state.tf];
      const N = this.B.N, n = this.state.rng === "ALL" ? N : Math.min(N, per[this.state.rng] || 125);
      this.n = Math.max(Math.min(n, N), Math.min(10, N)); this.end = N - 1 + this.n * 0.04; this.cross = null;
    }
    resize() {
      const w = this.root.querySelector(".kc-wrap"), W = w.clientWidth;
      const H = this.fs ? Math.max(240, w.clientHeight) : Math.round(Math.min(560, Math.max(380, W * 1.05)));
      const r = window.devicePixelRatio || 1;
      this.W = W; this.H = H; this.cv.width = W * r; this.cv.height = H * r; this.cv.style.height = H + "px"; this.cv.style.width = W + "px";
      this.ctx.setTransform(r, 0, 0, r, 0, 0); this.draw();
    }
    fullscreen() {
      this.fs = !this.fs; this.root.classList.toggle("kc-full", this.fs); document.body.style.overflow = this.fs ? "hidden" : "";
      this.root.querySelector(".kc-fs").textContent = this.fs ? "✕ 닫기" : "⛶ 크게";
      requestAnimationFrame(() => this.resize());
    }

    // ── 좌표 ───────────────────────────────────────
    get pw() { return this.W - AXW; }
    get bw() { return this.pw / this.n; }
    clamp() {
      const N = this.B.N;
      this.n = Math.max(Math.min(10, N), Math.min(this.n, N + 10));
      this.end = Math.max(this.n * 0.25 - 1, Math.min(this.end, N - 1 + this.n * 0.35));
    }
    panes() {
      const top = 4, avail = this.H - DATEH - top - GAP * 2, ph = Math.round(avail * 0.64), vh = Math.round(avail * 0.16);
      return {p: [top, top + ph], v: [top + ph + GAP, top + ph + GAP + vh], r: [top + ph + GAP * 2 + vh, this.H - DATEH]};
    }

    // ── 입력 ───────────────────────────────────────
    bind() {
      const cv = this.cv, P = new Map(); let g = null, lpT = null, vel = 0, lastX = 0, lastT = 0;
      cv.style.touchAction = "pan-y";               // 세로 스크롤은 페이지로, 가로·핀치는 차트가
      const local = e => { const r = cv.getBoundingClientRect(); return [e.clientX - r.left, e.clientY - r.top]; };
      const setCross = (x, y) => { this.cross = {x: Math.min(x, this.pw - 1), y}; this.draw(); };
      cv.addEventListener("pointerdown", e => {
        cancelAnimationFrame(this.anim); cv.setPointerCapture(e.pointerId);
        const [x, y] = local(e); P.set(e.pointerId, {x, y, x0: x, y0: y});
        if (P.size === 2) {
          clearTimeout(lpT); const [a, b] = [...P.values()];
          g = {mode: "pinch", d0: Math.abs(a.x - b.x) || 1, n0: this.n, end0: this.end, cx: (a.x + b.x) / 2};
          g.ci = this.end - this.n + g.cx / this.bw;  // 손가락 가운데의 봉 위치(고정)
          return;
        }
        g = {mode: "wait", x0: x, y0: y, end0: this.end, t0: performance.now(), had: !!this.cross};
        lastX = x; lastT = g.t0; vel = 0;
        if (e.pointerType !== "mouse") lpT = setTimeout(() => { if (g && g.mode === "wait") { g.mode = "cross"; setCross(x, y); navigator.vibrate && navigator.vibrate(8); } }, 320);
        else g.mode = "wait";
      });
      cv.addEventListener("pointermove", e => {
        const [x, y] = local(e), p = P.get(e.pointerId);
        if (!p) { if (e.pointerType === "mouse") setCross(x, y); return; }
        p.x = x; p.y = y;
        if (!g) return;
        if (g.mode === "pinch" && P.size >= 2) {
          const [a, b] = [...P.values()], d = Math.abs(a.x - b.x) || 1;
          this.n = g.n0 * g.d0 / d; this.clamp();
          const bw = this.pw / this.n; this.end = g.ci + this.n - g.cx / bw; this.clamp(); this.draw(); return;
        }
        if (g.mode === "wait") {
          if (Math.abs(x - g.x0) > 6 || Math.abs(y - g.y0) > 6) {
            clearTimeout(lpT);
            if (g.had && e.pointerType !== "mouse") { g.mode = "cross"; } else { g.mode = "pan"; this.cross = null; }
          }
        }
        if (g.mode === "cross") return setCross(x, y);
        if (g.mode === "pan") {
          this.end = g.end0 - (x - g.x0) / this.bw; this.clamp();
          const t = performance.now(); vel = 0.8 * vel + 0.2 * ((x - lastX) / Math.max(1, t - lastT)); lastX = x; lastT = t;
          if (e.pointerType === "mouse") this.cross = null;
          this.draw();
        }
      });
      const up = e => {
        const p = P.get(e.pointerId); P.delete(e.pointerId); clearTimeout(lpT);
        if (!g) return;
        if (g.mode === "pinch") { if (P.size === 0) g = null; else g = {mode: "none"}; return; }
        if (g.mode === "wait" && p && e.type === "pointerup" && e.pointerType !== "mouse") {      // 탭: 십자선 켜기/끄기
          if (this.cross) this.cross = null; else this.cross = {x: Math.min(p.x, this.pw - 1), y: p.y};
          this.draw();
        } else if (g.mode === "pan" && Math.abs(vel) > 0.05 && performance.now() - lastT < 80) {   // 관성
          let v = Math.max(-40, Math.min(40, vel * 16)); const step = () => {
            this.end -= v / this.bw; this.clamp(); this.draw(); v *= 0.9;
            if (Math.abs(v) > 0.3) this.anim = requestAnimationFrame(step);
          }; this.anim = requestAnimationFrame(step);
        }
        g = null;
      };
      cv.addEventListener("pointerup", up); cv.addEventListener("pointercancel", up);
      cv.addEventListener("pointerleave", e => { if (e.pointerType === "mouse" && !P.size) { this.cross = null; this.draw(); } });
      cv.addEventListener("wheel", e => {
        e.preventDefault(); const [x] = local(e), ci = this.end - this.n + x / this.bw;
        this.n *= Math.exp(e.deltaY * 0.0015); this.clamp(); this.end = ci + this.n - x / this.bw; this.clamp(); this.draw();
      }, {passive: false});
    }

    // ── 그리기 ─────────────────────────────────────
    draw() {
      if (!this.W || !this.B) return;
      const C = this.ctx, B = this.B, S = this.state, us = this.us, bw = this.bw, pw = this.pw, PN = this.panes();
      C.clearRect(0, 0, this.W, this.H);
      const i0 = Math.max(0, Math.floor(this.end - this.n)), i1 = Math.min(B.N - 1, Math.ceil(this.end));
      const X = i => (i - (this.end - this.n) - 0.5) * bw;   // 봉 가운데
      if (i1 < i0) return;
      // 가격 범위
      let hi = -Infinity, lo = Infinity, hiI = i0, loI = i0, vmax = 0;
      for (let i = i0; i <= i1; i++) {
        if (B.h[i] > hi) { hi = B.h[i]; hiI = i; } if (B.l[i] < lo) { lo = B.l[i]; loI = i; }
        vmax = Math.max(vmax, B.v[i]);
      }
      let yHi = hi, yLo = lo;
      const inc = arr => { for (let i = i0; i <= i1; i++) if (arr[i] != null) { yHi = Math.max(yHi, arr[i]); yLo = Math.min(yLo, arr[i]); } };
      if (S.ma) B.ma.forEach(inc); if (S.bb) { inc(B.bb.up); inc(B.bb.lo); }
      const pad = (yHi - yLo) * 0.08 || yHi * 0.02 || 1; yHi += pad; yLo -= pad;
      const [pt, pb] = PN.p, Y = v => pt + (yHi - v) / (yHi - yLo) * (pb - pt);
      const [vt, vb] = PN.v, VY = v => vb - v / (vmax || 1) * (vb - vt - 2);
      const [rt, rb] = PN.r, RY = v => rb - v / 100 * (rb - rt);

      C.font = "10px -apple-system,BlinkMacSystemFont,sans-serif"; C.textBaseline = "middle"; C.lineWidth = 1;
      // 격자 + 가격 축
      const step = niceStep((yHi - yLo) / 5); C.strokeStyle = GRID; C.fillStyle = AXT; C.textAlign = "left";
      for (let v = Math.ceil(yLo / step) * step; v <= yHi; v += step) {
        const y = Math.round(Y(v)) + .5; line(C, 0, y, pw, y); C.fillText(fmtAx(v, us, step), pw + 6, y);
      }
      [[vt, vb], [rt, rb]].forEach(([a, b]) => { C.strokeStyle = GRID; line(C, 0, a - GAP / 2 + .5, this.W, a - GAP / 2 + .5); });
      // 날짜 눈금
      C.textAlign = "center"; let lastPx = -1e9, lastLab = "";
      for (let i = i0; i <= i1; i++) {
        const d = B.d[i], p = B.d[i - 1] || "";
        let lab = null;
        if (S.tf === "D") { if (d.slice(0, 6) !== p.slice(0, 6)) lab = d.slice(4, 6) === "01" || !lastLab ? `${d.slice(2, 4)}.${d.slice(4, 6)}` : `${+d.slice(4, 6)}월`; }
        else if (S.tf === "W") { if (d.slice(0, 6) !== p.slice(0, 6) && +d.slice(4, 6) % 3 === 1) lab = `${d.slice(2, 4)}.${d.slice(4, 6)}`; }
        else if (d.slice(0, 4) !== p.slice(0, 4)) lab = `${d.slice(0, 4)}`;
        if (!lab) continue; const x = X(i);
        if (x - lastPx < 44 || x < 16 || x > pw - 12) continue; lastPx = x; lastLab = lab;
        C.strokeStyle = GRID; line(C, Math.round(x) + .5, pt, Math.round(x) + .5, rb);
        C.fillStyle = AXT; C.fillText(lab, x, this.H - DATEH / 2);
      }
      C.save(); C.beginPath(); C.rect(0, 0, pw, this.H); C.clip();
      // 볼린저
      if (S.bb) {
        C.fillStyle = "rgba(79,140,255,.07)"; C.beginPath(); let st = false;
        for (let i = i0; i <= i1; i++) if (B.bb.up[i] != null) { st ? C.lineTo(X(i), Y(B.bb.up[i])) : C.moveTo(X(i), Y(B.bb.up[i])); st = true; }
        for (let i = i1; i >= i0; i--) if (B.bb.lo[i] != null) C.lineTo(X(i), Y(B.bb.lo[i]));
        C.fill();
        C.setLineDash([4, 3]); path(C, B.bb.up, i0, i1, X, Y, "#4f8cff", 1); path(C, B.bb.lo, i0, i1, X, Y, "#4f8cff", 1); C.setLineDash([]);
        if (!S.ma) path(C, B.bb.m, i0, i1, X, Y, "rgba(79,140,255,.6)", 1);
      }
      // 캔들
      const body = Math.max(1, bw * 0.72);
      for (let i = i0; i <= i1; i++) {
        const o = B.o[i], c = B.c[i], up = c > o || (c === o && i > 0 && c >= B.c[i - 1]), col = up ? UP : DN, x = X(i);
        C.strokeStyle = col; C.fillStyle = col;
        line(C, Math.round(x) + .5, Y(B.h[i]), Math.round(x) + .5, Y(B.l[i]));
        if (bw >= 2.5) { const y1 = Y(Math.max(o, c)), y2 = Y(Math.min(o, c)); C.fillRect(x - body / 2, y1, body, Math.max(1, y2 - y1)); }
      }
      // 이평선
      if (S.ma) B.ma.forEach((a, k) => path(C, a, i0, i1, X, Y, MA[k][1], 1.2));
      // 공시 표시
      for (let i = i0; i <= i1; i++) if (B.mk[i]) {
        const x = X(i), y = Math.min(pb - 8, Y(B.l[i]) + 12);
        C.fillStyle = "#f5a524"; C.beginPath(); C.moveTo(x, y - 5); C.lineTo(x - 4.5, y + 3); C.lineTo(x + 4.5, y + 3); C.fill();
      }
      C.restore();
      // 최고/최저 (화면 안)
      C.font = "bold 10px -apple-system,sans-serif";
      [[hiI, hi, "최고", UP, -1], [loI, lo, "최저", DN, 1]].forEach(([i, v, t, col, dir]) => {
        const x = X(i), y = Y(v) + dir * 2, left = x > pw * 0.6, txt = `${t} ${fmt(v, us)}`;
        const w = C.measureText(txt).width, tx = left ? x - 16 - w : x + 16;
        C.strokeStyle = col; C.fillStyle = col; line(C, x, y + dir * 4, left ? x - 12 : x + 12, y + dir * 4);
        C.textAlign = "left"; C.fillText(txt, tx, y + dir * 4);
      });
      // 현재가 선
      const last = B.N - 1, lc = B.c[last], lup = last > 0 ? lc >= B.c[last - 1] : true, ly = Y(lc);
      if (ly > pt && ly < pb) {
        C.setLineDash([2, 3]); C.strokeStyle = lup ? UP : DN; line(C, 0, Math.round(ly) + .5, pw, Math.round(ly) + .5); C.setLineDash([]);
        tag(C, pw, ly, fmt(lc, us), lup ? UP : DN, this.W - pw);
      }
      // 거래량
      C.save(); C.beginPath(); C.rect(0, vt, pw, vb - vt); C.clip();
      for (let i = i0; i <= i1; i++) {
        const up = B.c[i] > B.o[i] || (B.c[i] === B.o[i] && i > 0 && B.c[i] >= B.c[i - 1]);
        C.fillStyle = up ? "rgba(240,68,82,.75)" : "rgba(61,139,253,.75)";
        const y = VY(B.v[i]); C.fillRect(X(i) - body / 2, y, body, vb - y);
      }
      path(C, B.vma, i0, i1, X, VY, "#f5a524", 1); C.restore();
      C.fillStyle = AXT; C.font = "10px -apple-system,sans-serif"; C.textAlign = "left"; C.fillText(fvol(vmax), pw + 6, vt + 6);
      // RSI
      C.strokeStyle = GRID; [30, 50, 70].forEach(v => { C.setLineDash(v === 50 ? [] : [3, 3]); C.strokeStyle = v === 70 ? "rgba(240,68,82,.5)" : v === 30 ? "rgba(61,139,253,.5)" : GRID; line(C, 0, RY(v), pw, RY(v)); C.fillStyle = AXT; C.fillText(v, pw + 6, RY(v)); });
      C.setLineDash([]);
      C.save(); C.beginPath(); C.rect(0, rt, pw, rb - rt); C.clip(); path(C, B.rsi, i0, i1, X, RY, "#a78bfa", 1.4); C.restore();
      // 패널 이름
      C.fillStyle = AXT; C.font = "10px -apple-system,sans-serif"; C.textAlign = "left";
      const cI = Math.max(0, Math.min(B.N - 1, this.cross ? Math.round(this.cross.x / bw + (this.end - this.n) + 0.5) : last));
      label(C, `거래량 ${fvol(B.v[cI])} · 20평균 ${B.vma[cI] != null ? fvol(B.vma[cI]) : "-"}`, 4, vt + 7);
      label(C, `RSI(14) ${B.rsi[cI] != null ? B.rsi[cI].toFixed(1) : "-"}`, 4, rt + 7);
      // 십자선
      if (this.cross) {
        const x = X(cI), y = this.cross.y;
        C.strokeStyle = "rgba(232,238,245,.55)"; C.setLineDash([3, 3]); line(C, Math.round(x) + .5, pt, Math.round(x) + .5, rb);
        if (y >= pt && y <= pb) { line(C, 0, Math.round(y) + .5, pw, Math.round(y) + .5); C.setLineDash([]); tag(C, pw, y, fmt(yHi - (y - pt) / (pb - pt) * (yHi - yLo), us), "#3a4a5e", this.W - pw); }
        C.setLineDash([]);
        const ds = dstr(B.d[cI]); C.font = "bold 10px -apple-system,sans-serif"; const w = C.measureText(ds).width + 12;
        const bx = Math.max(0, Math.min(pw - w, x - w / 2)); C.fillStyle = "#3a4a5e"; rr(C, bx, this.H - DATEH + 2, w, DATEH - 4, 4); C.fill();
        C.fillStyle = TXT; C.textAlign = "center"; C.fillText(ds, bx + w / 2, this.H - DATEH / 2);
      }
      this.drawInfo(cI);
    }
    drawInfo(i) {
      const B = this.B, us = this.us, p = i > 0 ? B.c[i - 1] : B.o[i], ch = p ? B.c[i] / p - 1 : 0, col = ch > 0 ? UP : ch < 0 ? DN : AXT;
      const cc = v => `style="color:${v > p ? UP : v < p ? DN : TXT}"`;
      const tfn = {D: "", W: " 주", M: " 월"}[this.state.tf];
      const ma = this.state.ma ? MA.map(([n, c], k) => B.ma[k][i] != null ? `<span style="color:${c}">${n} ${fmt(B.ma[k][i], us)}</span>` : "").join("") : "";
      const mk = (B.mk[i] || []).map(m => `<div class="kc-mk">📢 ${m.tag ? `[${esc(m.tag)}] ` : ""}${esc(m.title || "")}</div>`).join("");
      this.info.innerHTML = `<div class="kc-l1"><b>${dstr(B.d[i])}${tfn}</b>
        <span>시 <i ${cc(B.o[i])}>${fmt(B.o[i], us)}</i></span><span>고 <i ${cc(B.h[i])}>${fmt(B.h[i], us)}</i></span>
        <span>저 <i ${cc(B.l[i])}>${fmt(B.l[i], us)}</i></span><span>종 <i style="color:${col}">${fmt(B.c[i], us)}</i></span>
        <span style="color:${col}">${ch > 0 ? "▲" : ch < 0 ? "▼" : ""}${(Math.abs(ch) * 100).toFixed(2)}%</span><span>거래량 ${fvol(B.v[i])}</span></div>
        ${ma ? `<div class="kc-l2">${ma}</div>` : ""}${mk}`;
    }
  }

  // ── 그리기 도우미 ──────────────────────────────
  function line(C, x1, y1, x2, y2) { C.beginPath(); C.moveTo(x1, y1); C.lineTo(x2, y2); C.stroke(); }
  function path(C, a, i0, i1, X, Y, col, w) {
    C.strokeStyle = col; C.lineWidth = w; C.beginPath(); let st = false;
    for (let i = i0; i <= i1; i++) { if (a[i] == null) { st = false; continue; } st ? C.lineTo(X(i), Y(a[i])) : C.moveTo(X(i), Y(a[i])); st = true; }
    C.stroke(); C.lineWidth = 1;
  }
  function rr(C, x, y, w, h, r) { C.beginPath(); C.moveTo(x + r, y); C.arcTo(x + w, y, x + w, y + h, r); C.arcTo(x + w, y + h, x, y + h, r); C.arcTo(x, y + h, x, y, r); C.arcTo(x, y, x + w, y, r); C.closePath(); }
  function tag(C, x, y, txt, bg, w) {
    C.font = "bold 10px -apple-system,sans-serif"; C.fillStyle = bg; rr(C, x + 1, y - 8, w - 2, 16, 3); C.fill();
    C.fillStyle = "#fff"; C.textAlign = "left"; C.fillText(txt, x + 5, y); C.font = "10px -apple-system,sans-serif";
  }
  function label(C, t, x, y) { C.lineWidth = 3; C.strokeStyle = BG; C.strokeText(t, x, y); C.lineWidth = 1; C.fillStyle = AXT; C.fillText(t, x, y); }
  function niceStep(raw) { const p = 10 ** Math.floor(Math.log10(raw || 1)), f = raw / p; return (f < 1.5 ? 1 : f < 3 ? 2 : f < 7 ? 5 : 10) * p; }
  function fmtAx(v, us, step) { return us ? v.toFixed(step < 1 ? 2 : step < 10 ? 1 : 0) : Math.round(v).toLocaleString("ko-KR"); }
  function esc(s) { return String(s ?? "").replace(/[&<>"]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c])); }

  window.KChart = KChart;
})();

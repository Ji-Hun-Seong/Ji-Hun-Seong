/* kchart.js — 증권사 앱 스타일 캔들 차트 (외부 라이브러리 없음)
 *
 *  손가락: 좌우로 끌기 = 이동(관성) · 두 손가락 = 확대/축소 · 탭/길게 누르기 = 십자선(누른 채 움직이면 따라감) · 다시 탭 = 끄기
 *  마우스: 끌기 = 이동 · 휠 = 확대/축소 · 올려 두기 = 십자선
 *  일/주/월/년봉 · 기간(3개월~상장 이후 전체) · 이평선 5/20/60/120 · 볼린저(20,2) 상한/중간/하한 · 거래량 · RSI(14)+Signal(6)
 *  화면 안 최고/최저(날짜·현재가 대비 %) · 현재가 태그(가격·등락률) · 공시 표시 · RSI 교차 화살표
 *
 *  new KChart(el, {d, o, h, l, c, v}, {markers: [{date: "2026-10-02", tag: "자사주", title: "..."}], us: false})
 */
(function () {
  const UP = "#f0465a", DN = "#3d7bf5", BG = "#0b0b0d", GRID = "#1b1b1f", SEP = "#2a2a30", AXT = "#c9c9ce", MUT = "#8a8a92", BAND = "#17171a";
  const MA = [[5, "#ff8a00"], [20, "#3d7bf5"], [60, "#5aa03c"], [120, "#22b58c"]];
  const BBC = {up: "#4a86ff", mid: "#ff9a1f", lo: "#5aa03c"}, RSIC = "#ff8a00", SIGC = "#5aa03c";
  const AXW = 76, DATEH = 24, FONT = "-apple-system,BlinkMacSystemFont,'Apple SD Gothic Neo',sans-serif";

  // ── 지표 ─────────────────────────────────────────
  function sma(a, n) {
    const out = new Array(a.length).fill(null); let s = 0, k = 0;
    for (let i = 0; i < a.length; i++) {
      if (a[i] == null) { out[i] = null; continue; }
      s += a[i]; k++; if (k > n) { s -= a[i - n] ?? 0; k = n; }
      if (k >= n) out[i] = s / n;
    }
    return out;
  }
  function boll(c, n = 20, k = 2) {
    const m = sma(c, n), up = new Array(c.length).fill(null), lo = up.slice();
    for (let i = n - 1; i < c.length; i++) {
      if (m[i] == null) continue; let v = 0; for (let j = i - n + 1; j <= i; j++) v += (c[j] - m[i]) ** 2;
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
  function aggregate(D, tf) {                        // 일봉 → 주/월/년봉
    if (tf === "D") return D;
    const key = s => {
      if (tf === "Y") return s.slice(0, 4);
      if (tf === "M") return s.slice(0, 6);
      const dt = new Date(+s.slice(0, 4), +s.slice(4, 6) - 1, +s.slice(6, 8)), day = (dt.getDay() + 6) % 7;
      const mon = new Date(dt - day * 864e5); return `${mon.getFullYear()}-${mon.getMonth()}-${mon.getDate()}`;
    };
    const R = {d: [], o: [], h: [], l: [], c: [], v: []}; let k0 = null;
    for (let i = 0; i < D.d.length; i++) {
      const k = key(D.d[i]);
      if (k !== k0) { R.d.push(D.d[i]); R.o.push(D.o[i]); R.h.push(D.h[i]); R.l.push(D.l[i]); R.c.push(D.c[i]); R.v.push(D.v[i]); k0 = k; }
      else { const j = R.d.length - 1; R.h[j] = Math.max(R.h[j], D.h[i]); R.l[j] = Math.min(R.l[j], D.l[i]); R.c[j] = D.c[i]; R.v[j] += D.v[i]; }
    }
    return R;
  }

  const fmt = (v, us) => v == null ? "-" : us ? Number(v).toLocaleString("en-US", {minimumFractionDigits: us === true ? 2 : us, maximumFractionDigits: us === true ? 2 : us})
    : Math.round(v).toLocaleString("ko-KR");
  const fvol = v => v >= 1e8 ? (v / 1e8).toFixed(1) + "억" : v >= 1e4 ? (v / 1e4).toFixed(v >= 1e6 ? 0 : 1) + "만" : Math.round(v).toLocaleString();
  const dstr = s => `${s.slice(2, 4)}.${s.slice(4, 6)}.${s.slice(6, 8)}`;
  const pctS = x => (x > 0 ? "+" : "") + (x * 100).toFixed(2) + "%";
  const RNG = [["3M", "3개월"], ["6M", "6개월"], ["1Y", "1년"], ["3Y", "3년"], ["5Y", "5년"], ["10Y", "10년"], ["ALL", "전체"]];
  const YRS = {"3M": .25, "6M": .5, "1Y": 1, "3Y": 3, "5Y": 5, "10Y": 10};

  class KChart {
    constructor(root, raw, opt = {}) {
      this.root = root; this.us = !!opt.us; this.markers = opt.markers || [];
      this.state = Object.assign({tf: "D", rng: "6M", ma: true, bb: true, sig: true}, opt.state || {});
      if (!RNG.some(r => r[0] === this.state.rng)) this.state.rng = "6M";
      this.onState = opt.onState || (() => {});
      const D = {d: [], o: [], h: [], l: [], c: [], v: []};
      for (let i = 0; i < raw.d.length; i++) if (raw.c[i] != null && raw.h[i] != null && raw.l[i] != null && raw.c[i] > 0) {
        D.d.push(raw.d[i]); D.c.push(raw.c[i]); D.o.push(raw.o[i] || raw.c[i]); D.h.push(raw.h[i]); D.l.push(raw.l[i]); D.v.push(raw.v[i] || 0);
      }
      this.daily = D;
      root.classList.add("kc");
      root.innerHTML = `
        <div class="kc-top">
          <div class="kc-dd"><button class="kc-ddb">관심지표 ▾</button><div class="kc-menu">
            <label><input type="checkbox" data-t="ma"> 이동평균선 5·20·60·120</label>
            <label><input type="checkbox" data-t="bb"> 볼린저밴드 (20, 2)</label>
            <label><input type="checkbox" data-t="sig"> RSI 교차 화살표</label></div></div>
          <select class="kc-rng">${RNG.map(([k, l]) => `<option value="${k}">${l}</option>`).join("")}</select>
          <span style="flex:1"></span>
          <button class="kc-ic kc-fs" title="크게 보기">⤢</button></div>
        <div class="kc-info"></div>
        <div class="kc-wrap"><canvas></canvas></div>
        <div class="kc-tf">${[["D", "일"], ["W", "주"], ["M", "월"], ["Y", "년"]].map(([k, l]) => `<button data-v="${k}">${l}</button>`).join("")}</div>`;
      this.cv = root.querySelector("canvas"); this.ctx = this.cv.getContext("2d"); this.info = root.querySelector(".kc-info");
      root.querySelectorAll(".kc-tf button").forEach(b => b.onclick = () => { this.state.tf = b.dataset.v; this.build(); this.changed(); });
      root.querySelector(".kc-rng").onchange = e => { this.state.rng = e.target.value; this.fitRange(); this.changed(); };
      const dd = root.querySelector(".kc-dd");
      root.querySelector(".kc-ddb").onclick = e => { e.stopPropagation(); dd.classList.toggle("on"); };
      this._docClick = e => { if (!dd.contains(e.target)) dd.classList.remove("on"); };
      document.addEventListener("click", this._docClick);
      root.querySelectorAll(".kc-menu input").forEach(c => c.onchange = () => { this.state[c.dataset.t] = c.checked; this.changed(); });
      root.querySelector(".kc-fs").onclick = () => this.fullscreen();
      this.cross = null; this.bind();
      this.build(); this.syncUI();
      this.ro = new ResizeObserver(() => this.resize()); this.ro.observe(root.querySelector(".kc-wrap"));
      this.resize();
    }
    changed() { this.syncUI(); this.onState(this.state); this.draw(); }
    destroy() { this.ro && this.ro.disconnect(); cancelAnimationFrame(this.anim); document.removeEventListener("click", this._docClick); if (this.fs) this.fullscreen(); }
    syncUI() {
      this.root.querySelectorAll(".kc-tf button").forEach(b => b.classList.toggle("act", this.state.tf === b.dataset.v));
      this.root.querySelectorAll(".kc-menu input").forEach(c => c.checked = !!this.state[c.dataset.t]);
      this.root.querySelector(".kc-rng").value = this.state.rng;
    }
    build() {
      const B = this.B = aggregate(this.daily, this.state.tf), c = B.c;
      B.ma = MA.map(([n]) => sma(c, n)); B.bb = boll(c); B.rsi = rsi(c); B.sig = sma(B.rsi, 6); B.N = c.length;
      B.x = [];                                    // RSI × Signal 교차 (과매도권 골든 ▲ / 과매수권 데드 ▼)
      for (let i = 1; i < B.N; i++) {
        const a = B.rsi[i], s = B.sig[i], pa = B.rsi[i - 1], ps = B.sig[i - 1];
        if ([a, s, pa, ps].some(v => v == null)) continue;
        if (pa <= ps && a > s && Math.min(a, pa) < 40) B.x.push([i, 1]);
        else if (pa >= ps && a < s && Math.max(a, pa) > 60) B.x.push([i, -1]);
      }
      B.mk = {};
      for (const m of this.markers) {
        const ds = String(m.date || "").replace(/-/g, ""); if (ds.length !== 8) continue;
        let lo = 0, hi = B.N - 1;                    // ds가 들어가는 봉 (마지막으로 시작일 ≤ ds)
        if (B.d[0] > ds) continue;
        while (lo < hi) { const mid = (lo + hi + 1) >> 1; if (B.d[mid] <= ds) lo = mid; else hi = mid - 1; }
        (B.mk[lo] = B.mk[lo] || []).push(m);
      }
      this.fitRange();
    }
    fitRange() {
      const N = this.B.N, perYr = {D: 250, W: 52, M: 12, Y: 1}[this.state.tf];
      let n = this.state.rng === "ALL" ? N : Math.round(YRS[this.state.rng] * perYr);
      const minN = {D: 20, W: 20, M: 12, Y: Math.min(N, 5)}[this.state.tf];
      n = Math.max(Math.min(minN, N), Math.min(n, N));
      this.n = n; this.end = N - 1 + Math.max(1, n * 0.04); this.cross = null;
    }
    resize() {
      const w = this.root.querySelector(".kc-wrap"), W = w.clientWidth;
      if (!W) return;
      const H = this.fs ? Math.max(260, w.clientHeight) : Math.round(Math.min(760, Math.max(520, W * 1.6)));
      const r = window.devicePixelRatio || 1;
      this.W = W; this.H = H; this.cv.width = Math.round(W * r); this.cv.height = Math.round(H * r);
      this.cv.style.width = W + "px"; this.cv.style.height = H + "px";
      this.ctx.setTransform(r, 0, 0, r, 0, 0); this.draw();
    }
    fullscreen() {
      this.fs = !this.fs; this.root.classList.toggle("kc-full", this.fs); document.body.style.overflow = this.fs ? "hidden" : "";
      this.root.querySelector(".kc-fs").textContent = this.fs ? "✕" : "⤢";
      requestAnimationFrame(() => this.resize());
    }
    get pw() { return this.W - AXW; }
    get bw() { return this.pw / this.n; }
    clamp() {
      const N = this.B.N;
      this.n = Math.max(Math.min(10, N), Math.min(this.n, N * 1.05 + 5));
      this.end = Math.max(this.n * 0.3 - 1, Math.min(this.end, N - 1 + this.n * 0.35));
    }
    panes() {
      const top = 26, avail = this.H - top - DATEH, ph = Math.round(avail * 0.56), vh = Math.round(avail * 0.16);
      const p = [top, top + ph], dband = [p[1], p[1] + DATEH], v = [dband[1] + 18, dband[1] + vh], r = [v[1] + 22, this.H - 6];
      return {p, dband, v, r};
    }

    // ── 입력 ───────────────────────────────────────
    bind() {
      const cv = this.cv, P = new Map(); let g = null, lpT = null, vel = 0, lastX = 0, lastT = 0;
      cv.style.touchAction = "pan-y";
      const local = e => { const r = cv.getBoundingClientRect(); return [e.clientX - r.left, e.clientY - r.top]; };
      const setCross = (x, y) => { this.cross = {x: Math.max(0, Math.min(x, this.pw - 1)), y}; this.draw(); };
      cv.addEventListener("pointerdown", e => {
        cancelAnimationFrame(this.anim); try { cv.setPointerCapture(e.pointerId); } catch (_) {}
        const [x, y] = local(e); P.set(e.pointerId, {x, y});
        if (P.size === 2) {
          clearTimeout(lpT); const [a, b] = [...P.values()];
          g = {mode: "pinch", d0: Math.abs(a.x - b.x) || 1, n0: this.n, cx: (a.x + b.x) / 2};
          g.ci = this.end - this.n + g.cx / this.bw; return;
        }
        g = {mode: "wait", x0: x, y0: y, end0: this.end, had: !!this.cross};
        lastX = x; lastT = performance.now(); vel = 0;
        if (e.pointerType !== "mouse") lpT = setTimeout(() => { if (g && g.mode === "wait") { g.mode = "cross"; setCross(x, y); navigator.vibrate && navigator.vibrate(8); } }, 320);
      });
      cv.addEventListener("pointermove", e => {
        const [x, y] = local(e), p = P.get(e.pointerId);
        if (!p) { if (e.pointerType === "mouse") setCross(x, y); return; }
        p.x = x; p.y = y; if (!g) return;
        if (g.mode === "pinch" && P.size >= 2) {
          const [a, b] = [...P.values()], d = Math.abs(a.x - b.x) || 1;
          this.n = g.n0 * g.d0 / d; this.clamp(); this.end = g.ci + this.n - g.cx / this.bw; this.clamp(); this.draw(); return;
        }
        if (g.mode === "wait" && (Math.abs(x - g.x0) > 6 || Math.abs(y - g.y0) > 6)) {
          clearTimeout(lpT); if (g.had && e.pointerType !== "mouse") g.mode = "cross"; else { g.mode = "pan"; this.cross = null; }
        }
        if (g.mode === "cross") return setCross(x, y);
        if (g.mode === "pan") {
          this.end = g.end0 - (x - g.x0) / this.bw; this.clamp();
          const t = performance.now(); vel = 0.8 * vel + 0.2 * ((x - lastX) / Math.max(1, t - lastT)); lastX = x; lastT = t;
          this.draw();
        }
      });
      const up = e => {
        const p = P.get(e.pointerId); P.delete(e.pointerId); clearTimeout(lpT);
        if (!g) return;
        if (g.mode === "pinch") { g = P.size ? {mode: "none"} : null; return; }
        if (g.mode === "wait" && p && e.type === "pointerup" && e.pointerType !== "mouse") {
          this.cross = this.cross ? null : {x: Math.min(p.x, this.pw - 1), y: p.y}; this.draw();
        } else if (g.mode === "pan" && Math.abs(vel) > 0.05 && performance.now() - lastT < 80) {
          let v = Math.max(-40, Math.min(40, vel * 16));
          const step = () => { this.end -= v / this.bw; this.clamp(); this.draw(); v *= 0.9; if (Math.abs(v) > 0.3) this.anim = requestAnimationFrame(step); };
          this.anim = requestAnimationFrame(step);
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
      if (!this.W || !this.B || !this.B.N) return;
      const C = this.ctx, B = this.B, S = this.state, us = this.us, bw = this.bw, pw = this.pw, W = this.W, H = this.H, PN = this.panes();
      C.fillStyle = BG; C.fillRect(0, 0, W, H);
      const i0 = Math.max(0, Math.floor(this.end - this.n)), i1 = Math.min(B.N - 1, Math.ceil(this.end));
      const X = i => (i - (this.end - this.n) - 0.5) * bw;
      if (i1 < i0) return;
      let hi = -Infinity, lo = Infinity, hiI = i0, loI = i0, vmax = 0;
      for (let i = i0; i <= i1; i++) {
        if (B.h[i] > hi) { hi = B.h[i]; hiI = i; } if (B.l[i] < lo) { lo = B.l[i]; loI = i; } vmax = Math.max(vmax, B.v[i]);
      }
      let yHi = hi, yLo = lo;
      const inc = a => { for (let i = i0; i <= i1; i++) if (a[i] != null) { yHi = Math.max(yHi, a[i]); yLo = Math.min(yLo, a[i]); } };
      if (S.ma) B.ma.forEach(inc); if (S.bb) { inc(B.bb.up); inc(B.bb.lo); }
      const pad = (yHi - yLo) * 0.07 || yHi * 0.02 || 1; yHi += pad; yLo -= pad;
      const [pt, pb] = PN.p, Y = v => pt + (yHi - v) / (yHi - yLo) * (pb - pt);
      const [vt, vb] = PN.v, VY = v => vb - v / (vmax || 1) * (vb - vt);
      const [rt, rb] = PN.r, RY = v => rb - v / 100 * (rb - rt);
      const f = (px, w = "") => C.font = `${w} ${px}px ${FONT}`;
      C.textBaseline = "middle"; C.lineWidth = 1;

      // 격자 · 가격 축
      const step = niceStep((yHi - yLo) / 4); f(11); C.textAlign = "left";
      for (let v = Math.ceil(yLo / step) * step; v <= yHi; v += step) {
        const y = Math.round(Y(v)) + .5; if (y < pt + 8 || y > pb - 6) continue;
        C.strokeStyle = GRID; line(C, 0, y, pw, y); C.fillStyle = AXT; C.fillText(fmtAx(v, us, step), pw + 8, y);
      }
      // 날짜 띠 (가격 패널 아래) · 세로 격자 4칸 고르게
      C.fillStyle = BAND; C.fillRect(0, PN.dband[0], pw, DATEH);
      f(11); C.textAlign = "center";
      for (let k = 0; k < 4; k++) {
        const px = pw * (0.12 + k * 0.255), i = Math.round(px / bw + (this.end - this.n) + 0.5);
        if (i < 0 || i >= B.N) continue; const x = Math.round(X(i)) + .5;
        C.strokeStyle = GRID; line(C, x, pt, x, pb); line(C, x, vt - 18, x, rb);
        C.fillStyle = MUT; C.fillText(S.tf === "Y" ? B.d[i].slice(0, 4) : S.tf === "M" ? `${B.d[i].slice(2, 4)}.${B.d[i].slice(4, 6)}` : dstr(B.d[i]), x, PN.dband[0] + DATEH / 2);
      }
      // 패널 구분선 · 오른쪽 축 구분선
      C.strokeStyle = SEP; [PN.dband[1], PN.v[1] + 3].forEach(y => line(C, 0, Math.round(y) + .5, W, Math.round(y) + .5));
      line(C, Math.round(pw) + .5, 0, Math.round(pw) + .5, H);

      // ── 가격 패널
      C.save(); C.beginPath(); C.rect(0, pt, pw, pb - pt); C.clip();
      const body = Math.max(1, bw * 0.7);
      for (let i = i0; i <= i1; i++) {
        const o = B.o[i], c = B.c[i], upb = c > o || (c === o && i > 0 && c >= B.c[i - 1]), col = upb ? UP : DN, x = X(i);
        C.strokeStyle = col; C.fillStyle = col; line(C, Math.round(x) + .5, Y(B.h[i]), Math.round(x) + .5, Y(B.l[i]));
        if (bw >= 2.5) { const y1 = Y(Math.max(o, c)), y2 = Y(Math.min(o, c)); C.fillRect(x - body / 2, y1, body, Math.max(1, y2 - y1)); }
      }
      if (S.ma) B.ma.forEach((a, k) => path(C, a, i0, i1, X, Y, MA[k][1], k ? 1.1 : 1.3));
      if (S.bb) { path(C, B.bb.up, i0, i1, X, Y, BBC.up, 1.5); path(C, B.bb.m, i0, i1, X, Y, BBC.mid, 1.5); path(C, B.bb.lo, i0, i1, X, Y, BBC.lo, 1.5); }
      for (let i = i0; i <= i1; i++) if (B.mk[i]) {                          // 공시
        const x = X(i), y = Math.min(pb - 8, Y(B.l[i]) + 13);
        C.fillStyle = "#ffb020"; C.beginPath(); C.moveTo(x, y - 5); C.lineTo(x - 5, y + 4); C.lineTo(x + 5, y + 4); C.fill();
      }
      C.restore();
      // 범례
      const leg = [];
      if (S.ma) MA.forEach(([n, c]) => leg.push([String(n), c]));
      if (S.bb) leg.push(["BB 상한(20,2)", BBC.up], ["중간", BBC.mid], ["하한", BBC.lo]);
      let lx = 6; f(11);
      for (const [t, c] of leg) { C.fillStyle = c; C.fillRect(lx, 12, 9, 2); C.textAlign = "left"; C.fillText(t, lx + 11, 13); lx += 11 + C.measureText(t).width + 8; }
      // 최고/최저 (날짜, 현재가 대비)
      const lastC = B.c[B.N - 1];
      [[hiI, hi, UP, -1], [loI, lo, DN, 1]].forEach(([i, v, col]) => {
        const x = X(i), y = Y(v), left = x > pw * 0.55;
        const t = `${fmt(v, us)}`, t2 = `(${dstr(B.d[i])}), ${pctS(lastC / v - 1)}`;
        f(12, "bold"); const w1 = C.measureText(t).width; f(11); const w2 = C.measureText(t2).width;
        const ax = left ? x - 6 : x + 6, tx = left ? ax - 16 - w1 - w2 : ax + 16;
        C.strokeStyle = col; C.fillStyle = col; line(C, ax, y, left ? ax - 12 : ax + 12, y);
        C.beginPath(); if (left) { C.moveTo(ax, y); C.lineTo(ax - 4, y - 3); C.lineTo(ax - 4, y + 3); } else { C.moveTo(ax, y); C.lineTo(ax + 4, y - 3); C.lineTo(ax + 4, y + 3); } C.fill();
        C.textAlign = "left"; f(12, "bold"); C.fillText(t, Math.max(2, tx), y); f(11); C.fillText(t2, Math.max(2, tx) + w1, y);
      });
      // 현재가 태그 (가격 + 등락률)
      const L = B.N - 1, prev = L > 0 ? B.c[L - 1] : B.o[L], ch = prev ? lastC / prev - 1 : 0, pc = ch > 0 ? UP : ch < 0 ? DN : "#55555c";
      const ly = Math.max(pt + 18, Math.min(pb - 18, Y(lastC)));
      if (Y(lastC) >= pt && Y(lastC) <= pb) { C.setLineDash([2, 3]); C.strokeStyle = pc; line(C, 0, Math.round(Y(lastC)) + .5, pw, Math.round(Y(lastC)) + .5); C.setLineDash([]); }
      ptag(C, pw, ly, [fmt(lastC, us), pctS(ch)], pc, W - pw, 34);

      // ── 거래량
      f(12); C.fillStyle = AXT; C.textAlign = "left"; C.fillText("거래량", 8, vt - 9);
      C.save(); C.beginPath(); C.rect(0, vt, pw, vb - vt); C.clip();
      for (let i = i0; i <= i1; i++) {
        const upb = B.c[i] > B.o[i] || (B.c[i] === B.o[i] && i > 0 && B.c[i] >= B.c[i - 1]);
        C.fillStyle = upb ? UP : DN; const y = VY(B.v[i]); C.fillRect(X(i) - body / 2, y, body, vb - y);
      }
      C.restore();
      f(11); C.fillStyle = AXT; C.fillText(fvol(vmax), pw + 8, vt + 6);
      ptag(C, pw, Math.max(vt + 22, Math.min(vb - 10, VY(B.v[L]))), [fvol(B.v[L])], "#5a5a62", W - pw, 20);

      // ── RSI
      const legR = [["RSI(14)", RSIC], ["Signal(6)", SIGC]]; let rx = 8; f(12);
      for (const [t, c] of legR) { C.fillStyle = c; C.fillRect(rx, rt - 11, 9, 2); C.fillText(t, rx + 11, rt - 10); rx += 11 + C.measureText(t).width + 10; }
      C.strokeStyle = "#3a3a40"; [70, 30].forEach(v => { line(C, 0, Math.round(RY(v)) + .5, pw, Math.round(RY(v)) + .5); f(11); C.fillStyle = MUT; C.textAlign = "left"; C.fillText(v, 4, RY(v) - 7); });
      C.save(); C.beginPath(); C.rect(0, rt - 2, pw, rb - rt + 4); C.clip();
      path(C, B.sig, i0, i1, X, RY, SIGC, 1.3); path(C, B.rsi, i0, i1, X, RY, RSIC, 1.5);
      if (S.sig && bw >= 3) for (const [i, d] of B.x) {      // 너무 촘촘하면 화살표 생략
        if (i < i0 || i > i1) continue; const x = X(i), y = RY(B.rsi[i]) + (d > 0 ? 9 : -9);
        C.fillStyle = d > 0 ? UP : DN; C.beginPath();
        if (d > 0) { C.moveTo(x, y - 5); C.lineTo(x - 4.5, y + 3); C.lineTo(x + 4.5, y + 3); } else { C.moveTo(x, y + 5); C.lineTo(x - 4.5, y - 3); C.lineTo(x + 4.5, y - 3); }
        C.fill();
      }
      C.restore();
      f(11); C.fillStyle = AXT; C.textAlign = "left"; C.fillText("50.00", pw + 8, RY(50));
      if (B.rsi[L] != null) ptag(C, pw, Math.max(rt + 8, Math.min(rb - 8, RY(B.rsi[L]))), [B.rsi[L].toFixed(2)], RSIC, W - pw, 20);

      // ── 십자선
      const cI = Math.max(0, Math.min(B.N - 1, this.cross ? Math.round(this.cross.x / bw + (this.end - this.n) + 0.5) : L));
      if (this.cross) {
        const x = Math.round(X(cI)) + .5, y = this.cross.y;
        C.strokeStyle = "rgba(220,220,228,.6)"; line(C, x, pt, x, rb);
        if (y >= pt && y <= pb) { line(C, 0, Math.round(y) + .5, pw, Math.round(y) + .5); ptag(C, pw, y, [fmt(yHi - (y - pt) / (pb - pt) * (yHi - yLo), us)], "#3c3c44", W - pw, 20); }
        else if (y >= vt && y <= vb) { line(C, 0, Math.round(y) + .5, pw, Math.round(y) + .5); ptag(C, pw, y, [fvol((vb - y) / (vb - vt) * vmax)], "#3c3c44", W - pw, 20); }
        else if (y >= rt && y <= rb) { line(C, 0, Math.round(y) + .5, pw, Math.round(y) + .5); ptag(C, pw, y, [((rb - y) / (rb - rt) * 100).toFixed(2)], "#3c3c44", W - pw, 20); }
        const ds = dstr(B.d[cI]); f(11, "bold"); const w = C.measureText(ds).width + 14, bx = Math.max(0, Math.min(pw - w, x - w / 2));
        C.fillStyle = "#3c3c44"; rr(C, bx, PN.dband[0] + 3, w, DATEH - 6, 4); C.fill(); C.fillStyle = "#fff"; C.textAlign = "center"; C.fillText(ds, bx + w / 2, PN.dband[0] + DATEH / 2);
      }
      this.drawInfo(cI);
    }
    drawInfo(i) {
      const B = this.B, us = this.us, p = i > 0 ? B.c[i - 1] : B.o[i], ch = p ? B.c[i] / p - 1 : 0, col = ch > 0 ? UP : ch < 0 ? DN : AXT;
      const cc = v => `style="color:${v > p ? UP : v < p ? DN : "#e8e8ec"}"`;
      const tfn = {D: "", W: " 주", M: " 월", Y: " 년"}[this.state.tf];
      const ma = this.state.ma ? MA.map(([n, c], k) => B.ma[k][i] != null ? `<span style="color:${c}">${n} ${fmt(B.ma[k][i], us)}</span>` : "").join("") : "";
      const mk = (B.mk[i] || []).map(m => `<div class="kc-mk">📢 ${m.tag ? `[${esc(m.tag)}] ` : ""}${esc(m.title || "")}</div>`).join("");
      this.info.innerHTML = `<div class="kc-l1"><b>${dstr(B.d[i])}${tfn}</b>
        <span>시 <i ${cc(B.o[i])}>${fmt(B.o[i], us)}</i></span><span>고 <i ${cc(B.h[i])}>${fmt(B.h[i], us)}</i></span>
        <span>저 <i ${cc(B.l[i])}>${fmt(B.l[i], us)}</i></span><span>종 <i style="color:${col}">${fmt(B.c[i], us)}</i></span>
        <span style="color:${col}">${ch > 0 ? "▲" : ch < 0 ? "▼" : ""}${(Math.abs(ch) * 100).toFixed(2)}%</span><span>거래량 ${fvol(B.v[i])}</span></div>
        ${ma ? `<div class="kc-l2">${ma}</div>` : ""}${mk}`;
    }
  }

  function line(C, x1, y1, x2, y2) { C.beginPath(); C.moveTo(x1, y1); C.lineTo(x2, y2); C.stroke(); }
  function path(C, a, i0, i1, X, Y, col, w) {
    C.strokeStyle = col; C.lineWidth = w; C.lineJoin = "round"; C.beginPath(); let st = false;
    for (let i = i0; i <= i1; i++) { if (a[i] == null) { st = false; continue; } st ? C.lineTo(X(i), Y(a[i])) : C.moveTo(X(i), Y(a[i])); st = true; }
    C.stroke(); C.lineWidth = 1;
  }
  function rr(C, x, y, w, h, r) { C.beginPath(); C.moveTo(x + r, y); C.arcTo(x + w, y, x + w, y + h, r); C.arcTo(x + w, y + h, x, y + h, r); C.arcTo(x, y + h, x, y, r); C.arcTo(x, y, x + w, y, r); C.closePath(); }
  function ptag(C, x, y, lines, bg, w, h) {         // 오른쪽 축의 화살표 모양 가격 태그
    h = Math.max(h, lines.length * 15 + 5); const t = y - h / 2;
    C.fillStyle = bg; C.beginPath(); C.moveTo(x + 2, y); C.lineTo(x + 8, t); C.lineTo(x + w, t); C.lineTo(x + w, t + h); C.lineTo(x + 8, t + h); C.closePath(); C.fill();
    C.fillStyle = "#fff"; C.textAlign = "left";
    lines.forEach((s, k) => { C.font = `${k ? "" : "bold"} ${k ? 10.5 : 11.5}px ${FONT}`; C.fillText(s, x + 11, t + 10 + k * 15 + (lines.length === 1 ? (h - 20) / 2 : 0)); });
  }
  function niceStep(raw) { const p = 10 ** Math.floor(Math.log10(raw || 1)), f = raw / p; return (f < 1.5 ? 1 : f < 3 ? 2 : f < 7 ? 5 : 10) * p; }
  function fmtAx(v, us, step) { return us ? v.toFixed(step < 1 ? 2 : step < 10 ? 1 : 0) : Math.round(v).toLocaleString("ko-KR"); }
  function esc(s) { return String(s ?? "").replace(/[&<>"]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c])); }

  window.KChart = KChart;
})();

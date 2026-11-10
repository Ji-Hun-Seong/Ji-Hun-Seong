/* 백과사전 — 마스터로드·펀드로드 공용. 앱마다 <앱>/dict/terms.json 을 읽는다.
   · 용어·별칭이 정확히 맞으면 바로 그 항목으로 들어간다 (예: '배당락일' → 배당락일 항목)
   · 본문에만 나오는 말이면 그 절로 스크롤하고 형광펜 표시
   · 레슨·심화 글·백과 본문 속 용어는 자동으로 밑줄 링크 → 누르면 그 항목으로
   deep.js 의 dpBlock 을 그대로 써서 글 형식(p·ul·tip·calc·table·f·j)이 같다. 형식: deep-study/DICT.md */
"use strict";
const DC = {list: null, err: "", q: "", by: {}, id: {}, rx: null, cfg: {}};
const dcNorm = s => String(s || "").toLowerCase().replace(/[\s·・()\[\]{}'"’‘“”,.\-_/]/g, "");
const dcPlain = s => String(s || "").replace(/<[^>]+>/g, "");
function dcBlockText(b) { if (b.hero) return [b.hero.title, b.hero.sub, ...(b.hero.stats || []).flat()].join(" "); if (b.kv) return b.kv.flat().join(" "); if (b.tl) return b.tl.map(x => [x.d, x.t, x.x, x.me].join(" ")).join(" "); if (b.pts) return b.pts.map(x => x.t + " " + x.x).join(" "); if (b.donut) return b.donut.items.map(x => x[0] + " " + (x[2] || "")).join(" "); if (b.pc) return [...b.pc.bad, ...b.pc.good].join(" "); if (b.branch) return b.branch.map(x => [x.t, x.x, x.r].join(" ")).join(" "); if (b.callout != null) return b.callout; if (b.ex) return [b.ex.title, b.ex.l.t, b.ex.r.t, b.ex.top.t, b.ex.bot && b.ex.bot.t, b.ex.note].join(" "); if (b.chain) return [b.chain.title, ...b.chain.nodes.map(n => [n.t, n.x, n.go].join(" "))].join(" "); if (b.p != null) return b.p; if (b.tip != null) return b.tip; if (b.ul) return b.ul.join(" "); if (b.calc) return b.calc.join(" ");
  if (b.table) return [b.table.head, ...b.table.rows].flat().join(" "); if (b.f) return (b.f.steps || []).join(" ");
  if (b.j) return b.j.map(r => r.note || [r.pre, ...(r.dr || []).flat(), ...(r.cr || []).flat()].join(" ")).join(" "); return ""; }
const dcRe = s => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

async function dcLoad() {
  try { const r = await fetch("dict/terms.json?v=" + new Date().toISOString().slice(0, 13)); if (!r.ok) throw 0; const j = await r.json(); dcIndex(j.terms || j); DC.err = ""; }
  catch (e) { DC.err = "백과를 불러오지 못했어요"; DC.list = DC.list || []; }
  if (!cur() ? V.tab === "dict" : ["dterm", "lesson", "dtopic", ...(DC.cfg.linkViews || [])].includes(cur().v)) render();
}
function dcIndex(list) {
  DC.list = list; DC.by = {}; DC.id = {};
  const link = [];
  list.forEach(e => {
    DC.id[e.id] = e;
    e._keys = [e.k, ...(e.al || []), ...(e.al2 || []), e.en || ""].filter(Boolean);
    e._nk = e._keys.map(dcNorm);
    e._nk.forEach(k => { if (k && !DC.by[k]) DC.by[k] = e; });
    e._sec = (e.sec || []).map(s => dcPlain(s.b.map(dcBlockText).join(" ")));
    e._all = dcPlain(e.one) + " " + e._sec.join(" ");
    [e.k, ...(e.al || [])].forEach(k => { if (k && k.length >= 2) link.push([k, e.id]); });
  });
  link.sort((a, b) => b[0].length - a[0].length);
  DC.linkMap = {}; link.forEach(([k, id]) => { if (!DC.linkMap[k.toLowerCase()]) DC.linkMap[k.toLowerCase()] = id; });
  DC.rx = link.length ? new RegExp(link.map(([k]) => /^[A-Za-z0-9/&.\- ]+$/.test(k) ? `(?<![A-Za-z])${dcRe(k)}(?![A-Za-z])` : dcRe(k)).join("|"), "gi") : null;
}
const dcRel = e => (e.rel || []).map(k => DC.by[dcNorm(k)]).filter(x => x && x !== e);

/* ── 검색 ── */
function dcSearch(q) {
  const qn = dcNorm(q), ql = q.trim().toLowerCase(); if (!qn) return null;
  const terms = [];
  DC.list.forEach(e => {
    let sc = 0, why = "", sec = -1;
    e._nk.forEach((k, i) => { if (!k) return; let s = 0;
      if (k === qn) s = 1000; else if (k.startsWith(qn)) s = 700 - (k.length - qn.length); else if (k.includes(qn)) s = 500 - (k.length - qn.length);
      else if (qn.length >= 2 && qn.includes(k) && k.length >= 2) s = 300 + k.length * 5;
      if (s > sc) { sc = s; why = i ? e._keys[i] : ""; } });
    if (sc < 300) { const n = dcNorm(e._all).split(qn).length - 1; if (n) { sc = Math.max(sc, 100 + Math.min(n, 20) * 5); sec = e._sec.findIndex(t => dcNorm(t).includes(qn)); } }
    if (sc) terms.push({e, sc, why, sec, snip: sec >= 0 ? dcSnip(e._sec[sec], ql) : ""});
  });
  terms.sort((a, b) => b.sc - a.sc || a.e.k.length - b.e.k.length);
  const lessons = (DC.cfg.lessons ? DC.cfg.lessons() : []).filter(l => dcNorm(l.text).includes(qn) || dcNorm(l.t).includes(qn)).map(l => ({...l, snip: dcSnip(l.text, ql)}));
  const deeps = (window.DP && DP.idx ? DP.idx.topics : []).filter(m => dcNorm(m.t + m.area + m.sum + (m.kw || []).join(" ")).includes(qn));
  return {terms, lessons, deeps, exact: terms[0] && terms[0].sc >= 1000 ? terms[0].e : null};
}
function dcSnip(t, ql) { const i = t.toLowerCase().indexOf(ql); if (i < 0) return ""; const a = Math.max(0, i - 28), b = Math.min(t.length, i + ql.length + 40);
  return (a ? "…" : "") + esc(t.slice(a, i)) + "<mark>" + esc(t.slice(i, i + ql.length)) + "</mark>" + esc(t.slice(i + ql.length, b)) + (b < t.length ? "…" : ""); }

function dcTermBtn(e, extra = "") { return `<button class="bki" data-act="dcopen" data-arg="${esc(e.id)}"><span class="between"><b>${esc(e.k)}${e.en ? ` <small class="mut xs" style="display:inline;font-weight:600">${esc(e.en)}</small>` : ""}</b><span class="mut xs">${esc(e.area)}</span></span><small class="mut">${extra || esc(e.one)}</small></button>`; }
function dcResults() {
  if (!DC.list) return `<p class="mut" style="text-align:center;margin:30px 0">불러오는 중…</p>`;
  const r = dcSearch(DC.q);
  if (!r) return dcHome();
  const {terms, lessons, deeps, exact} = r;
  let h = "";
  if (exact) h += `<div class="dcx" data-act="dcopen" data-arg="${esc(exact.id)}"><span class="mut xs">${terms[0].why ? `'${esc(terms[0].why)}' → ` : ""}바로 가기</span><b>${esc(exact.k)}</b><small>${esc(exact.one)}</small><span class="go">${ic("play")} 열기</span></div>`;
  const rest = terms.filter(t => t.e !== exact);
  if (rest.length) h += `<div class="bkh">백과 항목 ${rest.length}</div>` + rest.slice(0, 30).map(t => dcTermBtn(t.e, t.snip ? `<span class="xs">${esc(t.e.sec[t.sec].h)} · </span>${t.snip}` : t.why ? `'${esc(t.why)}'로도 불러요 · ${esc(t.e.one)}` : "")).join("");
  if (lessons.length) h += `<div class="bkh">기초 레슨 ${lessons.length}</div>` + lessons.slice(0, 12).map(l => `<button class="bki" data-act="dclesson" data-arg="${esc(l.id)}"><b>${esc(l.t)}</b><small class="mut">${l.snip || esc(l.sub || "")}</small></button>`).join("");
  if (deeps.length) h += `<div class="bkh">심화 글 ${deeps.length}</div>` + deeps.map(m => `<button class="bki" data-act="dopen" data-arg="${esc(m.id)}"><b>${esc(m.t)}</b><small class="mut">${esc(m.sum)}</small></button>`).join("");
  return h || `<div class="card mut sm" style="text-align:center">'${esc(DC.q)}' 항목이 아직 없어요.<br>백과는 매일 늘어나요. 비슷한 말(예: 띄어쓰기 없이, 영문 약자)로도 찾아보세요.</div>`;
}
function dcHome() {
  const areas = [...new Set(DC.list.map(e => e.area))], rec = (S.dcRecent || []).map(id => DC.id[id]).filter(Boolean);
  const pick = (DC.cfg.featured || []).map(k => DC.by[dcNorm(k)]).filter(Boolean);
  return (DC.cfg.tools || []).filter(t => ACT[t.act]).map(t => `<button class="menu" data-act="${t.act}"><span class="t">${ic("target")}</span><span><b>${esc(t.label)}</b><small>${esc(t.sub || "")}</small></span></button>`).join("") + (rec.length ? `<div class="bkh">최근 본 항목</div><div class="dchips">${rec.map(e => `<button data-act="dcopen" data-arg="${esc(e.id)}">${esc(e.k)}</button>`).join("")}</div>` : "")
    + (pick.length ? `<div class="bkh">자주 찾는 말</div><div class="dchips">${pick.map(e => `<button data-act="dcopen" data-arg="${esc(e.id)}">${esc(e.k)}</button>`).join("")}</div>` : "")
    + areas.map(a => { const es = DC.list.filter(e => e.area === a).sort((x, y) => x.k.localeCompare(y.k, "ko"));
      return `<details class="dcar"><summary><b>${esc(a)}</b><span class="mut sm">${es.length}개</span></summary>${es.map(e => dcTermBtn(e)).join("")}</details>`; }).join("");
}


/* ── 시각 블록(인포그래픽) ── */
const VI = {users: '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20a6.5 6.5 0 0 1 13 0"/><circle cx="17" cy="9" r="2.5"/><path d="M16 14.2a5 5 0 0 1 5.5 5.8"/>', doc: '<path d="M14 3H6a1 1 0 0 0-1 1v16a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V8z"/><path d="M14 3v5h5M8.5 12.5h7M8.5 16.5h7"/>', coin: '<ellipse cx="12" cy="6.5" rx="7" ry="3"/><path d="M5 6.5v5c0 1.7 3.1 3 7 3s7-1.3 7-3v-5M5 11.5v5c0 1.7 3.1 3 7 3s7-1.3 7-3v-5"/>', mega: '<path d="M3 10v4a1 1 0 0 0 1 1h2l5 4V5L6 9H4a1 1 0 0 0-1 1z"/><path d="M15.5 8.5a5 5 0 0 1 0 7M18.5 5.5a9 9 0 0 1 0 13"/>', bank: '<path d="M3 9.5 12 4l9 5.5M5 10v8M9.5 10v8M14.5 10v8M19 10v8M3 20.5h18"/>', up: '<path d="M3 17l6-6 4 4 8-8"/><path d="M15 7h6v6"/>', down: '<path d="M3 7l6 6 4-4 8 8"/><path d="M15 17h6v-6"/>', cal: '<rect x="3.5" y="5" width="17" height="15.5" rx="2"/><path d="M3.5 10h17M8 3v4M16 3v4"/>', target: '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1.5"/>', flag: '<path d="M5 21V4h11l-2 4 2 4H5"/>', alert: '<path d="M10.3 4 2.5 18a2 2 0 0 0 1.7 3h15.6a2 2 0 0 0 1.7-3L13.7 4a2 2 0 0 0-3.4 0z"/><path d="M12 9.5v4.5M12 17.5h.01"/>', check: '<circle cx="12" cy="12" r="9"/><path d="m8 12.5 2.7 2.7L16.5 9.5"/>', cash: '<rect x="2.5" y="6" width="19" height="12" rx="2"/><circle cx="12" cy="12" r="2.8"/><path d="M6 9.5v5M18 9.5v5"/>', building: '<path d="M4 21V5a1 1 0 0 1 1-1h9a1 1 0 0 1 1 1v16M15 10h4a1 1 0 0 1 1 1v10M2.5 21h19M8 8h3M8 12h3M8 16h3"/>', clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3.5 2"/>', bond: '<path d="M6 3h9l4 4v14H6z"/><path d="M9 11h7M9 15h7M9 7h3"/>', pct: '<path d="M19 5 5 19"/><circle cx="7" cy="7" r="2.5"/><circle cx="17" cy="17" r="2.5"/>', swap: '<path d="M4 8h14l-3.5-3.5M20 16H6l3.5 3.5"/>', key: '<circle cx="8" cy="15" r="4.5"/><path d="m11.2 11.8 8.8-8.8M16.5 6.5l2.5 2.5"/>', calc: '<rect x="5" y="2.5" width="14" height="19" rx="2"/><path d="M8 6.5h8M8.5 11h.01M12 11h.01M15.5 11h.01M8.5 14.5h.01M12 14.5h.01M15.5 14.5h.01M8.5 18h.01M12 18h3.5"/>', bulb: '<path d="M15 14c.2-1 .7-1.7 1.5-2.5 1-.9 1.5-2.2 1.5-3.5A6 6 0 0 0 6 8c0 1 .2 2.2 1.5 3.5.7.7 1.3 1.5 1.5 2.5M9 18h6M10 22h4"/>', x: '<circle cx="12" cy="12" r="9"/><path d="m9 9 6 6M15 9l-6 6"/>'};
const vi = (n, sz = 22) => `<svg viewBox="0 0 24 24" width="${sz}" height="${sz}" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${VI[n] || VI.check}</svg>`;
const VC = ["#1d9bd1", "#1fa463", "#2f6fe4", "#7b5cff", "#f0a40b", "#1e3a8a", "#e0457b", "#0f9d8a"];
const TONE = {acc: "var(--acc)", gold: "var(--gold)", bad: "var(--bad)", blue: "#2f6fe4", violet: "#7b5cff"};
function dcDonut(o) { const tot = o.items.reduce((s, x) => s + x[1], 0), R = 52, C = 2 * Math.PI * R; let off = 0;
  const seg = o.items.map((x, i) => { const L = x[1] / tot * C, r = `<circle r="${R}" cx="70" cy="70" fill="none" stroke="${VC[i % VC.length]}" stroke-width="26" stroke-dasharray="${L} ${C - L}" stroke-dashoffset="${-off}" transform="rotate(-90 70 70)"/>`; off += L; return r; }).join("");
  return `<div class="vx-donut"><svg viewBox="0 0 140 140">${seg}<text x="70" y="66" text-anchor="middle" class="vx-dt1">${esc(o.center || "합계")}</text><text x="70" y="84" text-anchor="middle" class="vx-dt2">${esc(o.total || "")}</text></svg><div class="vx-leg">${o.items.map((x, i) => `<div><i style="background:${VC[i % VC.length]}"></i><span>${esc(x[0])}</span><b>${(x[1] / tot * 100).toFixed(1)}%</b>${x[2] ? `<small>${esc(x[2])}</small>` : ""}</div>`).join("")}</div></div>`; }
function dcBlock(b) {
  if (b.hero) { const h = b.hero; return `<div class="vx-hero">${h.kicker ? `<span class="vx-kick">${esc(h.kicker)}</span>` : ""}<div class="vx-ht">${esc(h.title)}</div>${h.sub ? `<div class="vx-hs">${esc(h.sub)}</div>` : ""}${(h.stats || []).length ? `<div class="vx-stats">${h.stats.map(s => `<div><b>${esc(s[1])}</b><small>${esc(s[0])}</small></div>`).join("")}</div>` : ""}</div>`; }
  if (b.kv) return `<div class="vx-kv">${b.kv.map(r => `<div><span>${esc(r[0])}</span><b>${esc(r[1])}</b></div>`).join("")}</div>`;
  if (b.tl) return `<div class="vx-tl">${b.tl.map((s, i) => `<div class="vx-st"><span class="vx-ic" style="background:${VC[i % VC.length]}">${vi(s.i || "cal", 20)}</span><div class="vx-sb"><div class="vx-sh">${s.d ? `<span class="vx-date">${esc(s.d)}</span>` : ""}<b>${esc(s.t)}</b></div>${s.x ? `<div class="vx-sx">${esc(s.x)}</div>` : ""}${s.me ? `<div class="vx-me">${vi("check", 14)}<span>${esc(s.me)}</span></div>` : ""}</div></div>`).join("")}</div>`;
  if (b.pts) return `<div class="vx-pts">${b.pts.map((p, i) => `<div class="vx-pt"><span class="vx-pi" style="color:${VC[(i + (b.c || 0)) % VC.length]}">${vi(p.i || "check", 24)}</span><div><b>${esc(p.t)}</b><div>${esc(p.x)}</div></div></div>`).join("")}</div>`;
  if (b.donut) return dcDonut(b.donut);
  if (b.pc) return `<div class="vx-pc"><div class="vx-bad"><div class="vx-pch">${vi("down", 26)}<b>${esc(b.pc.badT || "부담 요인")}</b></div><ul>${b.pc.bad.map(t => `<li>${esc(t)}</li>`).join("")}</ul></div><div class="vx-good"><div class="vx-pch">${vi("up", 26)}<b>${esc(b.pc.goodT || "기대 요인")}</b></div><ul>${b.pc.good.map(t => `<li>${esc(t)}</li>`).join("")}</ul></div></div>`;
  if (b.branch) return `<div class="vx-br">${b.branch.map(x => `<div class="vx-bc" style="--tc:${TONE[x.tone] || "var(--acc)"}"><div class="vx-bt">${vi(x.i || "check", 18)}<b>${esc(x.t)}</b></div><div class="vx-bx">${esc(x.x)}</div>${x.r ? `<div class="vx-brs">${esc(x.r)}</div>` : ""}</div>`).join("")}</div>`;
  if (b.ex) return dcEx(b.ex);
  if (b.chain) return dcChain(b.chain);
  if (b.callout != null) return `<div class="vx-call">${vi("bulb", 22)}<span>${esc(b.callout)}</span></div>`;
  return dpBlock(b);
}
const VXCSS = `.vx-hero{border-radius:18px;padding:18px 16px;margin:6px 0 14px;background:linear-gradient(135deg,#132a6b,#1d4fa8 60%,#2a7de1);color:#fff;box-shadow:0 8px 24px rgba(15,40,110,.25)}
.vx-kick{display:inline-block;font-size:12px;font-weight:800;background:rgba(255,255,255,.18);padding:4px 9px;border-radius:7px;margin-bottom:8px}.vx-ht{font-size:23px;font-weight:900;line-height:1.3;letter-spacing:-.03em}.vx-hs{font-size:14.5px;line-height:1.55;opacity:.92;margin-top:6px}
.vx-stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(96px,1fr));gap:8px;margin-top:14px}.vx-stats div{background:rgba(255,255,255,.13);border-radius:12px;padding:9px 10px}.vx-stats b{display:block;font-size:17px;font-weight:900;font-variant-numeric:tabular-nums;color:#fff!important}.vx-stats small{font-size:11.5px;opacity:.85}
.vx-kv{border:1px solid var(--line);border-radius:14px;overflow:hidden;margin:10px 0}.vx-kv div{display:flex;justify-content:space-between;gap:12px;padding:10px 12px;font-size:14px;border-bottom:1px solid var(--line)}.vx-kv div:last-child{border-bottom:0}.vx-kv div:nth-child(odd){background:var(--bg2)}.vx-kv span{color:var(--sub);flex:0 0 auto}.vx-kv b{text-align:right;color:var(--txt)!important;font-variant-numeric:tabular-nums}
.vx-tl{margin:12px 0;position:relative}.vx-st{display:flex;gap:12px;position:relative;padding-bottom:14px}.vx-st:not(:last-child)::before{content:"";position:absolute;left:19px;top:40px;bottom:0;width:2px;background:var(--line)}.vx-ic{width:40px;height:40px;border-radius:50%;display:grid;place-items:center;color:#fff;flex:0 0 auto;box-shadow:0 3px 8px rgba(0,0,0,.18)}
.vx-sb{flex:1;background:var(--bg2);border:1px solid var(--line);border-radius:12px;padding:9px 11px}.vx-sh{display:flex;align-items:center;gap:8px;flex-wrap:wrap}.vx-sh b{font-size:15px;color:var(--txt)!important}.vx-date{font-size:12px;font-weight:800;color:#fff;background:#1e3a8a;border-radius:6px;padding:2px 7px;font-variant-numeric:tabular-nums}.vx-sx{font-size:13.5px;color:var(--sub);line-height:1.55;margin-top:4px}.vx-me{display:flex;gap:6px;align-items:flex-start;font-size:13px;line-height:1.5;margin-top:6px;padding-top:6px;border-top:1px dashed var(--line);color:var(--acc)}.vx-me span{color:var(--txt)}.vx-me svg{margin-top:2px;flex:0 0 auto}
.vx-pts{display:grid;gap:8px;margin:10px 0}.vx-pt{display:flex;gap:12px;align-items:flex-start;background:var(--bg2);border:1px solid var(--line);border-radius:14px;padding:12px}.vx-pi{width:44px;height:44px;border-radius:50%;display:grid;place-items:center;background:var(--card);border:1px solid var(--line);flex:0 0 auto}.vx-pt b{display:block;font-size:15.5px;color:var(--txt)!important;margin-bottom:2px}.vx-pt div div{font-size:13.5px;color:var(--sub);line-height:1.55}
.vx-donut{display:flex;align-items:center;gap:14px;margin:12px 0;flex-wrap:wrap}.vx-donut svg{width:140px;height:140px;flex:0 0 auto}.vx-dt1{font-size:11px;fill:var(--sub)}.vx-dt2{font-size:15px;font-weight:900;fill:var(--txt)}.vx-leg{flex:1;min-width:150px;display:grid;gap:8px}.vx-leg div{display:grid;grid-template-columns:12px 1fr auto;gap:2px 8px;align-items:center;font-size:13.5px}.vx-leg i{width:12px;height:12px;border-radius:3px}.vx-leg b{color:var(--txt)!important}.vx-leg small{grid-column:2/4;color:var(--sub);font-size:12px}
.vx-pc{display:grid;gap:8px;margin:10px 0}.vx-pc>div{border-radius:14px;padding:12px 14px}.vx-bad{background:var(--bad-soft);border:1px solid rgba(229,72,77,.35)}.vx-good{background:var(--acc-soft);border:1px solid rgba(31,164,99,.35)}.vx-pch{display:flex;align-items:center;gap:8px;margin-bottom:6px}.vx-bad .vx-pch{color:var(--bad)}.vx-good .vx-pch{color:var(--acc)}.vx-pch b{font-size:15px;color:inherit!important}.vx-pc ul{margin:0;padding-left:18px}.vx-pc li{font-size:14px!important;line-height:1.6!important;margin:3px 0!important}
.vx-br{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin:10px 0}.vx-bc{border:1px solid var(--line);border-top:4px solid var(--tc);border-radius:12px;padding:10px;background:var(--bg2)}.vx-bt{display:flex;gap:6px;align-items:center;color:var(--tc)}.vx-bt b{font-size:14.5px;color:var(--txt)!important}.vx-bx{font-size:13px;color:var(--sub);line-height:1.5;margin-top:5px}.vx-brs{font-size:12.5px;font-weight:800;margin-top:7px;color:var(--tc)}
.vx-call{display:flex;gap:10px;align-items:center;background:#1e3a8a;color:#fff;border-radius:14px;padding:13px 14px;margin:12px 0;font-size:14.5px;line-height:1.55;font-weight:700}.vx-call svg{color:#ffd54a;flex:0 0 auto}
.dterm .dtop{border-radius:18px;margin:-6px -4px 14px;padding:16px;background:linear-gradient(135deg,var(--acc-soft),transparent 70%);border:1px solid var(--line)}`;


/* ── 일러스트(그림 블록용) ── */
const ART = {
 company: '<rect x="12" y="10" width="36" height="62" rx="3" fill="#3a6fd8"/><rect x="48" y="30" width="22" height="42" rx="2" fill="#2852a8"/><g fill="#cfe0ff">' + [0, 1, 2, 3, 4].map(r => [0, 1, 2].map(c => `<rect x="${17 + c * 10}" y="${16 + r * 10}" width="6" height="6" rx="1"/>`).join("")).join("") + '<rect x="53" y="36" width="5" height="5" rx="1"/><rect x="61" y="36" width="5" height="5" rx="1"/><rect x="53" y="45" width="5" height="5" rx="1"/><rect x="61" y="45" width="5" height="5" rx="1"/></g><rect x="25" y="62" width="10" height="10" fill="#1d3f86"/><rect x="6" y="72" width="68" height="3" rx="1.5" fill="#94a9d6"/>',
 investors: '<g><circle cx="24" cy="30" r="9" fill="#f2c9a0"/><path d="M15 27a9 8 0 0 1 18 0c-3-3-9-4-18 0z" fill="#3b2a20"/><path d="M8 66c0-12 7-20 16-20s16 8 16 20z" fill="#4f7fe0"/></g><g><circle cx="56" cy="30" r="9" fill="#f2c9a0"/><path d="M47 28a9 9 0 0 1 18 0c-2-4-10-5-18 0z" fill="#2b211b"/><path d="M40 66c0-12 7-20 16-20s16 8 16 20z" fill="#2b4d9b"/></g><g><circle cx="40" cy="36" r="9.5" fill="#f5cfa8"/><path d="M30 37c0-8 4-12 10-12s10 4 10 12c-2-5-6-7-10-7s-8 2-10 7z" fill="#4a3226"/><path d="M23 72c0-12 8-21 17-21s17 9 17 21z" fill="#ec7f9b"/></g>',
 person: '<circle cx="40" cy="28" r="12" fill="#f2c9a0"/><path d="M28 25a12 11 0 0 1 24 0c-4-4-12-5-24 0z" fill="#3b2a20"/><path d="M18 72c0-15 10-26 22-26s22 11 22 26z" fill="#4f7fe0"/>',
 stock: '<rect x="8" y="16" width="64" height="46" rx="4" fill="#fff6dc" stroke="#d9b56b" stroke-width="2"/><rect x="13" y="21" width="54" height="36" rx="2" fill="none" stroke="#e8cf92" stroke-width="1.5"/><text x="40" y="34" text-anchor="middle" font-size="9" font-weight="800" fill="#6b5420">주식</text><path d="M20 41h28M20 47h22" stroke="#cdb57a" stroke-width="2" stroke-linecap="round"/><circle cx="58" cy="50" r="7" fill="#f2b632" stroke="#c98d12" stroke-width="1.5"/><path d="M54 55l-2 9 6-3 6 3-2-9" fill="#d9483b"/>',
 bond: '<rect x="12" y="10" width="52" height="62" rx="4" fill="#eef4ff" stroke="#8fb0e8" stroke-width="2"/><text x="38" y="26" text-anchor="middle" font-size="9" font-weight="800" fill="#2a56b3">채권</text><path d="M20 34h36M20 41h28M20 48h32" stroke="#a9c2ec" stroke-width="2.5" stroke-linecap="round"/><circle cx="56" cy="60" r="10" fill="#2f6fe4"/><text x="56" y="64" text-anchor="middle" font-size="11" font-weight="900" fill="#fff">%</text>',
 money: '<g transform="translate(6 30)"><rect x="0" y="20" width="64" height="16" rx="3" fill="#2f9e5b"/><rect x="2" y="12" width="64" height="16" rx="3" fill="#38b26a"/><rect x="4" y="4" width="64" height="16" rx="3" fill="#47c47b"/><rect x="4" y="4" width="64" height="16" rx="3" fill="none" stroke="#1f7a44" stroke-width="1.5"/><circle cx="36" cy="12" r="5.5" fill="#d8f5e3"/><text x="36" y="15.5" text-anchor="middle" font-size="8" font-weight="900" fill="#1f7a44">₩</text><rect x="30" y="2" width="12" height="20" fill="#f2f2f2" opacity=".85"/></g>',
 coin: '<ellipse cx="40" cy="58" rx="22" ry="7" fill="#c98d12"/><rect x="18" y="44" width="44" height="14" fill="#e7a91d"/><ellipse cx="40" cy="44" rx="22" ry="7" fill="#f6c443"/><ellipse cx="40" cy="36" rx="22" ry="7" fill="#c98d12"/><rect x="18" y="24" width="44" height="12" fill="#e7a91d"/><ellipse cx="40" cy="24" rx="22" ry="7" fill="#f8d063"/><text x="40" y="27.5" text-anchor="middle" font-size="9" font-weight="900" fill="#8a5c00">₩</text>',
 bank: '<path d="M8 28 40 10l32 18z" fill="#5a6f9e"/><rect x="10" y="28" width="60" height="6" fill="#47598a"/><g fill="#9fb2db">' + [0, 1, 2, 3].map(i => `<rect x="${15 + i * 14}" y="36" width="8" height="26"/>`).join("") + '</g><rect x="8" y="62" width="64" height="7" rx="1" fill="#47598a"/>',
 gov: '<path d="M40 8c-9 0-16 7-16 14h32c0-7-7-14-16-14z" fill="#5b7fc7"/><rect x="14" y="22" width="52" height="6" fill="#3d5a99"/><g fill="#c5d4f2">' + [0, 1, 2, 3, 4].map(i => `<rect x="${17 + i * 10}" y="30" width="6" height="30"/>`).join("") + '</g><rect x="10" y="60" width="60" height="8" rx="1" fill="#3d5a99"/>',
 fund: '<rect x="10" y="18" width="60" height="50" rx="8" fill="#e9f7f1" stroke="#2fbf87" stroke-width="2"/><circle cx="32" cy="43" r="14" fill="#c7efdf"/><path d="M32 43V29a14 14 0 0 1 13.3 18.3z" fill="#2fbf87"/><path d="M32 43l13.3 4.3A14 14 0 0 1 22 53z" fill="#1d9bd1"/><path d="M52 36h12M52 43h9M52 50h12" stroke="#2fbf87" stroke-width="3" stroke-linecap="round"/><text x="40" y="14" text-anchor="middle" font-size="9" font-weight="800" fill="#1f9e6b">펀드</text>',
 factory: '<path d="M8 70V40l14 8v-8l14 8v-8l14 8V20h10v50z" fill="#6d84b7"/><rect x="50" y="12" width="10" height="10" fill="#8a9cc7"/><g fill="#ffd36b"><rect x="14" y="54" width="7" height="7"/><rect x="28" y="54" width="7" height="7"/><rect x="42" y="54" width="7" height="7"/></g><circle cx="58" cy="8" r="4" fill="#d6dbe8"/><circle cx="64" cy="5" r="3" fill="#e3e7f0"/>',
 doc: '<path d="M18 8h30l14 14v50H18z" fill="#fff" stroke="#a8b6d6" stroke-width="2"/><path d="M48 8v14h14" fill="#e6ebf6" stroke="#a8b6d6" stroke-width="2"/><path d="M26 34h28M26 42h28M26 50h20" stroke="#b9c6e2" stroke-width="3" stroke-linecap="round"/><circle cx="54" cy="60" r="9" fill="#2fbf87"/><path d="m50 60 3 3 5-6" stroke="#fff" stroke-width="2.5" fill="none" stroke-linecap="round"/>',
 cal: '<rect x="10" y="14" width="60" height="56" rx="6" fill="#fff" stroke="#a8b6d6" stroke-width="2"/><rect x="10" y="14" width="60" height="14" rx="6" fill="#e5484d"/><path d="M24 8v12M56 8v12" stroke="#47598a" stroke-width="4" stroke-linecap="round"/><g fill="#c9d3ea">' + [0, 1, 2].map(r => [0, 1, 2, 3].map(c => `<rect x="${17 + c * 13}" y="${34 + r * 11}" width="8" height="7" rx="1"/>`).join("")).join("") + '</g><rect x="43" y="45" width="8" height="7" rx="1" fill="#2f6fe4"/>',
 chartup: '<rect x="8" y="10" width="64" height="60" rx="6" fill="#fff" stroke="#a8b6d6" stroke-width="2"/><g fill="#9cc2f5"><rect x="18" y="46" width="9" height="16"/><rect x="32" y="38" width="9" height="24"/><rect x="46" y="30" width="9" height="32"/></g><path d="M16 44l14-10 12 6 20-18" stroke="#2fbf87" stroke-width="4" fill="none" stroke-linecap="round" stroke-linejoin="round"/><path d="M54 21h9v9" stroke="#2fbf87" stroke-width="4" fill="none" stroke-linecap="round"/>',
 ticket: '<path d="M8 24h64v10a6 6 0 0 0 0 12v10H8V46a6 6 0 0 0 0-12z" fill="#ffe08a" stroke="#d9a520" stroke-width="2"/><path d="M50 26v28" stroke="#d9a520" stroke-width="2" stroke-dasharray="3 3"/><text x="29" y="44" text-anchor="middle" font-size="10" font-weight="900" fill="#8a5c00">신주권리</text>',
 building: '<rect x="20" y="8" width="40" height="64" rx="3" fill="#6b8fd6"/><g fill="#e4ecff">' + [0, 1, 2, 3, 4].map(r => [0, 1, 2].map(c => `<rect x="${26 + c * 10}" y="${14 + r * 10}" width="6" height="6" rx="1"/>`).join("")).join("") + '</g><rect x="35" y="62" width="10" height="10" fill="#3d5a99"/><rect x="8" y="72" width="64" height="3" fill="#94a9d6"/>',
};
const art = (n, sz = 72) => `<svg class="vx-art" viewBox="0 0 80 80" width="${sz}" height="${sz}" aria-hidden="true">${ART[n] || ART.doc}</svg>`;
function dcEx(o) { const arrow = (dir, col) => `<svg viewBox="0 0 120 14" preserveAspectRatio="none" class="vx-arw"><path d="${dir > 0 ? "M2 7h108" : "M118 7H10"}" stroke="${col}" stroke-width="5" stroke-linecap="round"/><path d="${dir > 0 ? "M104 1l12 6-12 6z" : "M16 1 4 7l12 6z"}" fill="${col}"/></svg>`;
  return `<div class="vx-ex">${o.title ? `<div class="vx-ext">${esc(o.title)}</div>` : ""}<div class="vx-exg"><div class="vx-act">${art(o.l.a, 76)}<span>${esc(o.l.t)}</span></div><div class="vx-mid"><div class="vx-al" style="color:#2f6fe4">${esc(o.top.t)}</div>${arrow(1, "#2f6fe4")}${o.top.a ? art(o.top.a, 48) : ""}${o.bot ? `${o.bot.a ? art(o.bot.a, 48) : ""}${arrow(-1, "#1fa463")}<div class="vx-al" style="color:#1fa463">${esc(o.bot.t)}</div>` : ""}</div><div class="vx-act">${art(o.r.a, 76)}<span>${esc(o.r.t)}</span></div></div>${o.note ? `<div class="vx-exn">${esc(o.note)}</div>` : ""}</div>`; }
function dcChain(o) { return `<div class="vx-ch">${o.title ? `<div class="vx-ext">${esc(o.title)}</div>` : ""}${o.nodes.map((n, i) => `${i ? `<div class="vx-cha"><svg viewBox="0 0 20 30" width="16" height="26"><path d="M10 2v20" stroke="var(--sub2)" stroke-width="3" stroke-linecap="round"/><path d="M3 18l7 9 7-9z" fill="var(--sub2)"/></svg>${o.nodes[i - 1].go ? `<span>${esc(o.nodes[i - 1].go)}</span>` : ""}</div>` : ""}<div class="vx-chn">${art(n.a, 56)}<div><b>${esc(n.t)}</b>${n.x ? `<div>${esc(n.x)}</div>` : ""}</div></div>`).join("")}</div>`; }
const ARTCSS = `.vx-ex{background:linear-gradient(180deg,#eef4ff,#f8fbff);border:1px solid #d6e2f7;border-radius:18px;padding:14px 10px 12px;margin:12px 0;color:#14213d}
:root:not([data-theme=light]) .vx-ex,:root:not([data-theme=light]) .vx-ch{background:linear-gradient(180deg,#1a2550,#141c3d);border-color:var(--line);color:var(--txt)}
.vx-ext{text-align:center;font-size:17px;font-weight:900;letter-spacing:-.02em;margin-bottom:10px}.vx-exg{display:grid;grid-template-columns:84px 1fr 84px;align-items:center;gap:4px}.vx-act{display:flex;flex-direction:column;align-items:center;gap:6px}.vx-act span{background:#14213d;color:#fff;font-size:13px;font-weight:800;padding:5px 12px;border-radius:9px;text-align:center;line-height:1.3}
:root:not([data-theme=light]) .vx-act span{background:#2f6fe4}
.vx-mid{display:flex;flex-direction:column;align-items:center;gap:2px;min-width:0}.vx-arw{width:100%;height:14px}.vx-al{font-size:12.5px;font-weight:800;text-align:center;line-height:1.3}.vx-exn{margin-top:12px;background:rgba(255,255,255,.7);border:1px solid #d6e2f7;border-radius:12px;padding:10px 12px;text-align:center;font-size:14px;line-height:1.55;font-weight:600}
:root:not([data-theme=light]) .vx-exn{background:rgba(255,255,255,.06);border-color:var(--line)}
.vx-ch{background:linear-gradient(180deg,#eef4ff,#f8fbff);border:1px solid #d6e2f7;border-radius:18px;padding:14px;margin:12px 0;color:#14213d}.vx-chn{display:flex;align-items:center;gap:12px;background:rgba(255,255,255,.75);border:1px solid #d6e2f7;border-radius:14px;padding:8px 12px}
:root:not([data-theme=light]) .vx-chn{background:rgba(255,255,255,.05);border-color:var(--line)}
.vx-chn b{font-size:15px;color:inherit!important}.vx-chn div div{font-size:13px;opacity:.8;line-height:1.5}.vx-cha{display:flex;align-items:center;gap:8px;padding:2px 0 2px 32px;font-size:12.5px;font-weight:800;color:#2f6fe4}.vx-art{flex:0 0 auto}`;

/* ── 항목 화면 ── */
function dcTermView(c) {
  const e = DC.id[c.id]; if (!e) return `<div class="lhead"><button class="x" data-act="back">${ic("left")}</button></div><p class="mut">항목을 찾지 못했어요.</p>`;
  const lessons = (DC.cfg.lessons ? DC.cfg.lessons() : []).filter(l => [e.k, ...(e.al || [])].some(k => l.text.includes(k))).slice(0, 8);
  const deeps = (window.DP && DP.idx ? DP.idx.topics : []).filter(m => [e.k, ...(e.al || [])].some(k => (m.t + m.sum + (m.kw || []).join(" ")).includes(k)));
  const rel = dcRel(e), hero = !!(e.sec[0] && e.sec[0].b[0] && (e.sec[0].b[0].hero || e.sec[0].b[0].ex || e.sec[0].b[0].chain));
  return `<div class="lhead"><button class="x" data-act="back">${ic("left")}</button><span class="mut sm" style="font-weight:700;flex:1">백과 · ${esc(e.area)}</span><button class="x" data-act="dcfind">${ic("search")}</button></div>
  <div class="slide dterm"><div class="dtop"><span class="k">${esc(e.area)}</span><h2>${esc(e.k)}${e.en ? `<small>${esc(e.en)}</small>` : ""}</h2>
    ${(e.al || []).length ? `<div class="dalias">${e.al.map(a => `<span>${esc(a)}</span>`).join("")}</div>` : ""}
    ${hero ? "" : `<div class="done">${esc(e.one)}</div>`}</div>
    ${e.tool && ACT[e.tool] ? `<button class="btn ghost" style="margin-top:12px" data-act="${esc(e.tool)}">${ic("target")} 계산기로 직접 해 보기</button>` : ""}
    ${(() => { const sec = (s, i) => `<section id="ds-${i}" class="dsec"><h3><i>${String.fromCharCode(65 + i)}</i>${esc(s.h)}</h3>${s.b.map(dcBlock).join("")}</section>`, toc = `<div class="toc2">${e.sec.map((s, i) => `<button data-act="dcsec" data-arg="${i}"><i>${String.fromCharCode(65 + i)}</i>${esc(s.h)}</button>`).join("")}</div>`;
      return hero ? sec(e.sec[0], 0) + toc + e.sec.slice(1).map((s, i) => sec(s, i + 1)).join("") : toc + e.sec.map(sec).join(""); })()}
    ${rel.length ? `<section class="dsec drel"><h3>함께 보면 좋은 항목</h3><div class="dchips">${rel.map(r => `<button data-act="dcopen" data-arg="${esc(r.id)}">${esc(r.k)}</button>`).join("")}</div></section>` : ""}
    ${lessons.length || deeps.length ? `<section class="dsec drel"><h3>이 말이 나오는 공부</h3>${lessons.map(l => `<button class="bki" data-act="dclesson" data-arg="${esc(l.id)}"><b>${esc(l.t)}</b><small class="mut">기초 레슨</small></button>`).join("")}${deeps.map(m => `<button class="bki" data-act="dopen" data-arg="${esc(m.id)}"><b>${esc(m.t)}</b><small class="mut">심화 글</small></button>`).join("")}</section>` : ""}
    ${(e.src || []).length ? `<section class="dsec drel"><h3>확인한 원문</h3><ul>${e.src.map(s => `<li><a class="dl" href="${esc(s.u)}" target="_blank" rel="noopener">${esc(s.t)}</a> <span class="mut xs">${esc(s.o || "")}</span></li>`).join("")}</ul></section>` : ""}
    <p class="mut xs" style="margin-top:14px">${esc(e.upd || "")} 기준 · 제도는 바뀔 수 있어요. 실제 거래 전에는 해당 공시와 증권사 안내를 확인하세요.</p>
  </div>`;
}

/* ── 본문 속 용어 자동 링크 ── */
function dcLink(root, selfId) {
  if (!DC.rx || !root) return;
  const seen = new Set([selfId]), nodes = [], w = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {acceptNode: n => n.parentElement.closest("a,button,h2,h3,mark,.tm,.k,.dalias,.toc2,.drel,.done,textarea,svg") ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT});
  while (w.nextNode()) nodes.push(w.currentNode);
  let n = 0;
  for (const t of nodes) { if (n > 40) break;
    const s = t.nodeValue; DC.rx.lastIndex = 0; let m, last = 0, out = null;
    while ((m = DC.rx.exec(s))) { const id = DC.linkMap[m[0].toLowerCase()]; if (!id || seen.has(id)) continue; seen.add(id); n++;
      out = out || document.createDocumentFragment(); out.append(s.slice(last, m.index)); const sp = document.createElement("span"); sp.className = "tm"; sp.dataset.t = id; sp.textContent = m[0]; out.append(sp); last = m.index + m[0].length; }
    if (out) { out.append(s.slice(last)); t.replaceWith(out); } }
}
function dcMark(root, q) {
  const ql = q.trim().toLowerCase(); if (!ql || !root) return null;
  const w = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  while (w.nextNode()) { const t = w.currentNode, i = t.nodeValue.toLowerCase().indexOf(ql); if (i < 0 || t.parentElement.closest("h2,.toc2,.dalias")) continue;
    const r = document.createRange(); r.setStart(t, i); r.setEnd(t, i + ql.length); const mk = document.createElement("mark"); r.surroundContents(mk); return mk; }
  return null;
}
function dcAfter() {
  const c = cur(); if (!c || !DC.list) return;
  if (c.v === "dterm") { const root = $(".dterm"); dcLink(root, c.id);
    if (c.hl && !c.done) { c.done = 1; const mk = dcMark(root, c.hl); if (mk) setTimeout(() => mk.scrollIntoView({block: "center"}), 30); } }
  else if (["lesson", "dtopic", ...(DC.cfg.linkViews || [])].includes(c.v)) dcLink($(".slide"), null);
}
function dcOpen(id, hl) { if (!DC.id[id]) return; S.dcRecent = [id, ...(S.dcRecent || []).filter(x => x !== id)].slice(0, 10); save(); push({v: "dterm", id, hl: hl || ""}); }

function DictInit(cfg) {
  DC.cfg = cfg || {};
  document.head.insertAdjacentHTML("beforeend", `<style>${VXCSS}${ARTCSS}
.tm{color:inherit;text-decoration:underline;text-decoration-color:var(--acc);text-decoration-thickness:2px;text-underline-offset:3px;cursor:pointer}
mark{background:var(--gold-soft);color:inherit;border-radius:4px;padding:0 2px;box-shadow:0 0 0 2px var(--gold-soft)}
.dcs{position:sticky;top:calc(env(safe-area-inset-top) + 4px);z-index:4;display:flex;gap:8px;background:var(--bg);padding:4px 0 8px}
.dcs input{flex:1;height:50px;border:1px solid var(--line);border-radius:14px;background:var(--card);color:var(--txt);font:inherit;font-size:16px;padding:0 14px}
.dcs input:focus{outline:2px solid var(--acc);border-color:transparent}
.dcfake{display:flex;align-items:center;gap:10px;width:100%;height:50px;border:1px solid var(--line);border-radius:14px;background:var(--card);color:var(--sub2);padding:0 14px;margin:6px 0 8px;font-size:15px;text-align:left}
.dcx{display:block;background:var(--acc-soft);border:1.5px solid var(--acc);border-radius:16px;padding:14px 16px;margin:8px 0 4px;cursor:pointer;position:relative}
.dcx b{display:block;font-size:20px;margin:2px 0}.dcx small{display:block;color:var(--sub);font-size:13.5px;line-height:1.55;padding-right:60px}.dcx .go{position:absolute;right:14px;bottom:14px;color:var(--acc);font-weight:800;font-size:13px}
.dchips{display:flex;flex-wrap:wrap;gap:8px;margin:6px 0}.dchips button{background:var(--chip);border-radius:99px;padding:7px 13px;font-size:14px;font-weight:700}
.dcar{background:var(--card);border:1px solid var(--line);border-radius:14px;margin:8px 0;padding:0 12px}.dcar summary{display:flex;justify-content:space-between;align-items:center;padding:13px 2px;list-style:none;cursor:pointer}.dcar summary::-webkit-details-marker{display:none}.dcar[open]{padding-bottom:6px}
.dterm h2 small{display:block;font-size:13px;color:var(--sub);font-weight:600;margin-top:2px;letter-spacing:0}
.dalias{display:flex;flex-wrap:wrap;gap:6px;margin:-4px 0 12px}.dalias span{font-size:12px;background:var(--chip);color:var(--sub);border-radius:7px;padding:3px 8px}
.done{background:var(--bg2);border-left:4px solid var(--acc);border-radius:10px;padding:11px 13px;font-size:15px;line-height:1.65;font-weight:600}
.toc2{display:flex;flex-wrap:wrap;gap:6px;margin:12px 0 4px}
.toc2 button{display:flex;gap:6px;align-items:center;text-align:left;padding:5px 10px 5px 5px;font-size:13px;color:var(--sub);background:var(--chip);border-radius:99px}
.toc2 i,.dsec h3 i{font-style:normal;width:22px;height:22px;border-radius:7px;background:var(--acc-soft);color:var(--acc);display:inline-grid;place-items:center;font-size:12px;font-weight:900;flex:0 0 auto}
.dsec{scroll-margin-top:calc(env(safe-area-inset-top) + 12px)}.dsec h3{display:flex;gap:9px;align-items:center;font-size:18.5px;margin:26px 0 10px;letter-spacing:-.02em}
.dterm .dsec p{font-size:16.5px;line-height:1.85;margin:0 0 12px}.dterm .dsec li{font-size:16px}
</style>`);
  IP.search = '<circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/>';
  const old = TABS.findIndex(t => t[0] === DC.cfg.replaceTab); if (old >= 0) TABS.splice(old, 1, ["dict", "백과", "book"]); else TABS.splice(TABS.findIndex(t => t[0] === "road") + 1, 0, ["dict", "백과", "book"]);
  VIEW.dict = () => { setTimeout(dcBind);
    return `<h1 class="pg">백과사전</h1><div class="pgsub">${DC.list ? `${DC.list.length}개 항목 · ` : ""}용어를 치면 그 항목으로 바로 들어가요. 매일 늘어나요.</div>
    <form class="dcs" id="dcform" autocomplete="off"><input id="dcq" type="search" enterkeyhint="search" placeholder="예: 신주인수권, 배당락일, PER" value="${esc(DC.q)}"></form>${DC.err ? `<p class="mut sm">${DC.err}</p>` : ""}<div id="dcres">${dcResults()}</div>`; };
  VIEW.dterm = dcTermView;
  const road = VIEW.road; VIEW.road = () => road().replace('<div class="hero">', `<button class="dcfake" data-act="dcfind">${ic("search")}<span>모르는 말 찾기 — 신주인수권, 배당락일…</span></button><div class="hero">`);
  Object.assign(ACT, {
    dcopen: id => dcOpen(id, DC.list && DC.q && !DC.by[dcNorm(DC.q)] ? DC.q : ""),
    dcsec: i => { const s = document.getElementById("ds-" + i); if (s) s.scrollIntoView({behavior: "smooth", block: "start"}); },
    dcfind: () => { V.tab = "dict"; V.stack = []; render(); scrollTo(0, 0); const i = $("#dcq"); if (i) { i.focus(); i.select(); } },
    dclesson: id => DC.cfg.openLesson && DC.cfg.openLesson(id)
  });
  const _render = render;
  render = function () { _render(); dcAfter(); };
  document.addEventListener("click", ev => { const t = ev.target.closest && ev.target.closest(".tm"); if (!t) return; ev.preventDefault(); ev.stopPropagation(); dcOpen(t.dataset.t); }, true);
  dcLoad();
}
function dcBind() {
  const i = $("#dcq"), f = $("#dcform"), box = $("#dcres"); if (!i) return;
  const upd = () => { DC.q = i.value; box.innerHTML = dcResults(); bind2(box); };
  i.oninput = upd;
  f.onsubmit = ev => { ev.preventDefault(); DC.q = i.value; const r = DC.list && dcSearch(DC.q); if (!r) return; i.blur();
    if (r.exact) return dcOpen(r.exact.id);
    if (r.terms.length) return dcOpen(r.terms[0].e.id, r.terms[0].sc < 300 ? DC.q : "");
    upd(); };
  bind2(box);
}

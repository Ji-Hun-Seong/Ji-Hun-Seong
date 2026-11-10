/* 백과사전 — 마스터로드·펀드로드 공용. 앱마다 <앱>/dict/terms.json 을 읽는다.
   · 용어·별칭이 정확히 맞으면 바로 그 항목으로 들어간다 (예: '배당락일' → 배당락일 항목)
   · 본문에만 나오는 말이면 그 절로 스크롤하고 형광펜 표시
   · 레슨·심화 글·백과 본문 속 용어는 자동으로 밑줄 링크 → 누르면 그 항목으로
   deep.js 의 dpBlock 을 그대로 써서 글 형식(p·ul·tip·calc·table·f·j)이 같다. 형식: deep-study/DICT.md */
"use strict";
const DC = {list: null, err: "", q: "", by: {}, id: {}, rx: null, cfg: {}};
const dcNorm = s => String(s || "").toLowerCase().replace(/[\s·・()\[\]{}'"’‘“”,.\-_/]/g, "");
const dcPlain = s => String(s || "").replace(/<[^>]+>/g, "");
function dcBlockText(b) { if (b.hero) return [b.hero.title, b.hero.sub, ...(b.hero.stats || []).flat()].join(" "); if (b.kv) return b.kv.flat().join(" "); if (b.tl) return b.tl.map(x => [x.d, x.t, x.x, x.me].join(" ")).join(" "); if (b.pts) return b.pts.map(x => x.t + " " + x.x).join(" "); if (b.donut) return b.donut.items.map(x => x[0] + " " + (x[2] || "")).join(" "); if (b.pc) return [...b.pc.bad, ...b.pc.good].join(" "); if (b.branch) return b.branch.map(x => [x.t, x.x, x.r].join(" ")).join(" "); if (b.callout != null) return b.callout; if (b.ex) return [b.ex.title, b.ex.l.t, b.ex.r.t, b.ex.top.t, b.ex.bot && b.ex.bot.t, b.ex.note].join(" "); if (b.flow) return [b.flow.title, ...(b.flow.sub || []), ...b.flow.items.map(x => x.t), ...(b.flow.or || []).map(x => x.t + " " + (x.s || "")), b.flow.badge].join(" "); if (b.chain) return [b.chain.title, ...b.chain.nodes.map(n => [n.t, n.x, n.go].join(" "))].join(" "); if (b.p != null) return b.p; if (b.tip != null) return b.tip; if (b.ul) return b.ul.join(" "); if (b.calc) return b.calc.join(" ");
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
  if (b.flow) return dcFlow(b.flow);
  if (b.callout != null) return `<div class="vx-call">${vi("bulb", 22)}<span>${esc(b.callout)}</span></div>`;
  return dpBlock(b);
}
const VXCSS = `.vx-hero{border-radius:24px;padding:20px 18px;margin:6px 0 14px;background:linear-gradient(160deg,#3182f6,#4f9bff);color:#fff;box-shadow:0 6px 18px rgba(49,130,246,.25)}
.vx-kick{display:inline-block;font-size:12px;font-weight:800;background:rgba(255,255,255,.18);padding:4px 9px;border-radius:7px;margin-bottom:8px}.vx-ht{font-size:23px;font-weight:900;line-height:1.3;letter-spacing:-.03em}.vx-hs{font-size:14.5px;line-height:1.55;opacity:.92;margin-top:6px}
.vx-stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(96px,1fr));gap:8px;margin-top:14px}.vx-stats div{background:rgba(255,255,255,.18);border-radius:14px;padding:10px 12px}.vx-stats b{display:block;font-size:17px;font-weight:900;font-variant-numeric:tabular-nums;color:#fff!important}.vx-stats small{font-size:11.5px;opacity:.85}
.vx-kv{border:1px solid var(--line);border-radius:14px;overflow:hidden;margin:10px 0}.vx-kv div{display:flex;justify-content:space-between;gap:12px;padding:10px 12px;font-size:14px;border-bottom:1px solid var(--line)}.vx-kv div:last-child{border-bottom:0}.vx-kv div:nth-child(odd){background:var(--bg2)}.vx-kv span{color:var(--sub);flex:0 0 auto}.vx-kv b{text-align:right;color:var(--txt)!important;font-variant-numeric:tabular-nums}
.vx-tl{margin:12px 0;position:relative}.vx-st{display:flex;gap:12px;position:relative;padding-bottom:14px}.vx-st:not(:last-child)::before{content:"";position:absolute;left:19px;top:40px;bottom:0;width:2px;background:var(--line)}.vx-ic{width:40px;height:40px;border-radius:50%;display:grid;place-items:center;color:#fff;flex:0 0 auto;box-shadow:0 3px 8px rgba(0,0,0,.18)}
.vx-sb{flex:1;background:var(--bg2);border:1px solid var(--line);border-radius:12px;padding:9px 11px}.vx-sh{display:flex;align-items:center;gap:8px;flex-wrap:wrap}.vx-sh b{font-size:15px;color:var(--txt)!important}.vx-date{font-size:12px;font-weight:800;color:#fff;background:#1e3a8a;border-radius:6px;padding:2px 7px;font-variant-numeric:tabular-nums}.vx-sx{font-size:13.5px;color:var(--sub);line-height:1.55;margin-top:4px}.vx-me{display:flex;gap:6px;align-items:flex-start;font-size:13px;line-height:1.5;margin-top:6px;padding-top:6px;border-top:1px dashed var(--line);color:var(--acc)}.vx-me span{color:var(--txt)}.vx-me svg{margin-top:2px;flex:0 0 auto}
.vx-pts{display:grid;gap:8px;margin:10px 0}.vx-pt{display:flex;gap:12px;align-items:flex-start;background:var(--bg2);border:1px solid var(--line);border-radius:14px;padding:12px}.vx-pi{width:44px;height:44px;border-radius:50%;display:grid;place-items:center;background:var(--card);border:1px solid var(--line);flex:0 0 auto}.vx-pt b{display:block;font-size:15.5px;color:var(--txt)!important;margin-bottom:2px}.vx-pt div div{font-size:13.5px;color:var(--sub);line-height:1.55}
.vx-donut{display:flex;align-items:center;gap:14px;margin:12px 0;flex-wrap:wrap}.vx-donut svg{width:140px;height:140px;flex:0 0 auto}.vx-dt1{font-size:11px;fill:var(--sub)}.vx-dt2{font-size:15px;font-weight:900;fill:var(--txt)}.vx-leg{flex:1;min-width:150px;display:grid;gap:8px}.vx-leg div{display:grid;grid-template-columns:12px 1fr auto;gap:2px 8px;align-items:center;font-size:13.5px}.vx-leg i{width:12px;height:12px;border-radius:3px}.vx-leg b{color:var(--txt)!important}.vx-leg small{grid-column:2/4;color:var(--sub);font-size:12px}
.vx-pc{display:grid;gap:8px;margin:10px 0}.vx-pc>div{border-radius:14px;padding:12px 14px}.vx-bad{background:var(--bad-soft);border:1px solid rgba(229,72,77,.35)}.vx-good{background:var(--acc-soft);border:1px solid rgba(31,164,99,.35)}.vx-pch{display:flex;align-items:center;gap:8px;margin-bottom:6px}.vx-bad .vx-pch{color:var(--bad)}.vx-good .vx-pch{color:var(--acc)}.vx-pch b{font-size:15px;color:inherit!important}.vx-pc ul{margin:0;padding-left:18px}.vx-pc li{font-size:14px!important;line-height:1.6!important;margin:3px 0!important}
.vx-br{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin:10px 0}.vx-bc{border:1px solid var(--line);border-top:4px solid var(--tc);border-radius:12px;padding:10px;background:var(--bg2)}.vx-bt{display:flex;gap:6px;align-items:center;color:var(--tc)}.vx-bt b{font-size:14.5px;color:var(--txt)!important}.vx-bx{font-size:13px;color:var(--sub);line-height:1.5;margin-top:5px}.vx-brs{font-size:12.5px;font-weight:800;margin-top:7px;color:var(--tc)}
.vx-call{display:flex;gap:10px;align-items:center;background:#1e3a8a;color:#fff;border-radius:14px;padding:13px 14px;margin:12px 0;font-size:14.5px;line-height:1.55;font-weight:700}.vx-call svg{color:#ffd54a;flex:0 0 auto}
.dterm .dtop{border-radius:18px;margin:-6px -4px 14px;padding:16px;background:linear-gradient(135deg,var(--acc-soft),transparent 70%);border:1px solid var(--line)}`;


/* ── 일러스트(토스풍 3D 아이콘) ── */
const G = (id, a, b, x2 = 0, y2 = 1) => `<linearGradient id="${id}" x1="0" y1="0" x2="${x2}" y2="${y2}"><stop offset="0" stop-color="${a}"/><stop offset="1" stop-color="${b}"/></linearGradient>`;
const SH = '<ellipse cx="40" cy="74" rx="24" ry="3.5" fill="#000" opacity=".10"/>';
const ART = {
 coin: `<defs>${G("gc1", "#ffe27a", "#f5a623")}${G("gc2", "#f7b93a", "#d98a0b")}</defs>${SH}<ellipse cx="40" cy="44" rx="25" ry="25" fill="url(#gc2)"/><circle cx="40" cy="40" r="25" fill="url(#gc1)"/><circle cx="40" cy="40" r="19" fill="none" stroke="#e39a17" stroke-width="2.5" opacity=".7"/><text x="40" y="48" text-anchor="middle" font-size="22" font-weight="900" fill="#c27a00">₩</text><ellipse cx="31" cy="27" rx="9" ry="5" fill="#fff" opacity=".45" transform="rotate(-30 31 27)"/>`,
 coindown: `<defs>${G("gc1", "#ffe27a", "#f5a623")}${G("gc2", "#f7b93a", "#d98a0b")}${G("gr1", "#ff7a6b", "#e8382c")}</defs>${SH}<ellipse cx="36" cy="42" rx="24" ry="24" fill="url(#gc2)"/><circle cx="36" cy="38" r="24" fill="url(#gc1)"/><circle cx="36" cy="38" r="18" fill="none" stroke="#e39a17" stroke-width="2.5" opacity=".7"/><text x="36" y="46" text-anchor="middle" font-size="21" font-weight="900" fill="#c27a00">₩</text><ellipse cx="27" cy="26" rx="8" ry="4.5" fill="#fff" opacity=".45" transform="rotate(-30 27 26)"/><path d="M55 40h10v14h7L60 70 48 54h7z" fill="url(#gr1)"/>`,
 money: `<defs>${G("gm1", "#5fe08f", "#22a95a")}${G("gm2", "#3fc777", "#1b8f4b")}</defs>${SH}<rect x="10" y="44" width="58" height="24" rx="6" fill="url(#gm2)"/><rect x="12" y="34" width="58" height="24" rx="6" fill="url(#gm2)" opacity=".9"/><rect x="14" y="24" width="56" height="24" rx="6" fill="url(#gm1)"/><circle cx="42" cy="36" r="7" fill="#e9fff1" opacity=".9"/><text x="42" y="40" text-anchor="middle" font-size="9.5" font-weight="900" fill="#1b8f4b">₩</text><rect x="36" y="21" width="12" height="30" rx="2" fill="#fff" opacity=".85"/><rect x="18" y="27" width="20" height="4" rx="2" fill="#fff" opacity=".35"/>`,
 stock: `<defs>${G("gp1", "#fffdf6", "#f3e6c4")}${G("gb1", "#5b9dff", "#2b6fe0")}${G("gs1", "#ffd45c", "#f0a20c")}</defs>${SH}<rect x="12" y="12" width="52" height="58" rx="7" fill="url(#gp1)" stroke="#e6d3a1" stroke-width="1.5"/><rect x="12" y="12" width="52" height="15" rx="7" fill="url(#gb1)"/><rect x="12" y="20" width="52" height="7" fill="url(#gb1)"/><text x="38" y="23.5" text-anchor="middle" font-size="8.5" font-weight="900" fill="#fff">주식</text><path d="M20 37h30M20 44h24M20 51h18" stroke="#d9c38c" stroke-width="3" stroke-linecap="round"/><circle cx="55" cy="58" r="9" fill="url(#gs1)"/><path d="M50 64l-3 10 8-4 8 4-3-10" fill="#ff6b5a"/><circle cx="55" cy="58" r="4" fill="#fff" opacity=".5"/>`,
 newstock: `<defs>${G("gp1", "#fffdf6", "#f3e6c4")}${G("gu1", "#4ee38a", "#14b25a")}</defs>${SH}<rect x="22" y="8" width="44" height="52" rx="6" fill="#f1e2bb" transform="rotate(8 44 34)"/><rect x="16" y="12" width="44" height="54" rx="6" fill="url(#gp1)" stroke="#e6d3a1" stroke-width="1.5"/><path d="M23 34h28M23 41h22M23 48h26" stroke="#d9c38c" stroke-width="3" stroke-linecap="round"/><g fill="url(#gu1)"><path d="M27 26l5-7 5 7h-3v4h-4v-4z"/><path d="M41 26l5-7 5 7h-3v4h-4v-4z"/></g><rect x="40" y="52" width="32" height="16" rx="4" fill="#2fbf6b"/><rect x="43" y="49" width="32" height="16" rx="4" fill="#47d47f"/><rect x="55" y="49" width="7" height="16" fill="#fff" opacity=".8"/>`,
 warrant: `<defs>${G("gw1", "#ffffff", "#e9eef7")}${G("gb1", "#5b9dff", "#2b6fe0")}${G("gs1", "#ffd45c", "#f0a20c")}</defs>${SH}<rect x="14" y="10" width="50" height="60" rx="7" fill="url(#gw1)" stroke="#cdd8ea" stroke-width="1.5"/><text x="39" y="22" text-anchor="middle" font-size="7" font-weight="900" fill="#33507f">신주인수권 증서</text><path d="M21 28h36M21 34h30" stroke="#d3dceb" stroke-width="2.5" stroke-linecap="round"/><rect x="19" y="40" width="40" height="9" rx="3" fill="url(#gb1)"/><text x="39" y="47" text-anchor="middle" font-size="6.5" font-weight="900" fill="#fff">WARRANT</text><circle cx="52" cy="60" r="7.5" fill="url(#gs1)"/><path d="M48 65l-2 8 6-3 6 3-2-8" fill="#4d7fe0"/>`,
 ticket: `<defs>${G("gt1", "#ffe38a", "#ffbd2e")}</defs>${SH}<path d="M8 22h64v12a6 6 0 0 0 0 12v12H8V46a6 6 0 0 0 0-12z" fill="url(#gt1)"/><path d="M52 24v32" stroke="#e09a12" stroke-width="2" stroke-dasharray="3 3"/><text x="30" y="44" text-anchor="middle" font-size="9.5" font-weight="900" fill="#8a5600">신주권리</text><path d="M12 25h30" stroke="#fff" stroke-width="3" stroke-linecap="round" opacity=".5"/>`,
 company: `<defs>${G("gk1", "#6aa6ff", "#2f6fe4")}${G("gk2", "#3d7bea", "#1f4fb8")}</defs>${SH}<rect x="16" y="8" width="32" height="64" rx="6" fill="url(#gk1)"/><rect x="44" y="28" width="22" height="44" rx="5" fill="url(#gk2)"/><g fill="#dceaff">` + [0, 1, 2, 3, 4].map(r => [0, 1].map(c => `<rect x="${22 + c * 12}" y="${15 + r * 10}" width="8" height="6" rx="2"/>`).join("")).join("") + `<rect x="50" y="35" width="10" height="5" rx="2"/><rect x="50" y="45" width="10" height="5" rx="2"/><rect x="50" y="55" width="10" height="5" rx="2"/></g><rect x="27" y="62" width="10" height="10" rx="2" fill="#173f99"/><rect x="18" y="10" width="6" height="58" rx="3" fill="#fff" opacity=".18"/>`,
 building: `<defs>${G("gk1", "#7fb3ff", "#3d7bea")}</defs>${SH}<rect x="20" y="8" width="40" height="64" rx="7" fill="url(#gk1)"/><g fill="#e6f0ff">` + [0, 1, 2, 3, 4].map(r => [0, 1, 2].map(c => `<rect x="${26 + c * 10}" y="${15 + r * 10}" width="6" height="6" rx="2"/>`).join("")).join("") + `</g><rect x="35" y="62" width="10" height="10" rx="2" fill="#2554b8"/>`,
 investors: `<defs>${G("gf", "#ffdcb8", "#f3bf8e")}${G("gq1", "#6aa6ff", "#2f6fe4")}${G("gq2", "#ff9fb6", "#ec6f91")}${G("gq3", "#5a6ea8", "#33447a")}</defs>${SH}<path d="M6 68c0-12 7-20 17-20s17 8 17 20z" fill="url(#gq1)"/><circle cx="23" cy="32" r="10" fill="url(#gf)"/><path d="M13 30c1-7 6-10 10-10s10 3 10 10c-3-3-6-4-10-4s-7 1-10 4z" fill="#4a3426"/><path d="M40 68c0-12 7-20 17-20s17 8 17 20z" fill="url(#gq3)"/><circle cx="57" cy="32" r="10" fill="url(#gf)"/><path d="M47 30c1-7 6-10 10-10s10 3 10 10c-4-4-16-4-20 0z" fill="#2b211b"/><path d="M22 72c0-13 8-21 18-21s18 8 18 21z" fill="url(#gq2)"/><circle cx="40" cy="38" r="11" fill="url(#gf)"/><path d="M29 39c0-9 5-14 11-14s11 5 11 14c-2-5-6-8-11-8s-9 3-11 8z" fill="#5b3a28"/>`,
 person: `<defs>${G("gf", "#ffdcb8", "#f3bf8e")}${G("gq1", "#6aa6ff", "#2f6fe4")}</defs>${SH}<path d="M16 72c0-15 11-24 24-24s24 9 24 24z" fill="url(#gq1)"/><circle cx="40" cy="30" r="13" fill="url(#gf)"/><path d="M27 28c1-9 7-13 13-13s12 4 13 13c-4-4-9-6-13-6s-9 2-13 6z" fill="#3b2a20"/>`,
 bond: `<defs>${G("gw1", "#ffffff", "#e7eefb")}${G("gb2", "#5b9dff", "#2b6fe0")}</defs>${SH}<rect x="14" y="10" width="48" height="60" rx="7" fill="url(#gw1)" stroke="#c9d6ee" stroke-width="1.5"/><text x="38" y="25" text-anchor="middle" font-size="9" font-weight="900" fill="#2b5fc4">채권</text><path d="M22 33h32M22 40h26M22 47h30" stroke="#cfdbf0" stroke-width="3" stroke-linecap="round"/><circle cx="56" cy="58" r="12" fill="url(#gb2)"/><text x="56" y="62.5" text-anchor="middle" font-size="12" font-weight="900" fill="#fff">%</text><circle cx="52" cy="53" r="3" fill="#fff" opacity=".35"/>`,
 bank: `<defs>${G("gn1", "#93a7d6", "#5a72ad")}${G("gn2", "#e9eefb", "#c7d3ee")}</defs>${SH}<path d="M8 28 40 9l32 19z" fill="url(#gn1)"/><rect x="10" y="27" width="60" height="7" rx="2" fill="#5a72ad"/><g fill="url(#gn2)">` + [0, 1, 2, 3].map(i => `<rect x="${15 + i * 14}" y="36" width="8" height="26" rx="3"/>`).join("") + `</g><rect x="8" y="62" width="64" height="8" rx="3" fill="url(#gn1)"/><circle cx="40" cy="21" r="3.5" fill="#ffd45c"/>`,
 gov: `<defs>${G("gn1", "#8fb0f0", "#4f73c7")}${G("gn2", "#eef3ff", "#cdd9f3")}</defs>${SH}<path d="M40 8c-10 0-17 7-17 15h34c0-8-7-15-17-15z" fill="url(#gn1)"/><rect x="14" y="22" width="52" height="7" rx="2" fill="#4f73c7"/><g fill="url(#gn2)">` + [0, 1, 2, 3, 4].map(i => `<rect x="${17 + i * 10}" y="31" width="6" height="29" rx="2.5"/>`).join("") + `</g><rect x="10" y="60" width="60" height="9" rx="3" fill="url(#gn1)"/>`,
 fund: `<defs>${G("gpf", "#ffffff", "#e9f6f0")}${G("gpa", "#3ddc97", "#12a86b")}${G("gpb", "#5db2ff", "#2f7be8")}</defs>${SH}<rect x="8" y="14" width="64" height="54" rx="12" fill="url(#gpf)" stroke="#cdeadb" stroke-width="1.5"/><circle cx="32" cy="41" r="15" fill="#d9f4e7"/><path d="M32 41V26a15 15 0 0 1 14.3 19.6z" fill="url(#gpa)"/><path d="M32 41l14.3 4.6A15 15 0 0 1 21 51.5z" fill="url(#gpb)"/><path d="M54 33h11M54 41h8M54 49h11" stroke="#3ddc97" stroke-width="3.5" stroke-linecap="round"/>`,
 factory: `<defs>${G("gfa", "#9fb5e6", "#5f79b8")}</defs>${SH}<path d="M8 70V40l14 8v-8l14 8v-8l14 8V20h12v50z" fill="url(#gfa)"/><g fill="#ffd45c"><rect x="14" y="54" width="7" height="7" rx="2"/><rect x="28" y="54" width="7" height="7" rx="2"/><rect x="42" y="54" width="7" height="7" rx="2"/></g><circle cx="57" cy="12" r="5" fill="#e3e8f3"/><circle cx="65" cy="8" r="3.5" fill="#eef1f8"/>`,
 doc: `<defs>${G("gw1", "#ffffff", "#e9eef7")}${G("gpa", "#3ddc97", "#12a86b")}</defs>${SH}<path d="M18 8h30l14 14v48a2 2 0 0 1-2 2H18a2 2 0 0 1-2-2V10a2 2 0 0 1 2-2z" fill="url(#gw1)" stroke="#cdd8ea" stroke-width="1.5"/><path d="M48 8v14h14" fill="#e3e9f5"/><path d="M24 32h28M24 40h28M24 48h18" stroke="#d3dceb" stroke-width="3" stroke-linecap="round"/><circle cx="54" cy="60" r="10" fill="url(#gpa)"/><path d="m49.5 60 3 3 5.5-6" stroke="#fff" stroke-width="2.6" fill="none" stroke-linecap="round" stroke-linejoin="round"/>`,
 cal: `<defs>${G("gw1", "#ffffff", "#eef2f8")}${G("gr2", "#ff7d72", "#ef4a3c")}</defs>${SH}<rect x="10" y="14" width="60" height="56" rx="10" fill="url(#gw1)" stroke="#d5dceb" stroke-width="1.5"/><path d="M10 24a10 10 0 0 1 10-10h40a10 10 0 0 1 10 10v6H10z" fill="url(#gr2)"/><rect x="22" y="8" width="6" height="12" rx="3" fill="#5a6b8f"/><rect x="52" y="8" width="6" height="12" rx="3" fill="#5a6b8f"/><g fill="#d7dfee">` + [0, 1, 2].map(r => [0, 1, 2, 3].map(c => `<rect x="${18 + c * 12}" y="${36 + r * 10}" width="8" height="6" rx="2"/>`).join("")).join("") + `</g><rect x="42" y="46" width="8" height="6" rx="2" fill="#3182f6"/>`,
 chartup: `<defs>${G("gw1", "#ffffff", "#eef2f8")}${G("gpb", "#7cc0ff", "#3182f6")}${G("gpa", "#3ddc97", "#12a86b")}</defs>${SH}<rect x="8" y="10" width="64" height="60" rx="12" fill="url(#gw1)" stroke="#d5dceb" stroke-width="1.5"/><g fill="url(#gpb)"><rect x="18" y="46" width="10" height="16" rx="3"/><rect x="33" y="38" width="10" height="24" rx="3"/><rect x="48" y="28" width="10" height="34" rx="3"/></g><path d="M16 42l14-10 12 6 20-17" stroke="url(#gpa)" stroke-width="4.5" fill="none" stroke-linecap="round" stroke-linejoin="round"/><path d="M53 20h10v10" stroke="#12a86b" stroke-width="4.5" fill="none" stroke-linecap="round" stroke-linejoin="round"/>`,
 hourglass: `<defs>${G("gh", "#ffd45c", "#f0a20c")}</defs>${SH}<rect x="18" y="8" width="44" height="7" rx="3.5" fill="#5a6b8f"/><rect x="18" y="65" width="44" height="7" rx="3.5" fill="#5a6b8f"/><path d="M24 15h32c0 14-12 18-12 25s12 11 12 25H24c0-14 12-18 12-25s-12-11-12-25z" fill="#eaf2ff" stroke="#c9d6ee" stroke-width="1.5"/><path d="M30 60c3-6 7-8 10-8s7 2 10 8z" fill="url(#gh)"/><path d="M31 22h18c-2 6-6 8-9 9-3-1-7-3-9-9z" fill="url(#gh)"/>`,
};
const art = (n, sz = 72) => `<svg class="vx-art" viewBox="0 0 80 80" width="${sz}" height="${sz}" aria-hidden="true">${ART[n] || ART.doc}</svg>`;
const arrowR = '<svg class="vx-oarr" viewBox="0 0 34 20"><path d="M2 10h22" stroke="#ff8a3d" stroke-width="5" stroke-linecap="round"/><path d="M20 2l12 8-12 8z" fill="#ff8a3d"/></svg>';
function dcEx(o) {
  return `<div class="vx-ex">${o.title ? `<div class="vx-ext">${esc(o.title)}</div>` : ""}<div class="vx-exg"><div class="vx-act"><div class="vx-bub">${art(o.l.a, 58)}</div><span>${esc(o.l.t)}</span></div><div class="vx-mid"><div class="vx-pill vx-pb">${esc(o.top.t)} →</div>${o.top.a ? art(o.top.a, 44) : ""}${o.bot && o.bot.a ? art(o.bot.a, 44) : ""}${o.bot ? `<div class="vx-pill vx-pg">← ${esc(o.bot.t)}</div>` : ""}</div><div class="vx-act"><div class="vx-bub">${art(o.r.a, 58)}</div><span>${esc(o.r.t)}</span></div></div>${o.note ? `<div class="vx-exn">${esc(o.note)}</div>` : ""}</div>`; }
function dcFlow(o) {
  return `<div class="vx-flow">${o.title ? `<div class="vx-ft">${esc(o.title)}${o.en ? ` <em>${esc(o.en)}</em>` : ""}</div>` : ""}${(o.sub || []).length ? `<ul class="vx-fs">${o.sub.map(x => `<li>${esc(x)}</li>`).join("")}</ul>` : ""}
  <div class="vx-frow">${o.items.map((it, i) => `${i ? arrowR : ""}<div class="vx-fi">${art(it.a, 70)}<span>${esc(it.t)}</span></div>`).join("")}</div>
  ${(o.or || []).length ? `<div class="vx-or"><div class="vx-orl"><i></i><b>OR</b><i></i></div><div class="vx-orb">${o.or.map((x, i) => `<div class="vx-ob ${i ? "vx-ob2" : ""}"><b>${esc(x.t)}</b>${x.s ? `<small>${esc(x.s)}</small>` : ""}</div>`).join("")}</div></div>` : ""}
  ${o.badge ? `<div class="vx-badge">${esc(o.badge)}</div>` : ""}</div>`; }
function dcChain(o) { return `<div class="vx-ch">${o.title ? `<div class="vx-ext">${esc(o.title)}</div>` : ""}${o.nodes.map((n, i) => `${i ? `<div class="vx-cha"><span class="vx-dots"></span>${o.nodes[i - 1].go ? `<span class="vx-go">${esc(o.nodes[i - 1].go)}</span>` : ""}</div>` : ""}<div class="vx-chn"><div class="vx-bub vx-bs">${art(n.a, 50)}</div><div class="vx-cht"><span class="vx-no">${i + 1}</span><b>${esc(n.t)}</b>${n.x ? `<div>${esc(n.x)}</div>` : ""}</div></div>`).join("")}</div>`; }
const ARTCSS = `:root{--t-card:#ffffff;--t-tint:#f2f4f6;--t-tx:#191f28;--t-sub:#4e5968;--t-blue:#3182f6;--t-bsoft:#e8f3ff;--t-gsoft:#e5f8ee;--t-green:#00a661;--t-orange:#ff8a3d;--t-cream:#fffaf2}
:root:not([data-theme=light]){--t-card:#202027;--t-tint:#2c2c35;--t-tx:#f2f4f6;--t-sub:#b0b8c1;--t-bsoft:rgba(49,130,246,.18);--t-gsoft:rgba(0,196,113,.16);--t-green:#2fd38a;--t-cream:#25252d}
.vx-ex,.vx-ch,.vx-flow{background:var(--t-card);border-radius:24px;padding:18px 14px;margin:14px 0;color:var(--t-tx);box-shadow:0 2px 12px rgba(0,30,80,.08);border:1px solid rgba(0,0,0,.04)}
:root:not([data-theme=light]) .vx-ex,:root:not([data-theme=light]) .vx-ch,:root:not([data-theme=light]) .vx-flow{border-color:rgba(255,255,255,.05);box-shadow:none}
.vx-ext{text-align:center;font-size:18px;font-weight:800;letter-spacing:-.03em;margin:2px 0 14px}
.vx-exg{display:grid;grid-template-columns:80px minmax(0,1fr) 80px;align-items:center;gap:6px}.vx-act{display:flex;flex-direction:column;align-items:center;gap:8px}.vx-act span{font-size:14px;font-weight:800;color:var(--t-tx);text-align:center}
.vx-bub{width:76px;height:76px;border-radius:50%;background:var(--t-tint);display:grid;place-items:center}.vx-bs{width:62px;height:62px;flex:0 0 auto}
.vx-mid{display:flex;flex-direction:column;align-items:center;gap:6px;min-width:0}.vx-pill{font-size:12px;font-weight:800;padding:5px 9px;letter-spacing:-.02em;word-break:keep-all;border-radius:99px;text-align:center;line-height:1.3;max-width:100%}.vx-pb{background:var(--t-bsoft);color:var(--t-blue)}.vx-pg{background:var(--t-gsoft);color:var(--t-green)}
.vx-exn{word-break:keep-all;margin-top:14px;background:var(--t-tint);border-radius:14px;padding:12px 14px;text-align:center;font-size:14px;line-height:1.6;color:var(--t-sub);font-weight:600}
.vx-flow{background:var(--t-cream)}.vx-ft{text-align:center;font-size:24px;font-weight:900;letter-spacing:-.04em;color:#1f4e9a}:root:not([data-theme=light]) .vx-ft{color:#7fb0ff}.vx-ft em{font-style:normal;font-size:16px;color:var(--t-orange);font-weight:800}
.vx-fs{margin:8px auto 4px;padding:0;list-style:none;display:table}.vx-fs li{font-size:14px!important;font-weight:700;color:var(--t-sub);margin:3px 0!important;line-height:1.5!important}.vx-fs li::before{content:"•";color:#1f4e9a;margin-right:6px}
.vx-frow{display:flex;align-items:center;justify-content:center;gap:2px;margin:14px 0 6px}.vx-fi{display:flex;flex-direction:column;align-items:center;gap:4px;width:82px}.vx-fi span{font-size:12.5px;font-weight:800;color:var(--t-sub);text-align:center;line-height:1.3;word-break:keep-all}.vx-oarr{width:28px;height:18px;flex:0 0 auto;margin-bottom:22px}
.vx-or{margin-top:6px}.vx-orl{display:flex;align-items:center;gap:8px;margin:0 18px}.vx-orl i{flex:1;height:2px;background:var(--t-orange);opacity:.6;border-radius:2px}.vx-orl b{color:var(--t-orange);font-size:15px;font-weight:900}
.vx-orb{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:10px}.vx-ob{background:var(--t-card);border:2px solid var(--t-orange);border-radius:14px;padding:10px 8px;text-align:center;box-shadow:0 2px 0 rgba(255,138,61,.35)}.vx-ob b{display:block;font-size:15px;color:var(--t-tx)!important}.vx-ob small{font-size:12px;color:var(--t-sub)}.vx-ob2 b{color:#e8513a!important}
.vx-badge{display:table;margin:14px auto 0;background:#1f4e9a;color:#fff;font-weight:900;font-size:15px;padding:8px 18px;border-radius:10px;transform:skewX(-6deg)}
.vx-ch{padding:18px 14px}.vx-chn{display:flex;align-items:center;gap:12px}.vx-cht{min-width:0}.vx-cht b{font-size:15.5px;color:var(--t-tx)!important}.vx-cht div{font-size:13.5px;color:var(--t-sub);line-height:1.5;margin-top:2px}
.vx-no{display:inline-grid;place-items:center;width:20px;height:20px;border-radius:50%;background:var(--t-blue);color:#fff;font-size:11.5px;font-weight:900;margin-right:6px;vertical-align:1px}
.vx-cha{display:flex;align-items:center;gap:10px;min-height:30px;padding-left:30px}.vx-dots{width:2px;height:26px;background:repeating-linear-gradient(to bottom,var(--t-blue) 0 4px,transparent 4px 8px);opacity:.5}.vx-go{font-size:12.5px;font-weight:800;color:var(--t-blue);background:var(--t-bsoft);padding:3px 10px;border-radius:99px}
.vx-art{flex:0 0 auto;overflow:visible}`;

/* ── 항목 화면 ── */
function dcTermView(c) {
  const e = DC.id[c.id]; if (!e) return `<div class="lhead"><button class="x" data-act="back">${ic("left")}</button></div><p class="mut">항목을 찾지 못했어요.</p>`;
  const lessons = (DC.cfg.lessons ? DC.cfg.lessons() : []).filter(l => [e.k, ...(e.al || [])].some(k => l.text.includes(k))).slice(0, 8);
  const deeps = (window.DP && DP.idx ? DP.idx.topics : []).filter(m => [e.k, ...(e.al || [])].some(k => (m.t + m.sum + (m.kw || []).join(" ")).includes(k)));
  const rel = dcRel(e), hero = !!(e.sec[0] && e.sec[0].b[0] && (e.sec[0].b[0].hero || e.sec[0].b[0].ex || e.sec[0].b[0].chain || e.sec[0].b[0].flow));
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
  const seen = new Set([selfId]), nodes = [], w = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {acceptNode: n => n.parentElement.closest("a,button,h2,h3,mark,.tm,.k,.dalias,.toc2,.drel,.done,textarea,svg,.vx-fi,.vx-act,.vx-pill,.vx-ft,.vx-badge,.vx-ob,.vx-ext,.vx-hero,.vx-cht b,.vx-go,.vx-date,.vx-sh") ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT});
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

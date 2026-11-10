/* 백과사전 — 마스터로드·펀드로드 공용. 앱마다 <앱>/dict/terms.json 을 읽는다.
   · 용어·별칭이 정확히 맞으면 바로 그 항목으로 들어간다 (예: '배당락일' → 배당락일 항목)
   · 본문에만 나오는 말이면 그 절로 스크롤하고 형광펜 표시
   · 레슨·심화 글·백과 본문 속 용어는 자동으로 밑줄 링크 → 누르면 그 항목으로
   deep.js 의 dpBlock 을 그대로 써서 글 형식(p·ul·tip·calc·table·f·j)이 같다. 형식: deep-study/DICT.md */
"use strict";
const DC = {list: null, err: "", q: "", by: {}, id: {}, rx: null, cfg: {}};
const dcNorm = s => String(s || "").toLowerCase().replace(/[\s·・()\[\]{}'"’‘“”,.\-_/]/g, "");
const dcPlain = s => String(s || "").replace(/<[^>]+>/g, "");
function dcBlockText(b) { if (b.p != null) return b.p; if (b.tip != null) return b.tip; if (b.ul) return b.ul.join(" "); if (b.calc) return b.calc.join(" ");
  if (b.table) return [b.table.head, ...b.table.rows].flat().join(" "); if (b.f) return (b.f.steps || []).join(" ");
  if (b.j) return b.j.map(r => r.note || [r.pre, ...(r.dr || []).flat(), ...(r.cr || []).flat()].join(" ")).join(" "); return ""; }
const dcRe = s => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

async function dcLoad() {
  try { const r = await fetch("dict/terms.json?v=" + new Date().toISOString().slice(0, 13)); if (!r.ok) throw 0; const j = await r.json(); dcIndex(j.terms || j); DC.err = ""; }
  catch (e) { DC.err = "백과를 불러오지 못했어요"; DC.list = DC.list || []; }
  if (!cur() ? V.tab === "dict" : ["dterm", "lesson", "dtopic"].includes(cur().v)) render();
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
  return (rec.length ? `<div class="bkh">최근 본 항목</div><div class="dchips">${rec.map(e => `<button data-act="dcopen" data-arg="${esc(e.id)}">${esc(e.k)}</button>`).join("")}</div>` : "")
    + (pick.length ? `<div class="bkh">자주 찾는 말</div><div class="dchips">${pick.map(e => `<button data-act="dcopen" data-arg="${esc(e.id)}">${esc(e.k)}</button>`).join("")}</div>` : "")
    + areas.map(a => { const es = DC.list.filter(e => e.area === a).sort((x, y) => x.k.localeCompare(y.k, "ko"));
      return `<details class="dcar"><summary><b>${esc(a)}</b><span class="mut sm">${es.length}개</span></summary>${es.map(e => dcTermBtn(e)).join("")}</details>`; }).join("");
}

/* ── 항목 화면 ── */
function dcTermView(c) {
  const e = DC.id[c.id]; if (!e) return `<div class="lhead"><button class="x" data-act="back">${ic("left")}</button></div><p class="mut">항목을 찾지 못했어요.</p>`;
  const lessons = (DC.cfg.lessons ? DC.cfg.lessons() : []).filter(l => [e.k, ...(e.al || [])].some(k => l.text.includes(k))).slice(0, 8);
  const deeps = (window.DP && DP.idx ? DP.idx.topics : []).filter(m => [e.k, ...(e.al || [])].some(k => (m.t + m.sum + (m.kw || []).join(" ")).includes(k)));
  const rel = dcRel(e);
  return `<div class="lhead"><button class="x" data-act="back">${ic("left")}</button><span class="mut sm" style="font-weight:700;flex:1">백과 · ${esc(e.area)}</span><button class="x" data-act="dcfind">${ic("search")}</button></div>
  <div class="slide dterm"><span class="k">${esc(e.area)}</span><h2>${esc(e.k)}${e.en ? `<small>${esc(e.en)}</small>` : ""}</h2>
    ${(e.al || []).length ? `<div class="dalias">${e.al.map(a => `<span>${esc(a)}</span>`).join("")}</div>` : ""}
    <div class="done">${esc(e.one)}</div>
    <div class="toc2">${e.sec.map((s, i) => `<button data-act="dcsec" data-arg="${i}"><i>${String.fromCharCode(65 + i)}</i>${esc(s.h)}</button>`).join("")}</div>
    ${e.sec.map((s, i) => `<section id="ds-${i}" class="dsec"><h3><i>${String.fromCharCode(65 + i)}</i>${esc(s.h)}</h3>${s.b.map(dpBlock).join("")}</section>`).join("")}
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
  else if (c.v === "lesson" || c.v === "dtopic") dcLink($(".slide"), null);
}
function dcOpen(id, hl) { if (!DC.id[id]) return; S.dcRecent = [id, ...(S.dcRecent || []).filter(x => x !== id)].slice(0, 10); save(); push({v: "dterm", id, hl: hl || ""}); }

function DictInit(cfg) {
  DC.cfg = cfg || {};
  document.head.insertAdjacentHTML("beforeend", `<style>
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
.done{background:var(--bg2);border-left:4px solid var(--acc);border-radius:10px;padding:12px 14px;font-size:16px;line-height:1.7;font-weight:600}
.toc2{display:flex;flex-direction:column;gap:2px;margin:14px 0 4px;padding:8px 0;border-top:1px solid var(--line);border-bottom:1px solid var(--line)}
.toc2 button{display:flex;gap:10px;align-items:center;text-align:left;padding:7px 2px;font-size:14.5px;color:var(--sub)}
.toc2 i,.dsec h3 i{font-style:normal;width:22px;height:22px;border-radius:7px;background:var(--acc-soft);color:var(--acc);display:inline-grid;place-items:center;font-size:12px;font-weight:900;flex:0 0 auto}
.dsec{scroll-margin-top:calc(env(safe-area-inset-top) + 12px)}.dsec h3{display:flex;gap:9px;align-items:center;font-size:18.5px;margin:26px 0 10px;letter-spacing:-.02em}
.dterm .dsec p{font-size:16.5px;line-height:1.85;margin:0 0 12px}.dterm .dsec li{font-size:16px}
</style>`);
  IP.search = '<circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/>';
  const at = TABS.findIndex(t => t[0] === "road") + 1; TABS.splice(at, 0, ["dict", "백과", "book"]);
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

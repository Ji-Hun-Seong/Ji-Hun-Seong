/* 심화 서고 — 펀드로드·마스터로드 공용. 앱마다 <앱>/deep/index.json 과 topics/*.json 을 읽는다.
   글은 deep-study/README.md 형식으로 매일 쌓이고, 기록은 앱의 S 에 함께 저장된다. */
"use strict";
const DP = {idx: null, topics: {}, err: "", q: ""};
const dpStamp = () => new Date().toISOString().slice(0, 13);
async function dpIndex() { try { const r = await fetch("deep/index.json?v=" + dpStamp()); if (!r.ok) throw 0; DP.idx = await r.json(); DP.err = ""; } catch (e) { DP.err = "목록을 불러오지 못했어요"; DP.idx = DP.idx || {topics: []}; } if (!cur() && V.tab === "deep") render(); }
async function dpTopic(m) { if (DP.topics[m.id]) return DP.topics[m.id]; const r = await fetch(`deep/topics/${m.id}.json?v=${encodeURIComponent(m.date)}`); if (!r.ok) throw 0; return DP.topics[m.id] = await r.json(); }
const dpFlow = f => f.steps ? `<div class="flow">${f.steps.map((s, i) => `<div class="st"><span class="no">${i + 1}</span><span>${esc(s)}</span></div>`).join("")}</div>` : "";
const dpAc = s => s.map(a => `<div class="ac"><span>${esc(a[0])}${a[2] ? ` <small>${esc(a[2])}</small>` : ""}</span>${a[1] ? `<b>${esc(a[1])}</b>` : ""}</div>`).join("");
const dpJ = rows => `<div class="jr">${rows.map(r => r.note != null ? `<div class="jn">${esc(r.note)}</div>` : `${r.pre ? `<div class="jp">${esc(r.pre)}</div>` : ""}<div class="jt"><div><em>차변</em>${dpAc(r.dr)}</div><div><em>대변</em>${dpAc(r.cr)}</div></div>`).join("")}</div>`;
const dpTable = t => `<div class="dtw"><table class="dt"><thead><tr>${t.head.map(h => `<th>${esc(h)}</th>`).join("")}</tr></thead><tbody>${t.rows.map(r => `<tr>${r.map(c => `<td>${esc(c)}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
function dpBlock(b) {
  if (b.p != null) return `<p>${esc(b.p)}</p>`;
  if (b.ul) return `<ul>${b.ul.map(t => `<li>${esc(t)}</li>`).join("")}</ul>`;
  if (b.tip != null) return `<div class="tip">${ic("bulb")}<span>${esc(b.tip)}</span></div>`;
  if (b.calc) return `<div class="jr">${b.calc.map(t => `<div class="jn">${esc(t)}</div>`).join("")}</div>`;
  if (b.j) return dpJ(b.j);
  if (b.f) return dpFlow(b.f);
  if (b.table) return dpTable(b.table);
  return "";
}
const dpSlides = t => [{k: t.area, h: t.t, body: `<p>${esc(t.intro)}</p><div class="toc">${t.sections.map((s, i) => `<span>${i + 1}. ${esc(s.h)}</span>`).join("")}</div>`},
  ...t.sections.map((s, i) => ({k: `${i + 1} / ${t.sections.length}`, h: s.h, body: s.b.map(dpBlock).join("")})),
  {k: "근거", h: "확인한 원문", body: `<ul>${t.src.map(s => `<li><a class="dl" href="${esc(s.u)}" target="_blank" rel="noopener">${esc(s.t)}</a> <span class="mut xs">${esc(s.o || "")}</span></li>`).join("")}</ul>${t.limits ? `<div class="tip">${ic("alert")}<span>${esc(t.limits)}</span></div>` : ""}`}];
const dpQs = t => t.qs.map((r, i) => { const id = `${t.id}-${i + 1}`, order = r[1].map((_, k) => k).sort((x, y) => dpHash(id + x) - dpHash(id + y)); return {id, q: r[0], o: order.map(k => r[1][k]), a: order.indexOf(0), e: r[2], deep: t.t}; });
function dpHash(s) { let h = 2166136261; for (const c of s) { h ^= c.charCodeAt(0); h = Math.imul(h, 16777619); } return h >>> 0; }
function dpList() { const all = DP.idx.topics, q = DP.q.trim().toLowerCase(), f = all.filter(m => !q || (m.t + m.area + m.sum).toLowerCase().includes(q)), areas = [...new Set(f.map(m => m.area))];
  if (!all.length) return `<div class="card mut">첫 글을 준비 중이에요. 매일 한 주제씩 쌓여요.</div>`;
  return areas.map(a => `<div class="bkh">${esc(a)}</div>` + f.filter(m => m.area === a).map(m => `<button class="bki" data-act="dopen" data-arg="${esc(m.id)}"><span class="between"><b>${esc(m.t)}</b>${S.deepDone[m.id] ? `<span style="color:var(--acc)">${ic("check")}</span>` : S.deepPos[m.id] ? `<span class="mut xs">읽는 중</span>` : ""}</span><small class="mut">${esc(m.sum)}</small><small class="mut xs">${esc(m.date)} · ${m.n_sections}절 · 약 ${Math.max(1, Math.round(m.chars / 500))}분 · 문제 ${m.n_qs}개</small></button>`).join("")).join("") || `<p class="mut" style="text-align:center;margin:30px 0">검색 결과가 없어요.</p>`; }
function DeepInit() {
  S.dq = S.dq || {}; S.deepDone = S.deepDone || {}; S.deepPos = S.deepPos || {};
  document.head.insertAdjacentHTML("beforeend", `<style>.flow{margin:12px 0}.flow .st{display:flex;align-items:center;gap:10px;background:var(--bg2);border:1px solid var(--line);border-radius:12px;padding:10px 12px;font-size:14.5px;line-height:1.4;font-weight:600;margin-bottom:8px}.flow .no{width:24px;height:24px;border-radius:8px;background:var(--acc-soft);color:var(--acc);display:grid;place-items:center;font-size:12.5px;font-weight:900;flex:0 0 auto}.toc{display:flex;flex-direction:column;gap:6px;margin-top:14px;padding-top:12px;border-top:1px solid var(--line);font-size:14px;color:var(--sub)}.jr{background:var(--bg2);border:1px solid var(--line);border-radius:14px;padding:12px;margin:12px 0}.jn{font-size:13.5px;line-height:1.6;color:var(--sub);margin:4px 0;font-variant-numeric:tabular-nums}.jp{font-size:12.5px;font-weight:800;color:var(--acc);margin:10px 0 4px}.jt{display:grid;grid-template-columns:1fr 1fr;gap:1px;background:var(--line);border-radius:10px;overflow:hidden;margin:6px 0}.jt>div{background:var(--card);padding:9px 10px}.jt em{display:block;font-style:normal;font-size:11.5px;font-weight:800;color:var(--sub2);margin-bottom:4px}.ac{display:flex;flex-direction:column;font-size:13.5px;line-height:1.35;margin:5px 0}.slide .ac b{color:var(--txt);font-variant-numeric:tabular-nums}.ac small{color:var(--sub2);font-size:11.5px}.tip{display:flex;gap:9px;background:var(--gold-soft);border-radius:12px;padding:11px 12px;font-size:14.5px;line-height:1.6;margin:10px 0 12px}.tip svg{color:var(--gold);margin-top:2px}.search{width:100%;height:48px;border:1px solid var(--line);border-radius:14px;background:var(--card);color:var(--txt);font:inherit;padding:0 14px;margin-bottom:6px}.bkh{font-size:13px;font-weight:800;color:var(--acc);margin:16px 2px 6px}.bki{display:block;width:100%;text-align:left;background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px 14px;margin:6px 0;font-size:15px}.bki small{display:block;margin-top:3px;font-size:13px;line-height:1.5}.dtw{overflow-x:auto;margin:12px 0}.dt{border-collapse:collapse;font-size:13px;line-height:1.45;min-width:100%}.dt th,.dt td{border:1px solid var(--line);padding:7px 8px;text-align:left;vertical-align:top}.dt th{background:var(--bg2);white-space:nowrap}.dl{color:var(--acc)}.slide p{margin:0 0 12px}.slide p,.slide li,.q,.opt,.fb,.tip{word-break:keep-all;overflow-wrap:anywhere}nav.tab button{font-size:11.5px}</style>`);
  TABS.splice(1, 0, ["deep", "심화", "list"]);
  VIEW.deep = () => { if (!DP.idx) { dpIndex(); return `<h1 class="pg">심화 서고</h1><div class="pgsub">불러오는 중…</div>`; } setTimeout(() => { const si = $("#dpsearch"); if (si) si.oninput = () => { DP.q = si.value; const b = $("#dpres"); b.innerHTML = dpList(); bind2(b); }; });
    const t = DP.idx.topics, dn = t.filter(m => S.deepDone[m.id]).length, ch = t.reduce((s, m) => s + m.chars, 0);
    return `<h1 class="pg">심화 서고</h1><div class="pgsub">끝이 없는 공부예요. 매일 한 주제씩 원문으로 확인해 쌓입니다.</div><div class="stat3"><div><b>${t.length}</b><small>주제</small></div><div><b>${dn}</b><small>읽은 주제</small></div><div><b>${Math.round(ch / 1000)}천</b><small>누적 글자</small></div></div>${DP.err ? `<p class="mut sm">${DP.err}</p>` : ""}<div style="height:10px"></div><input id="dpsearch" class="search" type="search" placeholder="주제 검색" value="${esc(DP.q)}" autocomplete="off"><div id="dpres">${dpList()}</div>`; };
  VIEW.dtopic = c => { const t = c.t, sl = dpSlides(t), qs = dpQs(t), total = sl.length + qs.length, head = n => `<div class="lhead"><button class="x" data-act="back">${ic("x")}</button><div class="bar"><i style="width:${n / total * 100}%"></i></div><span class="mut sm" style="font-weight:700">${Math.min(n + 1, total)}/${total}</span></div>`;
    if (c.i < sl.length) { const s = sl[c.i]; return head(c.i) + `<div class="slide"><span class="k">${esc(s.k)}</span><h2>${esc(s.h)}</h2>${s.body}</div>${dock(`<button class="btn" data-act="dnx">${c.i === sl.length - 1 ? "확인 문제 풀기" : "다음"}</button>`, c.i > 0)}`; }
    const qi = c.i - sl.length;
    if (qi >= qs.length) return `<div class="big"><div class="s">${c.ok}/${qs.length}</div><p class="mut">${esc(t.t)}</p><span class="xpchip">+${c.gain} XP</span></div>${dock(`<button class="btn" data-act="back">목록으로</button>`)}`;
    const q = qs[qi]; return head(c.i) + `<span class="pill acc" style="margin-bottom:4px">확인 ${qi + 1}/${qs.length}</span><div class="q">${esc(q.q)}</div>${q.o.map((o, i) => optBtn(i, o, c.pick, c.shown ? q.a : null, "dqp")).join("")}${c.shown ? `<div class="fb ${c.pick === q.a ? "ok" : "no"}"><b>${c.pick === q.a ? "정답! +5 XP" : "정답은 " + (q.a + 1) + "번"}</b>${esc(q.e)}</div>` : ""}${dock(`<button class="btn" data-act="${c.shown ? "dqn" : "dqc"}" ${c.pick == null ? "disabled" : ""}>${c.shown ? "계속" : "확인"}</button>`)}`; };
  Object.assign(ACT, {
    dopen: async id => { const m = DP.idx.topics.find(x => x.id === id); try { const t = await dpTopic(m); const p = S.deepDone[id] ? 0 : (S.deepPos[id] || 0); push({v: "dtopic", t, i: p < dpSlides(t).length ? p : 0, pick: null, shown: false, ok: 0, gain: 0}); } catch (e) { toast("글을 불러오지 못했어요"); } },
    dnx: () => { const c = cur(); c.i++; S.deepPos[c.t.id] = c.i; save(); render(); scrollTo(0, 0); },
    dqp: i => { const c = cur(); if (!c.shown) { c.pick = +i; render(); } },
    dqc: () => { const c = cur(), qs = dpQs(c.t), q = qs[c.i - dpSlides(c.t).length], ok = c.pick === q.a; S.dq[q.id] = q; record(q.id, ok); if (ok) { c.ok++; c.gain += 5; } c.shown = true; render(); },
    dqn: () => { const c = cur(), id = c.t.id; c.i++; c.pick = null; c.shown = false; if (c.i - dpSlides(c.t).length >= c.t.qs.length) { if (!S.deepDone[id]) { c.gain += 30; S.deepDone[id] = Date.now(); } delete S.deepPos[id]; addXP(c.gain); } render(); scrollTo(0, 0); }
  });
  dpIndex();
}
function bind2(root) { root.querySelectorAll("[data-act]").forEach(b => b.onclick = e => { e.stopPropagation(); ACT[b.dataset.act](b.dataset.arg, b); }); }

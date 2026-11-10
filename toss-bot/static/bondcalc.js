/* 채권 단가 계산기 — 금융투자협회 '금융투자회사의 영업 및 업무에 관한 규정' 제7-5조·별표 14 방식.
   이표채: 이자 구간 단위 복리 + 다음 이자일까지 단수기간 단리(D/B). 만기일시(할인·복리·단리채): 연 단위 복리 + 1년 미만 단리.
   일수는 달력 일수(윤년 366), 단가는 액면 1만 원당·원 미만 절사. 영업일(휴일) 조정은 하지 않는다. */
"use strict";
const BC = {f: {kind: "coupon", c: "2.25", iss: "2018-06-10", mat: "2021-06-10", K: "2", st: "2019-10-28", r: "1.30", face: "10000000000", sk: ""}};
const bcD = s => { const [y, m, d] = s.split("-").map(Number); return new Date(Date.UTC(y, m - 1, d)); };
const bcS = d => d.toISOString().slice(0, 10);
const bcDays = (a, b) => Math.round((b - a) / 864e5);
function bcAddM(d, m) { const y = d.getUTCFullYear(), mo = d.getUTCMonth() + m, last = new Date(Date.UTC(y, mo + 1, 0)).getUTCDate(); return new Date(Date.UTC(y, mo, Math.min(d.getUTCDate(), last))); }
const bcN = (x, p = 0) => Number(x).toLocaleString("ko-KR", {minimumFractionDigits: p, maximumFractionDigits: p});

function bcCoupon(c, mat, K, st, r) {
  const step = 12 / K, ds = [mat]; for (let i = 1; ; i++) { const d = bcAddM(mat, -step * i); ds.unshift(d); if (d <= st) break; }
  const prev = ds[0], fut = ds.slice(1), n = fut.length, nxt = fut[0], I = 10000 * c / K, v = 1 + r / K;
  const D = bcDays(st, nxt), B = bcDays(prev, nxt), simple = 1 + r / K * D / B;
  const flows = fut.map((d, k) => { const cf = I + (k === n - 1 ? 10000 : 0), pv = cf / Math.pow(v, k) / simple; return {d, cf, pv, t: (k + D / B) / K}; });
  const dirty = flows.reduce((s, f) => s + f.pv, 0), ai = I * bcDays(prev, st) / B, mac = flows.reduce((s, f) => s + f.pv * f.t, 0) / dirty;
  return {dirty, ai, mac, mod: mac / v, flows, steps: [`이자 구간: ${bcS(prev)} ~ ${bcS(nxt)} (B = ${B}일), 결제일 → 다음 이자일 D = ${D}일`, `회차 이자 I = 10,000 × ${(c * 100).toFixed(3)}% ÷ ${K} = ${bcN(I, 4)}원, 남은 지급 ${n}회`, `다음 이자일 시점 가치 = Σ CF ÷ (1 + r/K)^k = ${bcN(dirty * simple, 4)}`, `단리 할인 = 1 + ${(r / K).toFixed(6)} × ${D}/${B} = ${simple.toFixed(6)}`, `더티 단가 = ${bcN(dirty * simple, 4)} ÷ ${simple.toFixed(6)} = ${bcN(dirty, 4)}`, `경과이자 = ${bcN(I, 4)} × ${bcDays(prev, st)}/${B} = ${bcN(ai, 4)}`]};
}
function bcLump(S, mat, st, r) {
  let n = 0; while (bcAddM(mat, -12 * (n + 1)) >= st) n++;
  const anchor = bcAddM(mat, -12 * n), d = bcDays(st, anchor), yb = bcDays(bcAddM(anchor, -12), anchor), simple = 1 + r * d / yb;
  const dirty = S / Math.pow(1 + r, n) / simple, mac = n + d / yb;
  return {dirty, ai: 0, mac, mod: mac / (1 + r), flows: [{d: mat, cf: S, pv: dirty, t: mac}], steps: [`만기 상환액 S = ${bcN(S, 2)}`, `연 단위 기간 n = ${n}년 (${bcS(anchor)} ~ ${bcS(mat)}), 남은 단수기간 d = ${d}일 / 그 1년 ${yb}일`, `가격 = S ÷ (1 + r)^${n} ÷ (1 + r × ${d}/${yb}) = ${bcN(dirty, 4)}`]};
}
function bcRun() {
  const f = BC.f, c = +f.c / 100, r = +f.r / 100, K = +f.K, face = +String(f.face).replace(/,/g, "");
  const mat = bcD(f.mat), st = bcD(f.st), iss = bcD(f.iss);
  if (!(st < mat) || isNaN(r) || isNaN(c)) return {err: "결제일이 만기 전인지, 숫자가 맞는지 확인해 주세요."};
  let x, note = "";
  if (f.kind === "coupon") x = bcCoupon(c, mat, K, st, r);
  else { let S = 10000; if (f.kind !== "discount") { const yrs = bcDays(iss, mat) / 365; S = Math.floor(f.kind === "compound" ? 10000 * Math.pow(1 + c, Math.round(yrs)) : 10000 * (1 + c * Math.round(yrs))); note = `발행~만기 ${Math.round(yrs)}년 ${f.kind === "compound" ? "연복리" : "단리"}로 만기 상환액 계산(원 미만 절사)`; }
    x = bcLump(S, mat, st, r); if (note) x.steps.unshift(note); }
  const unit = Math.floor(x.dirty + 1e-9);
  return {...x, unit, amt: unit * face / 10000, aiAmt: x.ai * face / 10000, dv01: x.mod * unit * face / 10000 * 1e-4};
}
function bcView() {
  const f = BC.f, x = bcRun(), inp = (k, l, t = "text", ex = "") => `<label class="bcf"><span>${l}</span><input data-bc="${k}" type="${t}" value="${esc(f[k])}" ${ex}></label>`;
  return `<div class="lhead"><button class="x" data-act="back">${ic("left")}</button><span class="mut sm" style="font-weight:700;flex:1">채권 단가 계산기</span></div>
  <div class="card"><div class="bcg">
    <label class="bcf"><span>종류</span><select data-bc="kind">${[["coupon", "이표채"], ["discount", "할인채"], ["compound", "복리채"], ["simple", "단리채"]].map(([k, l]) => `<option value="${k}" ${f.kind === k ? "selected" : ""}>${l}</option>`).join("")}</select></label>
    ${inp("c", "표면금리 %", "text", 'inputmode="decimal"')}${inp("r", "수익률 %", "text", 'inputmode="decimal"')}
    ${inp("iss", "발행일", "date")}${inp("mat", "만기일", "date")}${inp("st", "결제일", "date")}
    ${f.kind === "coupon" ? `<label class="bcf"><span>이자 주기</span><select data-bc="K">${[["1", "연 1회"], ["2", "6개월"], ["4", "3개월"], ["12", "1개월"]].map(([k, l]) => `<option value="${k}" ${f.K === k ? "selected" : ""}>${l}</option>`).join("")}</select></label>` : ""}
    ${inp("face", "액면 금액(원)", "text", 'inputmode="numeric"')}
  </div><p class="mut xs" style="margin:8px 0 0">기본값: 국고02250-2106(18-3) 실제 발행 조건 · 결제일·수익률은 예시. 휴일 조정은 반영하지 않아요.</p></div>
  <div id="bcout">${bcOut(x)}</div>`;
}
function bcOut(x) {
  if (x.err) return `<div class="card mut">${x.err}</div>`;
  return `<div class="card"><div class="bcres">
    <div><small>단가(1만 원당, 원 미만 절사)</small><b>${bcN(x.unit)}원</b><span class="mut xs">계산값 ${bcN(x.dirty, 4)}</span></div>
    <div><small>결제금액</small><b>${bcN(x.amt)}원</b></div>
    <div><small>경과이자(1만 원당)</small><b>${bcN(x.ai, 4)}</b><span class="mut xs">금액 ${bcN(Math.round(x.aiAmt))}원</span></div>
    <div><small>클린 단가</small><b>${bcN(x.dirty - x.ai, 4)}</b></div>
    <div><small>수정듀레이션</small><b>${x.mod.toFixed(4)}</b><span class="mut xs">맥컬리 ${x.mac.toFixed(4)}년</span></div>
    <div><small>DV01(1bp)</small><b>${bcN(Math.round(x.dv01))}원</b></div></div></div>
  <div class="card"><b>계산 과정</b><div class="jr">${x.steps.map(s => `<div class="jn">${esc(s)}</div>`).join("")}</div>
  <div class="dtw"><table class="dt"><thead><tr><th>지급일</th><th>현금흐름</th><th>현재가치</th><th>기간(년)</th></tr></thead><tbody>${x.flows.map(f => `<tr><td>${bcS(f.d)}</td><td>${bcN(f.cf, 2)}</td><td>${bcN(f.pv, 4)}</td><td>${f.t.toFixed(4)}</td></tr>`).join("")}</tbody></table></div></div>`;
}
function bcBind() { document.querySelectorAll("[data-bc]").forEach(el => el[el.tagName === "SELECT" ? "onchange" : "oninput"] = () => { BC.f[el.dataset.bc] = el.value; if (el.tagName === "SELECT") { render(); return; } const o = $("#bcout"); if (o) o.innerHTML = bcOut(bcRun()); }); }
function BondCalcInit() {
  document.head.insertAdjacentHTML("beforeend", `<style>.bcg{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:10px}.bcf{display:flex;flex-direction:column;gap:4px;font-size:12.5px;color:var(--sub)}.bcf input,.bcf select{height:44px;border:1px solid var(--line);border-radius:10px;background:var(--bg2);color:var(--txt);font:inherit;font-size:15px;padding:0 10px;min-width:0;width:100%;box-sizing:border-box;-webkit-appearance:none;appearance:none}.bcres{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:12px}.bcres b{word-break:break-all}.bcres div{display:flex;flex-direction:column}.bcres small{color:var(--sub);font-size:12px}.bcres b{font-size:18px;font-variant-numeric:tabular-nums}</style>`);
  VIEW.bcalc = () => { setTimeout(bcBind); return bcView(); };
  ACT.bcopen = () => push({v: "bcalc"});
}

/* 퀴즈 계산기 — 문제 화면(보기 .opt 가 있을 때)에 떠 있는 계산기 버튼 + 하단 계산기 시트.
   eval 없이 직접 파싱(사칙연산·괄호·%). 결과는 '165만 원'처럼 한국식 단위로도 보여 준다.
   마스터로드·펀드로드·자문패스 공용. 스크립트 태그 하나로 붙고, 다른 코드와 상태를 공유하지 않는다. */
(function () {
  "use strict";
  const ACC = "var(--acc, var(--pri, #2ee6a8))";
  const css = `
#qcFab{position:fixed;right:max(16px, calc(50% - 262px));bottom:calc(env(safe-area-inset-bottom) + 92px);z-index:30;width:56px;height:56px;border-radius:18px;border:1px solid var(--line);background:var(--card);color:${ACC};display:none;place-items:center;box-shadow:0 6px 18px rgba(0,0,0,.28);cursor:pointer;padding:0}
#qcFab.on{display:grid}#qcFab svg{width:26px;height:26px}#qcFab:active{transform:scale(.95)}
#qcFab .dot{position:absolute;top:8px;right:8px;width:8px;height:8px;border-radius:50%;background:${ACC};display:none}#qcFab.has .dot{display:block}
#qcWrap{position:fixed;inset:0;z-index:55;display:none;align-items:flex-end;justify-content:center;background:rgba(0,0,0,.15)}
#qcWrap.on{display:flex}
#qc{width:100%;max-width:560px;background:var(--card);border:1px solid var(--line);border-bottom:0;border-radius:24px 24px 0 0;padding:10px 16px calc(env(safe-area-inset-bottom) + 14px);box-shadow:0 -10px 30px rgba(0,0,0,.3);font-family:inherit;color:var(--txt)}
#qc .grab{width:40px;height:5px;border-radius:9px;background:var(--line);margin:0 auto 8px}
#qc .top{display:flex;align-items:center;justify-content:space-between;margin-bottom:6px}
#qc .top b{font-size:15px}#qc .top button{background:none;border:0;color:var(--sub);font:inherit;font-weight:700;font-size:14px;padding:6px 4px;cursor:pointer}
#qc .scr{background:var(--bg2, var(--chip));border:1px solid var(--line);border-radius:16px;padding:10px 14px;text-align:right;min-height:78px}
#qc .ex{font-size:17px;color:var(--sub);word-break:break-all;min-height:26px;font-variant-numeric:tabular-nums}
#qc .rs{font-size:28px;font-weight:900;letter-spacing:-.02em;word-break:break-all;line-height:1.25;font-variant-numeric:tabular-nums}
#qc .ko{font-size:13.5px;color:${ACC};font-weight:700;min-height:20px}
#qc .his{display:flex;gap:6px;overflow-x:auto;margin:8px 0 2px;scrollbar-width:none}#qc .his::-webkit-scrollbar{display:none}
#qc .his button{flex:0 0 auto;border:1px solid var(--line);background:var(--chip);color:var(--sub);border-radius:99px;padding:5px 11px;font:inherit;font-size:12.5px;font-weight:700;cursor:pointer;white-space:nowrap}
#qc .keys{display:grid;grid-template-columns:repeat(4,1fr);gap:7px;margin-top:8px}
#qc .keys button{height:48px;border-radius:14px;border:0;background:var(--chip);color:var(--txt);font:inherit;font-size:21px;font-weight:700;cursor:pointer;-webkit-user-select:none;user-select:none}
#qc .keys button:active{filter:brightness(1.25);transform:scale(.97)}
#qc .keys .fn{color:var(--sub);font-size:17px}#qc .keys .op{color:${ACC};font-size:24px}
#qc .keys .eq{background:${ACC};color:var(--qc-on,#04261b)}
#qc .unit{display:flex;gap:8px;margin-top:8px}#qc .unit button{flex:1;height:36px;border-radius:12px;border:1px solid var(--line);background:none;color:var(--sub);font:inherit;font-size:14px;font-weight:800;cursor:pointer}`;

  const ICON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="4" y="2" width="16" height="20" rx="2"/><path d="M8 6h8M8 10h.01M12 10h.01M16 10h.01M8 14h.01M12 14h.01M16 14h.01M8 18h.01M12 18h4"/></svg>';

  /* ── 계산 엔진 (재귀 하강) ── */
  function calc(src) {
    const s = src.replace(/×/g, "*").replace(/÷/g, "/").replace(/−/g, "-").replace(/,/g, "").replace(/\s/g, "");
    let i = 0;
    const peek = () => s[i];
    function num() {
      const m = /^(\d+\.?\d*|\.\d+)/.exec(s.slice(i)); if (!m) throw 0; i += m[0].length; let v = parseFloat(m[0]);
      if (s[i] === "만") { v *= 1e4; i++; } else if (s[i] === "억") { v *= 1e8; i++; }
      return v;
    }
    function atom() {
      let v;
      if (peek() === "-") { i++; return -atom(); }
      if (peek() === "+") { i++; return atom(); }
      if (peek() === "(") { i++; v = expr(); if (peek() === ")") i++; }
      else v = num();
      while (peek() === "%") { v /= 100; i++; }
      if (peek() === "(" || /[\d.]/.test(peek() || "")) v *= atom(); // 2(3+4) 같은 암묵 곱
      return v;
    }
    function pow() { let v = atom(); if (peek() === "^") { i++; v = Math.pow(v, unary()); } return v; }
    function unary() { if (peek() === "-") { i++; return -unary(); } return pow(); }
    function term() { let v = unary(); while (peek() === "*" || peek() === "/") { const o = s[i++]; const r = unary(); v = o === "*" ? v * r : v / r; } return v; }
    function expr() { let v = term(); while (peek() === "+" || peek() === "-") { const o = s[i++]; const r = term(); v = o === "+" ? v + r : v - r; } return v; }
    if (!s) return null;
    const v = expr(); if (i < s.length) throw 0; if (!isFinite(v)) throw 0;
    return Math.round(v * 1e10) / 1e10;
  }
  const fmt = v => { if (v == null) return ""; const a = Math.abs(v); if (a !== 0 && (a >= 1e15 || a < 1e-6)) return v.toExponential(6); return v.toLocaleString("ko-KR", {maximumFractionDigits: 8}); };
  function ko(v) { // 165만 원 / 1억 2,300만 원
    if (v == null || !isFinite(v) || Math.abs(v) < 1e4) return "";
    const neg = v < 0; let n = Math.round(Math.abs(v)); const jo = Math.floor(n / 1e12), eok = Math.floor(n % 1e12 / 1e8), man = Math.floor(n % 1e8 / 1e4), won = n % 1e4;
    const p = []; if (jo) p.push(jo.toLocaleString() + "조"); if (eok) p.push(eok.toLocaleString() + "억"); if (man) p.push(man.toLocaleString() + "만"); if (won) p.push(won.toLocaleString());
    return "≈ " + (neg ? "−" : "") + p.join(" ") + (Math.abs(v) % 1 ? " (소수점 반올림)" : "");
  }

  /* ── 상태 ── */
  const K = "quiz-calc-v1";
  let st = {ex: "", his: []}; try { Object.assign(st, JSON.parse(localStorage.getItem(K) || "{}")); } catch (e) {}
  const keep = () => { try { localStorage.setItem(K, JSON.stringify(st)); } catch (e) {} };
  let justEq = false;

  function build() {
    document.head.insertAdjacentHTML("beforeend", `<style>${css}</style>`);
    const fab = document.createElement("button"); fab.id = "qcFab"; fab.setAttribute("aria-label", "계산기 열기"); fab.innerHTML = ICON + '<i class="dot"></i>';
    const wrap = document.createElement("div"); wrap.id = "qcWrap";
    const K4 = [["AC", "fn"], ["(", "fn"], [")", "fn"], ["÷", "op"], ["7"], ["8"], ["9"], ["×", "op"], ["4"], ["5"], ["6"], ["−", "op"], ["1"], ["2"], ["3"], ["+", "op"], ["%", "fn"], ["0"], [".", ""], ["=", "eq"]];
    wrap.innerHTML = `<div id="qc" role="dialog" aria-label="계산기"><div class="grab"></div>
      <div class="top"><b>계산기</b><span><button data-k="⌫">⌫ 지우기</button><button data-k="close">닫기</button></span></div>
      <div class="scr"><div class="ex"></div><div class="rs">0</div><div class="ko"></div></div>
      <div class="his"></div>
      <div class="unit"><button data-k="만">만</button><button data-k="억">억</button><button data-k="00">00</button><button data-k="^">xʸ</button></div>
      <div class="keys">${K4.map(([k, c]) => `<button data-k="${k}" class="${c || ""}">${k}</button>`).join("")}</div></div>`;
    document.body.append(fab, wrap);
    fab.onclick = open;
    wrap.onclick = e => { if (e.target === wrap) close(); };
    wrap.querySelectorAll("[data-k]").forEach(b => b.onclick = e => { e.stopPropagation(); press(b.dataset.k); });
    if (!getComputedStyle(document.documentElement).getPropertyValue("--acc").trim()) wrap.style.setProperty("--qc-on", "#fff");
    paint();
    // 보기가 있는 문제 화면에서만 버튼 노출
    const sync = () => { const on = !!document.querySelector("#app .opt"); fab.classList.toggle("on", on); if (!on && wrap.classList.contains("on")) close(); };
    new MutationObserver(sync).observe(document.getElementById("app") || document.body, {childList: true, subtree: true}); sync();
    document.addEventListener("keydown", e => {
      if (!wrap.classList.contains("on")) return;
      const m = {"*": "×", "/": "÷", "-": "−", Enter: "=", "=": "=", Backspace: "⌫", Escape: "close", Delete: "AC"}[e.key] || (/^[\d.+()%^]$/.test(e.key) ? e.key : null);
      if (m) { e.preventDefault(); press(m); }
    });
  }
  function open() { document.getElementById("qcWrap").classList.add("on"); }
  function close() { document.getElementById("qcWrap").classList.remove("on"); }
  function press(k) {
    if (k === "close") return close();
    if (k === "AC") { st.ex = ""; justEq = false; }
    else if (k === "⌫") { st.ex = st.ex.slice(0, -1); justEq = false; }
    else if (k === "=") { let v; try { v = calc(st.ex); } catch (e) { v = undefined; }
      if (v == null) return flash();
      st.his = [`${st.ex} = ${fmt(v)}`, ...st.his.filter(h => h !== `${st.ex} = ${fmt(v)}`)].slice(0, 6); st.ex = String(v); justEq = true; }
    else { if (justEq && /^[\d.(만억]$/.test(k)) st.ex = ""; justEq = false; st.ex += k; }
    keep(); paint();
  }
  function flash() { const r = document.querySelector("#qc .rs"); r.style.color = "var(--bad, #ff6b7a)"; r.textContent = "식을 확인해 주세요"; setTimeout(() => { r.style.color = ""; paint(); }, 900); }
  function paint() {
    const q = document.getElementById("qc"); if (!q) return; let v = null; try { v = calc(st.ex); } catch (e) {}
    q.querySelector(".ex").textContent = st.ex.replace(/\d+(\.\d+)?/g, m => m.includes(".") ? Number(m.split(".")[0]).toLocaleString("ko-KR") + "." + m.split(".")[1] : Number(m).toLocaleString("ko-KR")) || " ";
    q.querySelector(".rs").textContent = v == null ? (st.ex ? "…" : "0") : fmt(v);
    q.querySelector(".ko").textContent = ko(v);
    const h = q.querySelector(".his"); h.innerHTML = st.his.map((t, i) => `<button data-h="${i}">${t.replace(/[&<>"]/g, "")}</button>`).join("");
    h.querySelectorAll("[data-h]").forEach(b => b.onclick = e => { e.stopPropagation(); const t = st.his[+b.dataset.h]; st.ex = t.split(" = ")[1].replace(/,/g, ""); justEq = true; keep(); paint(); });
    document.getElementById("qcFab")?.classList.toggle("has", !!st.ex);
  }
  window.QuizCalc = {calc, ko};
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", build); else build();
})();

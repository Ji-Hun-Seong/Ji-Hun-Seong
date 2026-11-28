/* 학습 기록 서버 동기화 — 마스터로드·펀드로드·자문패스 공용.
   기록은 원래 브라우저(localStorage)에만 있어서, 주소가 바뀌거나(대시보드 주소 ↔ 공개 /app/ ↔ 홈 화면 아이콘)
   사파리가 오래 안 쓴 사이트 저장소를 지우면 '주린이'부터 다시 시작했다.
   → 내가 정한 '동기화 코드'로 서버에 저장해 두고, 어느 주소·기기에서든 같은 코드면 기록을 이어 받는다.
   사용: <script src="../sync.js" data-app="masterroad" data-key="masterroad-v1"></script>  (앱 스크립트보다 먼저) */
(function () {
  "use strict";
  const me = document.currentScript, APP = me.dataset.app, KEY = me.dataset.key;
  const CODE_K = "study-sync-code", TS_K = "study-sync-ts:" + KEY;
  const ls = window.localStorage;
  const api = "../api/study";
  let code = ls.getItem(CODE_K) || "", status = code ? "연결됨" : "꺼짐", timer = null, busy = false;

  // 1) 앱이 기록을 저장할 때마다(같은 KEY) 시각을 남기고 2초 뒤 서버로 올림
  const rawSet = Storage.prototype.setItem;
  Storage.prototype.setItem = function (k, v) {
    rawSet.call(this, k, v);
    if (this === ls && k === KEY) { rawSet.call(ls, TS_K, String(Date.now())); schedule(); }
  };
  function schedule() { if (!code) return; clearTimeout(timer); timer = setTimeout(push, 2000); }
  async function push() {
    if (!code || busy) return; busy = true;
    if (!ls.getItem(TS_K)) rawSet.call(ls, TS_K, String(Date.now()));
    try {
      const r = await fetch(api, {method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({app: APP, k: code, ts: +(ls.getItem(TS_K) || 0), data: ls.getItem(KEY) || "{}"})});
      const j = await r.json(); status = j.ok ? "저장됨 " + new Date().toLocaleTimeString("ko-KR", {hour: "2-digit", minute: "2-digit"}) : (j.error || "저장 실패");
    } catch (e) { status = "오프라인 — 다음에 다시 올려요"; }
    busy = false; paint();
  }
  // 2) 열 때: 서버 기록이 더 최신이면(또는 이 브라우저 기록이 비었으면) 받아서 새로고침
  async function pull(force) {
    if (!code) return;
    try {
      const r = await fetch(`${api}?app=${encodeURIComponent(APP)}&k=${encodeURIComponent(code)}`, {cache: "no-store"});
      const j = await r.json();
      if (j.error) { status = j.error; return paint(); }
      const localTs = +(ls.getItem(TS_K) || 0), hasLocal = !!ls.getItem(KEY);
      // 동기화 전부터 쓰던 기록(시각 없음)과 서버 기록이 둘 다 있으면 → 더 많이 푼 쪽(기록이 긴 쪽)을 남김
      const serverWins = j.data && (force || !hasLocal || (localTs === 0 ? j.data.length >= (ls.getItem(KEY) || "").length : (j.ts || 0) > localTs));
      if (serverWins) {
        if (ls.getItem(KEY) === j.data) { rawSet.call(ls, TS_K, String(j.ts || Date.now())); status = "최신 상태"; return paint(); }
        rawSet.call(ls, KEY, j.data); rawSet.call(ls, TS_K, String(j.ts || Date.now()));
        sessionStorage.setItem("study-sync-restored", "1"); location.reload(); return;
      }
      if (hasLocal && (!j.data || localTs === 0 || localTs > (j.ts || 0))) return push();   // 서버에 없거나 이 기기가 더 최신 → 올림
      status = "최신 상태"; paint();
    } catch (e) { status = "서버에 연결 못 했어요"; paint(); }
  }

  /* ── 설정 시트 ── */
  const css = `#ssWrap{position:fixed;inset:0;z-index:70;background:rgba(0,0,0,.5);display:none;align-items:flex-end;justify-content:center}#ssWrap.on{display:flex}
#ss{width:100%;max-width:560px;background:var(--card);color:var(--txt);border-radius:24px 24px 0 0;padding:22px 20px calc(env(safe-area-inset-bottom) + 18px)}
#ss h3{margin:0 0 6px;font-size:19px}#ss p{margin:0 0 12px;color:var(--sub);font-size:14px;line-height:1.6}
#ss input{width:100%;height:50px;border:1.5px solid var(--line);border-radius:14px;background:var(--bg2,var(--chip));color:var(--txt);font:inherit;font-size:17px;font-weight:700;padding:0 14px;letter-spacing:.02em}
#ss .st{font-size:13px;color:var(--acc,var(--pri));font-weight:700;margin:8px 2px 0;min-height:18px}
#ss .bt{display:flex;gap:10px;margin-top:14px}#ss .bt button{flex:1;height:50px;border-radius:14px;border:0;font:inherit;font-weight:800;font-size:16px;cursor:pointer;background:var(--chip);color:var(--txt)}
#ss .bt .go{background:var(--acc,var(--pri));color:var(--ss-on,#04261b)}#ss .off{background:none;border:0;color:var(--sub);font:inherit;font-size:13px;margin-top:12px;text-decoration:underline;cursor:pointer}`;
  function open() {
    let w = document.getElementById("ssWrap");
    if (!w) {
      document.head.insertAdjacentHTML("beforeend", `<style>${css}</style>`);
      w = document.createElement("div"); w.id = "ssWrap";
      w.innerHTML = `<div id="ss"><h3>기록 동기화</h3><p>나만 아는 <b>동기화 코드</b>를 정하면 기록이 서버에 저장돼요. 다른 주소·기기·홈 화면 아이콘에서도 같은 코드를 넣으면 이어서 공부할 수 있어요. 세 앱(마스터로드·펀드로드·자문패스)에 같은 코드를 쓰면 돼요.</p>
        <input id="ssCode" autocomplete="off" autocapitalize="off" spellcheck="false" placeholder="예: jihun-study-0917 (6자 이상)"><div class="st" id="ssSt"></div>
        <div class="bt"><button data-x>닫기</button><button class="go" id="ssGo">연결하고 불러오기</button></div><button class="off" id="ssOff">이 기기에서 동기화 끄기</button></div>`;
      document.body.appendChild(w);
      if (!getComputedStyle(document.documentElement).getPropertyValue("--acc").trim()) w.style.setProperty("--ss-on", "#fff");
      w.onclick = e => { if (e.target === w || e.target.hasAttribute("data-x")) w.classList.remove("on"); };
      w.querySelector("#ssGo").onclick = async () => {
        const v = w.querySelector("#ssCode").value.trim();
        if (v.length < 6) { status = "6자 이상으로 정해 주세요"; return paint(); }
        code = v; rawSet.call(ls, CODE_K, v); status = "확인 중…"; paint(); await pull(false);
      };
      w.querySelector("#ssOff").onclick = () => { code = ""; ls.removeItem(CODE_K); status = "꺼짐"; paint(); };
    }
    w.querySelector("#ssCode").value = code; paint(); w.classList.add("on");
  }
  function paint() { const s = document.getElementById("ssSt"); if (s) s.textContent = code ? "상태: " + status : "아직 연결 안 됨 — 기록이 이 브라우저에만 있어요"; }

  window.StudySync = {open, push, pull, get code() { return code; }, get status() { return status; }};
  window.addEventListener("pagehide", () => { if (timer) { clearTimeout(timer); push(); } });
  if (code) document.readyState === "loading" ? document.addEventListener("DOMContentLoaded", () => pull(false)) : pull(false);
  if (sessionStorage.getItem("study-sync-restored")) { sessionStorage.removeItem("study-sync-restored"); setTimeout(() => { const t = document.getElementById("toast"); if (t && typeof t.classList !== "undefined") { t.textContent = "서버에 저장된 기록을 불러왔어요"; t.classList.add("on"); setTimeout(() => t.classList.remove("on"), 2200); } }, 400); }
})();

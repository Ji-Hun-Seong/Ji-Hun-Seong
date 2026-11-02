"""
chart_server.py — 종목 검색 → 볼린저 전략 차트 페이지

실행:  python3 chart_server.py              (기본 포트 8081)
접속:  아이폰 Tailscale 켜고  http://100.104.210.126:8081

환경변수(봇 .env와 공유): DART_API_KEY, KIS_APP_KEY, KIS_APP_SECRET(선택)
같은 폴더에 필요: bb_strategy.py, bb_chart.py, data_sources.py, foreign_flow.py
"""

from __future__ import annotations

import io
import os
import threading
import time

import pandas as pd
from flask import Flask, Response, jsonify, request

import data_sources as ds
from bb_chart import draw
from bb_strategy import Config, add_indicators, evaluate

app = Flask(__name__)
CFG = Config()
TTL = 300                       # 같은 종목은 5분 동안 캐시
_cache: dict[str, tuple[float, dict]] = {}
_lock = threading.Lock()


def analyze(item: dict) -> dict:
    key = item["code"]
    with _lock:
        hit = _cache.get(key)
        if hit and time.time() - hit[0] < TTL:
            return hit[1]
    us = bool(item.get("us"))
    df = ds.get_ohlcv(item["code"], us=us)
    buybacks = [] if us else ds.get_buybacks(item.get("corp_code"))
    flows = None if us else ds.get_flows(item["code"])

    cfg = CFG
    if us:   # 미국 종목엔 자사주 공시·외국인 수급 개념이 없음 → 볼린저만
        cfg = Config(require=("bollinger",))
    r = evaluate(df, buybacks, flows, cfg)
    d = add_indicators(df, cfg)
    last, prev = d.iloc[-1], d.iloc[-2]

    buf = io.BytesIO()
    title = f"{item['name']} ({item['code']})"
    chart = draw(df, buybacks, flows, title=title, path=buf, cfg=cfg,
                 last_n=120, figsize=(6.4, 9.6), font_scale=1.45)   # 휴대폰 세로 화면용

    checks = []
    labels = {"buyback": "자사주 공시", "bollinger": "볼린저", "foreign": "외국인 수급"}
    for k, (ok, msg) in r["checks"].items():
        if k not in cfg.require:
            continue
        if k == "foreign" and flows is None:
            msg = "수급 데이터 없음 (KIS 키 미설정)"
        checks.append({"key": k, "label": labels[k], "ok": bool(ok), "msg": msg})

    out = {
        "name": item["name"], "code": item["code"], "us": us,
        "currency": df.attrs.get("currency", ""),
        "asof": f"{d.index[-1]:%Y-%m-%d}",
        "close": float(last["close"]), "chg": float(last["close"] / prev["close"] - 1),
        "pctb": float(last["pctb"]), "bw": float(last["bw"]), "mfi": float(last["mfi"]),
        "buy": bool(r["buy"]), "checks": checks,
        "buy_dates": [f"{t:%Y-%m-%d}" for t in chart["buy_dates"]][-5:],
        "buybacks": sorted(buybacks, key=lambda e: e["date"], reverse=True)[:8],
        "png": buf.getvalue(),
    }
    with _lock:
        _cache[key] = (time.time(), out)
    return out


@app.get("/api/search")
def api_search():
    return jsonify([{k: v for k, v in c.items() if k != "corp_code"} | {"corp_code": c.get("corp_code")}
                    for c in ds.search(request.args.get("q", ""))])


@app.get("/api/analyze")
def api_analyze():
    q = request.args.get("q", "")
    hits = ds.search(q, limit=1)
    if not hits:
        return jsonify({"error": f"'{q}' 종목을 찾지 못했습니다"}), 404
    try:
        a = analyze(hits[0])
    except LookupError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        return jsonify({"error": f"데이터 오류: {e}"}), 502
    return jsonify({k: v for k, v in a.items() if k != "png"} | {"chart": f"/chart/{a['code']}.png?t={int(time.time())}"})


@app.get("/chart/<code>.png")
def chart_png(code):
    hit = _cache.get(code)
    if not hit:
        items = ds.search(code, limit=1)
        if not items:
            return "not found", 404
        hit = (0, analyze(items[0]))
    return Response(hit[1]["png"], mimetype="image/png", headers={"Cache-Control": "max-age=300"})


@app.get("/")
def index():
    return Response(PAGE, mimetype="text/html")


PAGE = """<!doctype html>
<html lang="ko"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="apple-mobile-web-app-capable" content="yes">
<title>종목 차트</title>
<style>
:root{--bg:#0f1520;--card:#1a2230;--fg:#e5e7eb;--mut:#9ca3af;--ok:#22c55e;--no:#ef4444;--acc:#60a5fa;--warn:#f59e0b}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font-family:-apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo","Noto Sans KR",sans-serif;padding:max(16px,env(safe-area-inset-top)) 16px 40px}
h1{font-size:26px;margin:8px 4px 16px}
.search{position:relative}
.search input{width:100%;padding:15px 16px;border-radius:14px;border:1px solid #2b3545;background:var(--card);color:var(--fg);font-size:17px;outline:none}
.search input:focus{border-color:var(--acc)}
.sug{position:absolute;left:0;right:0;top:58px;background:var(--card);border:1px solid #2b3545;border-radius:12px;overflow:hidden;z-index:5;display:none}
.sug div{padding:12px 16px;border-bottom:1px solid #222b3a;display:flex;justify-content:space-between}
.sug div:active,.sug div.on{background:#243044}.sug small{color:var(--mut)}
.card{background:var(--card);border-radius:18px;padding:18px;margin-top:14px}
.head{display:flex;justify-content:space-between;align-items:flex-end;gap:8px}
.name{font-size:21px;font-weight:700}.code{color:var(--mut);font-size:14px;margin-top:2px}
.px{font-size:24px;font-weight:700;text-align:right}.chg{font-size:14px;text-align:right}
.up{color:#f87171}.dn{color:#60a5fa}
.verdict{margin-top:14px;padding:14px;border-radius:12px;font-weight:700;font-size:17px;text-align:center}
.verdict.buy{background:rgba(34,197,94,.15);color:var(--ok)}.verdict.wait{background:#222b3a;color:var(--mut)}
.chk{display:flex;gap:10px;padding:11px 0;border-bottom:1px solid #222b3a;font-size:15px}.chk:last-child{border:0}
.chk b{min-width:112px;white-space:nowrap}.chk span{color:var(--mut)}
.metrics{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-top:12px}
.metrics div{background:#141b27;border-radius:10px;padding:10px;text-align:center}
.metrics small{display:block;color:var(--mut);font-size:12px}.metrics b{font-size:17px}
img.chart{width:100%;border-radius:12px;margin-top:4px;display:block}
.ev{display:flex;justify-content:space-between;padding:10px 0;border-bottom:1px solid #222b3a;font-size:14px}.ev:last-child{border:0}
.ev a{color:var(--acc);text-decoration:none}.t{font-size:17px;font-weight:700;margin-bottom:6px}
.muted{color:var(--mut);font-size:13px;line-height:1.5}
.err{color:var(--no)}.spin{color:var(--mut);text-align:center;padding:30px}
.chips{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}.chips button{background:#1f2937;color:var(--fg);border:0;border-radius:999px;padding:8px 14px;font-size:14px}
</style></head><body>
<h1>종목 차트</h1>
<div class="search">
  <input id="q" placeholder="종목명·코드·미국 티커 (예: 삼성전자, 005930, AAPL)" autocomplete="off" enterkeyhint="search">
  <div class="sug" id="sug"></div>
</div>
<div class="chips" id="recent"></div>
<div id="out"></div>
<script>
const $=s=>document.querySelector(s), q=$('#q'), sug=$('#sug'), out=$('#out');
let timer, items=[], sel=-1;
const fmt=(v,cur)=>cur==='KRW'?Math.round(v).toLocaleString()+'원':(cur==='USD'?'$':'')+v.toLocaleString(undefined,{maximumFractionDigits:2});
const esc=s=>String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
function recent(){let r=[];try{r=JSON.parse(localStorage.getItem('recent')||'[]')}catch(e){}return r}
function saveRecent(n){let r=recent().filter(x=>x!==n);r.unshift(n);r=r.slice(0,6);try{localStorage.setItem('recent',JSON.stringify(r))}catch(e){}drawRecent()}
function drawRecent(){$('#recent').innerHTML=recent().map(n=>`<button>${esc(n)}</button>`).join('');
  $('#recent').querySelectorAll('button').forEach(b=>b.onclick=()=>go(b.textContent))}
q.addEventListener('input',()=>{clearTimeout(timer);const v=q.value.trim();if(!v){sug.style.display='none';return}
  timer=setTimeout(async()=>{items=await (await fetch('/api/search?q='+encodeURIComponent(v))).json();sel=-1;
    sug.innerHTML=items.map((c,i)=>`<div data-i="${i}">${esc(c.name)}<small>${esc(c.code)}</small></div>`).join('');
    sug.style.display=items.length?'block':'none';
    sug.querySelectorAll('div').forEach(d=>d.onclick=()=>go(items[d.dataset.i].code,items[d.dataset.i].name));},200)});
q.addEventListener('keydown',e=>{const ds=sug.querySelectorAll('div');
  if(e.key==='ArrowDown'||e.key==='ArrowUp'){sel=(sel+(e.key==='ArrowDown'?1:-1)+ds.length)%ds.length;ds.forEach((d,i)=>d.classList.toggle('on',i===sel));e.preventDefault()}
  if(e.key==='Enter'){e.preventDefault();if(sel>=0&&items[sel])go(items[sel].code,items[sel].name);else go(q.value)}});
document.addEventListener('click',e=>{if(!e.target.closest('.search'))sug.style.display='none'});
async function go(code,name){sug.style.display='none';q.blur();if(!code.trim())return;
  out.innerHTML='<div class="spin">차트 그리는 중…</div>';
  history.replaceState(null,'','?q='+encodeURIComponent(code));
  try{const r=await fetch('/api/analyze?q='+encodeURIComponent(code));const a=await r.json();
    if(a.error){out.innerHTML=`<div class="card err">${esc(a.error)}</div>`;return}
    saveRecent(a.name);q.value=a.name;render(a)}catch(e){out.innerHTML=`<div class="card err">불러오기 실패: ${esc(e)}</div>`}}
function render(a){
  const up=a.chg>=0;
  const checks=a.checks.map(c=>`<div class="chk"><b>${c.ok?'✅':'❌'} ${c.label}</b><span>${esc(c.msg)}</span></div>`).join('');
  const evs=a.buybacks.length?a.buybacks.map(e=>`<div class="ev"><span>${e.date} · ${esc(e.type)}</span><a href="${e.url}" target="_blank">원문</a></div>`).join('')
    :`<div class="muted">${a.us?'미국 종목은 자사주 공시를 조회하지 않습니다':'최근 2년 자사주 공시 없음'}</div>`;
  out.innerHTML=`
  <div class="card">
    <div class="head"><div><div class="name">${esc(a.name)}</div><div class="code">${esc(a.code)} · ${a.asof} 종가</div></div>
      <div><div class="px">${fmt(a.close,a.currency)}</div><div class="chg ${up?'up':'dn'}">${up?'▲':'▼'} ${(Math.abs(a.chg)*100).toFixed(2)}%</div></div></div>
    <div class="verdict ${a.buy?'buy':'wait'}">${a.buy?'매수 조건 충족':'매수 조건 미충족 — 대기'}</div>
    <div style="margin-top:6px">${checks}</div>
    <div class="metrics"><div><small>%b</small><b>${a.pctb.toFixed(2)}</b></div>
      <div><small>BandWidth</small><b>${a.bw.toFixed(3)}</b></div><div><small>MFI</small><b>${a.mfi.toFixed(0)}</b></div></div>
  </div>
  <div class="card" style="padding:10px"><img class="chart" src="${a.chart}" alt="차트"></div>
  <div class="card"><div class="t">자사주 공시</div>${evs}</div>
  <div class="card"><div class="t">최근 매수 신호일</div><div class="muted">${a.buy_dates.length?a.buy_dates.join(' · '):'최근 160영업일 동안 없음'}</div>
    <div class="muted" style="margin-top:10px">초록 ▲ = 세 조건 모두 충족 · 파란 ○ = 볼린저만 충족 · 점선 = 자사주 공시</div></div>`;
}
drawRecent();
const p=new URLSearchParams(location.search).get('q'); if(p) go(p);
</script></body></html>"""


if __name__ == "__main__":
    host = os.environ.get("CHART_HOST", "0.0.0.0")
    port = int(os.environ.get("CHART_PORT", "8081"))
    app.run(host=host, port=port, threaded=True)

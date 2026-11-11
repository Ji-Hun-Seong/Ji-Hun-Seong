/* ─────────────────────────────────────────────────────────────
   🎨 이모지 → 세련된 선 아이콘 (Lucide 스타일, 24×24 · 선 굵기 2 · 글자색을 따라감)
   화면에 그려지는 모든 글자에서 이모지를 찾아 SVG 아이콘으로 바꿔 줌 (나중에 생기는 내용도 자동)
   · 상태 점(🟢🟡🔴⚪🟠🔵) → 색 점   · 국기(🇰🇷🇺🇸…) → KR·US 작은 배지
   · 끄려면: localStorage.setItem("emoji", "1") 후 새로고침
   아이콘 모양 출처: Lucide (ISC 라이선스, lucide.dev)
   ───────────────────────────────────────────────────────────── */
(function () {
  try { if (localStorage.getItem("emoji") === "1") return; } catch (e) {}

  const P = {   // 아이콘 이름 → SVG 안쪽 (path·circle·rect)
    gem: '<path d="M6 3h12l4 6-10 13L2 9Z"/><path d="M11 3 8 9l4 13 4-13-3-6"/><path d="M2 9h20"/>',
    rocket: '<path d="M4.5 16.5c-1.5 1.26-2 5-2 5s3.74-.5 5-2c.71-.84.7-2.13-.09-2.91a2.18 2.18 0 0 0-2.91-.09z"/><path d="m12 15-3-3a22 22 0 0 1 2-3.95A12.88 12.88 0 0 1 22 2c0 2.72-.78 7.5-6 11a22.35 22.35 0 0 1-4 2z"/><path d="M9 12H4s.55-3.03 2-4c1.62-1.08 5 0 5 0"/><path d="M12 15v5s3.03-.55 4-2c1.08-1.62 0-5 0-5"/>',
    landmark: '<path d="M3 22h18"/><path d="M6 18v-7"/><path d="M10 18v-7"/><path d="M14 18v-7"/><path d="M18 18v-7"/><path d="M12 2 20 7H4z"/>',
    alert: '<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/><path d="M12 9v4"/><path d="M12 17h.01"/>',
    leaf: '<path d="M11 20A7 7 0 0 1 9.8 6.1C15.5 5 17 4.48 19 2c1 2 2 4.18 2 8 0 5.5-4.78 10-10 10Z"/><path d="M2 21c0-3 1.85-5.36 5.08-6C9.5 14.52 12 13 13 12"/>',
    ban: '<circle cx="12" cy="12" r="10"/><path d="m4.9 4.9 14.2 14.2"/>',
    zap: '<path d="M4 14a1 1 0 0 1-.78-1.63l9.9-10.2a.5.5 0 0 1 .86.46l-1.92 6.02A1 1 0 0 0 13 10h7a1 1 0 0 1 .78 1.63l-9.9 10.2a.5.5 0 0 1-.86-.46l1.92-6.02A1 1 0 0 0 11 14z"/>',
    check: '<path d="M20 6 9 17l-5-5"/>',
    pin: '<path d="M12 17v5"/><path d="M9 10.76a2 2 0 0 1-1.11 1.79l-1.78.9A2 2 0 0 0 5 15.24V16a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-.76a2 2 0 0 0-1.11-1.79l-1.78-.9A2 2 0 0 1 15 10.76V7a1 1 0 0 1 1-1 2 2 0 0 0 0-4H8a2 2 0 0 0 0 4 1 1 0 0 1 1 1z"/>',
    building: '<rect x="4" y="2" width="16" height="20" rx="2"/><path d="M9 22v-4h6v4"/><path d="M8 6h.01M12 6h.01M16 6h.01M8 10h.01M12 10h.01M16 10h.01M8 14h.01M12 14h.01M16 14h.01"/>',
    bank: '<path d="M3 22h18"/><path d="M5 18v-7M9.5 18v-7M14.5 18v-7M19 18v-7"/><path d="M2 11 12 4l10 7"/><circle cx="12" cy="8" r="1"/>',
    news: '<path d="M15 18h-5"/><path d="M18 14h-8"/><path d="M4 22h16a2 2 0 0 0 2-2V4a2 2 0 0 0-2-2H8a2 2 0 0 0-2 2v16a2 2 0 0 1-4 0v-9a2 2 0 0 1 2-2h2"/><rect x="10" y="6" width="8" height="4" rx="1"/>',
    up: '<path d="M22 7 13.5 15.5 8.5 10.5 2 17"/><path d="M16 7h6v6"/>',
    down: '<path d="M22 17 13.5 8.5 8.5 13.5 2 7"/><path d="M16 17h6v-6"/>',
    book: '<path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H20v20H6.5a2.5 2.5 0 0 1 0-5H20"/>',
    user: '<circle cx="12" cy="8" r="5"/><path d="M20 21a8 8 0 0 0-16 0"/>',
    scale: '<path d="m16 16 3-8 3 8c-.87.65-1.92 1-3 1s-2.13-.35-3-1Z"/><path d="m2 16 3-8 3 8c-.87.65-1.92 1-3 1s-2.13-.35-3-1Z"/><path d="M7 21h10"/><path d="M12 3v18"/><path d="M3 7h2c2 0 5-1 7-2 2 1 5 2 7 2h2"/>',
    flask: '<path d="M10 2v7.31"/><path d="M14 9.3V2"/><path d="M8.5 2h7"/><path d="M14 9.3a6.5 6.5 0 1 1-4 0"/>',
    eye: '<path d="M2.06 12.35a1 1 0 0 1 0-.7 10.75 10.75 0 0 1 19.88 0 1 1 0 0 1 0 .7 10.75 10.75 0 0 1-19.88 0"/><circle cx="12" cy="12" r="3"/>',
    x: '<path d="M18 6 6 18"/><path d="m6 6 12 12"/>',
    chart: '<path d="M3 3v16a2 2 0 0 0 2 2h16"/><path d="M18 17V9"/><path d="M13 17V5"/><path d="M8 17v-3"/>',
    file: '<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/><path d="M14 2v4a2 2 0 0 0 2 2h4"/><path d="M16 13H8"/><path d="M16 17H8"/>',
    bulb: '<path d="M15 14c.2-1 .7-1.7 1.5-2.5 1-.9 1.5-2.2 1.5-3.5A6 6 0 0 0 6 8c0 1 .2 2.2 1.5 3.5.7.7 1.3 1.5 1.5 2.5"/><path d="M9 18h6"/><path d="M10 22h4"/>',
    box: '<path d="M11 21.73a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73z"/><path d="M12 22V12"/><path d="m3.3 7 8.7 5 8.7-5"/>',
    target: '<circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/>',
    sprout: '<path d="M7 20h10"/><path d="M10 20c5.5-2.5.8-6.4 3-10"/><path d="M9.5 9.4c1.1.8 1.8 2.2 2.3 3.7-2 .4-3.5.4-4.8-.3-1.2-.6-2.3-1.9-3-4.2 2.8-.5 4.4 0 5.5.8z"/><path d="M14.1 6a7 7 0 0 0-1.1 4c1.9-.1 3.3-.6 4.3-1.4 1-1 1.6-2.3 1.7-4.6-2.7.1-4 1-4.9 2z"/>',
    bot: '<path d="M12 8V4H8"/><rect x="4" y="8" width="16" height="12" rx="2"/><path d="M2 14h2"/><path d="M20 14h2"/><path d="M15 13v2"/><path d="M9 13v2"/>',
    contrast: '<circle cx="12" cy="12" r="10"/><path d="M12 18a6 6 0 0 0 0-12v12z"/>',
    moon: '<path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/>',
    sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41"/>',
    lock: '<rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>',
    shield: '<path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/>',
    search: '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>',
    globe: '<circle cx="12" cy="12" r="10"/><path d="M12 2a14.5 14.5 0 0 0 0 20 14.5 14.5 0 0 0 0-20"/><path d="M2 12h20"/>',
    flame: '<path d="M8.5 14.5A2.5 2.5 0 0 0 11 12c0-1.38-.5-2-1-3-1.07-2.14-.22-4.05 2-6 .5 2.5 2 4.9 4 6.5 2 1.6 3 3.5 3 5.5a7 7 0 1 1-14 0c0-1.15.43-2.29 1-3a2.5 2.5 0 0 0 2.5 2.5z"/>',
    pie: '<path d="M21 12c.55 0 1-.45.98-1a10 10 0 0 0-9-9c-.55-.02-1 .43-1 .98v8a1 1 0 0 0 1 1z"/><path d="M21.21 15.89A10 10 0 1 1 8 2.83"/>',
    compass: '<circle cx="12" cy="12" r="10"/><path d="m16.24 7.76-1.8 5.4a2 2 0 0 1-1.27 1.27l-5.4 1.8 1.8-5.4a2 2 0 0 1 1.28-1.28z"/>',
    refresh: '<path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/><path d="M8 16H3v5"/>',
    hourglass: '<path d="M5 22h14"/><path d="M5 2h14"/><path d="M17 22v-4.17a2 2 0 0 0-.59-1.42L12 12l-4.41 4.41A2 2 0 0 0 7 17.83V22"/><path d="M7 2v4.17a2 2 0 0 0 .59 1.42L12 12l4.41-4.41A2 2 0 0 0 17 6.17V2"/>',
    coins: '<circle cx="8" cy="8" r="6"/><path d="M18.09 10.37A6 6 0 1 1 10.34 18"/><path d="M7 6h1v4"/><path d="m16.71 13.88.7.71-2.82 2.82"/>',
    bell: '<path d="M10.27 21a2 2 0 0 0 3.46 0"/><path d="M3.26 15.33A1 1 0 0 0 4 17h16a1 1 0 0 0 .74-1.67C19.41 13.96 18 12.5 18 8A6 6 0 0 0 6 8c0 4.5-1.41 5.96-2.74 7.33"/>',
    trophy: '<path d="M6 9H4.5a2.5 2.5 0 0 1 0-5H6"/><path d="M18 9h1.5a2.5 2.5 0 0 0 0-5H18"/><path d="M4 22h16"/><path d="M18 2H6v7a6 6 0 0 0 12 0V2Z"/><path d="M12 15v7"/>',
    sparkle: '<path d="M12 3l1.9 5.8L20 11l-6.1 2.2L12 19l-1.9-5.8L4 11l6.1-2.2z"/>',
    thumbup: '<path d="M7 10v12"/><path d="M15 5.88 14 10h5.83a2 2 0 0 1 1.92 2.56l-2.33 8A2 2 0 0 1 17.5 22H4a2 2 0 0 1-2-2v-8a2 2 0 0 1 2-2h2.76a2 2 0 0 0 1.79-1.11L12 2a3.13 3.13 0 0 1 3 3.88Z"/>',
    ruler: '<path d="M21.3 15.3a2.4 2.4 0 0 1 0 3.4l-2.6 2.6a2.4 2.4 0 0 1-3.4 0L2.7 8.7a2.41 2.41 0 0 1 0-3.4l2.6-2.6a2.41 2.41 0 0 1 3.4 0Z"/><path d="m14.5 12.5 2-2M11.5 9.5l2-2M8.5 6.5l2-2M17.5 15.5l2-2"/>',
    db: '<ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M3 5v14a9 3 0 0 0 18 0V5"/><path d="M3 12a9 3 0 0 0 18 0"/>',
    radio: '<path d="M4.9 19.1C1 15.2 1 8.8 4.9 4.9"/><path d="M7.8 16.2c-2.3-2.3-2.3-6.1 0-8.5"/><circle cx="12" cy="12" r="2"/><path d="M16.2 7.8c2.3 2.3 2.3 6.1 0 8.5"/><path d="M19.1 4.9C23 8.8 23 15.1 19.1 19"/>',
    pointer: '<path d="M22 14a8 8 0 0 1-8 8"/><path d="M18 11v-1a2 2 0 0 0-2-2a2 2 0 0 0-2 2"/><path d="M14 10V9a2 2 0 0 0-2-2a2 2 0 0 0-2 2v1"/><path d="M10 9.5V4a2 2 0 0 0-2-2a2 2 0 0 0-2 2v10"/><path d="M18 11a2 2 0 1 1 4 0v3a8 8 0 0 1-8 8h-2c-2.8 0-4.5-.86-5.99-2.34l-3.6-3.6a2 2 0 0 1 2.83-2.82L7 15"/>',
    brain: '<path d="M12 5a3 3 0 1 0-5.997.125 4 4 0 0 0-2.526 5.77 4 4 0 0 0 .556 6.588A4 4 0 1 0 12 18Z"/><path d="M12 5a3 3 0 1 1 5.997.125 4 4 0 0 1 2.526 5.77 4 4 0 0 1-.556 6.588A4 4 0 1 1 12 18Z"/>',
    megaphone: '<path d="m3 11 18-5v12L3 14v-3z"/><path d="M11.6 16.8a3 3 0 1 1-5.8-1.6"/>',
    square: '<rect x="3" y="3" width="18" height="18" rx="2"/>',
    home: '<path d="M3 10.5 12 3l9 7.5"/><path d="M5 9v10.5a1.5 1.5 0 0 0 1.5 1.5H10v-6h4v6h3.5a1.5 1.5 0 0 0 1.5-1.5V9"/>',
    wallet: '<path d="M19 7V5.5A1.5 1.5 0 0 0 17.5 4H5a2 2 0 0 0 0 4h14a1 1 0 0 1 1 1v3"/><path d="M3 6v12a2 2 0 0 0 2 2h14a1 1 0 0 0 1-1v-3"/><path d="M21 12v4h-4a2 2 0 0 1 0-4z"/>',
    basket: '<path d="m15 11-1 9"/><path d="m19 11-4-7"/><path d="M2 11h20"/><path d="m3.5 11 1.6 7.4a2 2 0 0 0 2 1.6h9.8a2 2 0 0 0 2-1.6l1.7-7.4"/><path d="M4.5 15.5h15"/><path d="m5 11 4-7"/><path d="m9 11 1 9"/>',
    factory: '<path d="M2 20a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V8l-7 5V8l-7 5V4a2 2 0 0 0-2-2H4a2 2 0 0 0-2 2Z"/><path d="M17 18h1"/><path d="M12 18h1"/><path d="M7 18h1"/>',
    exchange: '<path d="M8 3 4 7l4 4"/><path d="M4 7h16"/><path d="m16 21 4-4-4-4"/><path d="M20 17H4"/>',
    mouse: '<rect x="5" y="2" width="14" height="20" rx="7"/><path d="M12 6v4"/>',
    smile: '<circle cx="12" cy="12" r="10"/><path d="M8 14s1.5 2 4 2 4-2 4-2"/><path d="M9 9h.01"/><path d="M15 9h.01"/>',
    monitor: '<rect x="2" y="3" width="20" height="14" rx="2"/><path d="M8 21h8"/><path d="M12 17v4"/>',
    cap: '<path d="M21.42 10.92a1 1 0 0 0-.02-1.84L12.83 5.18a2 2 0 0 0-1.66 0L2.6 9.08a1 1 0 0 0 0 1.83l8.57 3.91a2 2 0 0 0 1.66 0z"/><path d="M22 10v6"/><path d="M6 12.5V16a6 3 0 0 0 12 0v-3.5"/>',
    star: '<path d="m12 2 3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01z"/>',
    receipt: '<path d="M4 2v20l2-1 2 1 2-1 2 1 2-1 2 1 2-1 2 1V2l-2 1-2-1-2 1-2-1-2 1-2-1-2 1Z"/><path d="M8 8h8"/><path d="M8 12h8"/><path d="M8 16h5"/>',
    clock: '<circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>',
    calendar: '<path d="M8 2v4"/><path d="M16 2v4"/><rect x="3" y="4" width="18" height="18" rx="2"/><path d="M3 10h18"/>',
    hash: '<path d="M4 9h16"/><path d="M4 15h16"/><path d="M10 3 8 21"/><path d="m16 3-2 18"/>',
  };
  const TONE = {star: "var(--warn)", alert: "var(--warn)", ban: "var(--up)", check: "var(--ok)", x: "var(--up)", flame: "#f97316", sparkle: "var(--warn)", trophy: "var(--warn)"};

  // 이모지 → [아이콘, 회전(선택)]
  const MAP = {
    "💎": "gem", "🚀": "rocket", "🏛️": "landmark", "🏛": "landmark", "⚠️": "alert", "⚠": "alert", "🧘": "leaf",
    "🚫": "ban", "⛔": "ban", "⚡": "zap", "✅": "check", "✓": "check", "✔": "check", "✔️": "check",
    "📌": "pin", "🏢": "building", "🏰": "building", "🏦": "bank", "📰": "news", "📈": "up", "↗": "up", "↗️": "up", "🔺": "up",
    "🔻": "down", "↘️": "down", "↘": "down", "📒": "book", "📘": "book", "📖": "book", "📑": "file", "📜": "file", "📄": "file",
    "📝": "file", "📋": "file", "👤": "user", "🧑‍💼": "user", "⚖️": "scale", "⚖": "scale", "🧪": "flask", "👀": "eye",
    "🔭": "eye", "❌": "x", "✕": "x", "📊": "chart", "💡": "bulb", "📦": "box", "🎯": "target", "🌱": "sprout",
    "🌳": "sprout", "🤖": "bot", "🧠": "brain", "🌓": "contrast", "🌙": "moon", "☀️": "sun", "☀": "sun", "🌅": "sun",
    "🔒": "lock", "🛡️": "shield", "🛡": "shield", "🔎": "search", "🔍": "search", "🌍": "globe", "🔥": "flame",
    "🚨": "flame", "🧩": "pie", "🧭": "compass", "🔄": "refresh", "🔁": "refresh", "⏳": "hourglass", "💸": "coins",
    "💰": "coins", "🪙": "coins", "🔔": "bell", "🏆": "trophy", "🦅": "trophy", "✨": "sparkle", "👍": "thumbup",
    "👎": "thumbdown", "📏": "ruler", "🗄️": "db", "🗄": "db", "📡": "radio", "👆": "pointer", "📢": "megaphone", "☐": "square", "⌂": "home", "◎": "wallet",
    "🧺": "basket", "🏭": "factory", "💱": "exchange", "🖱️": "mouse", "🖱": "mouse", "🙂": "smile", "🖥️": "monitor", "🖥": "monitor",
    "🎓": "cap", "📚": "book", "🌐": "globe", "🚧": "alert", "🐢": "hourglass", "⭐": "star", "🧾": "receipt", "⏰": "clock",
    "🏅": "trophy", "🔢": "hash", "📅": "calendar", "🗓️": "calendar", "🗓": "calendar",
  };
  const DOT = {"🟢": "var(--ok)", "🟡": "var(--warn)", "🔴": "var(--up)", "⚪": "var(--sub)", "🟠": "#f97316", "🔵": "var(--blue)", "🔸": "#f97316"};
  const FLAG = {"🇰🇷": "KR", "🇺🇸": "US", "🇪🇺": "EU", "🇨🇳": "CN", "🇯🇵": "JP"};

  const css = document.createElement("style");
  css.textContent = `.ic{width:1.05em;height:1.05em;vertical-align:-0.16em;flex:0 0 auto;display:inline-block}
.ic-dot{display:inline-block;width:.62em;height:.62em;border-radius:50%;vertical-align:.05em;margin:0 .1em}
.ic-flag{display:inline-block;font:700 .62em/1 -apple-system,BlinkMacSystemFont,sans-serif;letter-spacing:.04em;padding:.28em .42em;border-radius:.4em;
  border:1px solid currentColor;opacity:.75;vertical-align:.12em}`;
  document.head.appendChild(css);

  const svg = (name) => {
    const flip = name === "thumbdown";
    const body = P[flip ? "thumbup" : name];
    const tone = TONE[name];
    return `<svg class="ic" viewBox="0 0 24 24" fill="none" stroke="${tone || "currentColor"}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${flip ? `<g transform="rotate(180 12 12)">${body}</g>` : body}</svg>`;
  };
  const keys = Object.keys(MAP).concat(Object.keys(DOT), Object.keys(FLAG)).sort((a, b) => b.length - a.length);
  const ANYFLAG = "(?:\\uD83C[\\uDDE6-\\uDDFF]){2}";   // 목록에 없는 국기도 두 글자 배지로 (🇹🇼 → TW)
  const RX = new RegExp("(" + keys.map(k => k.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|") + "|" + ANYFLAG + ")️?", "g");
  const code = (k) => String.fromCharCode(k.codePointAt(0) - 0x1F1E6 + 65, k.codePointAt(2) - 0x1F1E6 + 65);
  const html = (k) => DOT[k] ? `<span class="ic-dot" style="background:${DOT[k]}"></span>`
    : FLAG[k] ? `<span class="ic-flag">${FLAG[k]}</span>` : MAP[k] ? svg(MAP[k]) : `<span class="ic-flag">${code(k)}</span>`;
  const SKIP = {SCRIPT: 1, STYLE: 1, TEXTAREA: 1, INPUT: 1, OPTION: 1, SELECT: 1, svg: 1, SVG: 1, TITLE: 1, CANVAS: 1};

  function fix(root) {
    if (!root) return;
    const w = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
      acceptNode: n => {
        for (let p = n.parentNode; p && p !== root.parentNode; p = p.parentNode) if (SKIP[p.nodeName]) return NodeFilter.FILTER_REJECT;
        RX.lastIndex = 0;
        return RX.test(n.nodeValue) ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_SKIP;
      }
    });
    const hits = [];
    while (w.nextNode()) hits.push(w.currentNode);
    for (const n of hits) {
      const span = document.createElement("span");
      span.innerHTML = n.nodeValue.replace(/[&<>]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;"}[c])).replace(RX, (m, k) => html(k));
      const frag = document.createDocumentFragment();
      while (span.firstChild) frag.appendChild(span.firstChild);
      n.parentNode && n.parentNode.replaceChild(frag, n);
    }
  }

  let queued = false;
  const pending = new Set();
  const mo = new MutationObserver(ms => {
    for (const m of ms) {
      if (m.type === "characterData") pending.add(m.target.parentNode);
      else m.addedNodes.forEach(n => pending.add(n.nodeType === 3 ? n.parentNode : n));
    }
    if (!queued) { queued = true; requestAnimationFrame(() => {
      queued = false; mo.disconnect();
      pending.forEach(n => n && n.isConnected && fix(n)); pending.clear();
      mo.observe(document.body, {childList: true, subtree: true, characterData: true});
    }); }
  });
  const start = () => { fix(document.body); mo.observe(document.body, {childList: true, subtree: true, characterData: true}); };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start); else start();
  window.iconize = fix;
})();

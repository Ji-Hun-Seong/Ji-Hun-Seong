<h1 align="center">
  <span style="background: linear-gradient(to right, #ff7e5f, #feb47b); -webkit-background-clip: text; color: transparent;">Jihun's GITHUB</span>
</h1>

<p align="center">
  <img src="https://img.shields.io/badge/Profile-Awesome-blueviolet?style=flat-square&logo=github" alt="Profile Badge">
</p>

<p align="center">
  <em>Exploring the intersection of code, creativity, and community.</em>
</p>

---

## 🌟 About Me

Hello! I'm Jihun, a passionate IT engineer with a strong focus on Python-based data engineering and IT infrastructure.

- 🏢 **Current Work:** IT Engineer at Shinhan Fund Partners.
- 🏢 **Previous Experience:** Data Engineer at Douzone Bizon.
- 🌱 **Learning:** Advancing in data pipelines, ETL processes, and cloud-based solutions.
- 💬 **Ask Me About:** Python, data engineering, and system optimization.

---

## 🚀 Technologies & Tools

```text
Programming: Python, SQL, Bash
Data Engineering: Pandas, PySpark, Airflow
Cloud Platforms: AWS, GCP
Tools: Docker, Git, Jenkins
```

---

## 📊 GitHub Stats

<p align="center">
  <img src="https://github-readme-stats.vercel.app/api?username=Ji-Hun-Seong&show_icons=true&theme=radical" alt="Jihun's GitHub Stats">
</p>

<p align="center">
  <img src="https://github-readme-streak-stats.herokuapp.com/?user=Ji-Hun-Seong&theme=radical" alt="Jihun's GitHub Streak">
</p>

---

## ✨ Highlights

### 📈 Featured Project: 지훈의 투자 연구실

> 퇴근 후에 혼자 설계·운영하는 개인 투자 자동화 시스템 — 공시·시세 수집, 대가 기준 종목 채점, 급등주 연구, 소액 자동 매매까지.
> 숫자는 표본 수와 함께 적고, 세운 가설은 매일 채점합니다.

**👉 [데모 페이지 보기](https://claude.ai/artifact/Kw7nRSL8g6yHCzux18S23b)** — 앱 화면·구조·실제 기록을 한 페이지에

| 모듈 | 하는 일 | 폴더 |
|---|---|---|
| 🏛️ 발굴 · 대가 채점 | 그레이엄·버핏·린치·피셔 등 10인의 원전 기준을 숫자로 옮겨 한국·해외 종목 채점 (DART 최대 10년 재무) | [`toss-bot/chartpage`](toss-bot/chartpage) |
| 🚀 급등주 연구실 | 장중 20분마다 +10% 종목 기록 → 공시·뉴스로 재료 판정 → 가설 → 장 마감·다음 날 채점 | [`surge-study`](surge-study) |
| 🤖 자동 매매 봇 | 한국 자사주 공시 스윙 · 미국 나스닥 변동성 맞춤 레버리지 (가상 모드 기본, 실전 전환은 서버 명령만) | [`toss-bot`](toss-bot) |
| 💎 매매일지 DNA 가치주 | 실제 매매 기록에서 뽑은 성향으로 저PBR·배당 종목 순위 | [`value-bot`](value-bot) |
| 🧾 대가 포트폴리오 추적 | SEC 13F로 애크먼 등 보유 변화 정리·알림 | [`13f`](13f) |

**구조**

```text
DART · KRX · 네이버 · 야후 · SEC
        │
        ▼
GitHub Actions (26개 작업, 20분~주 단위 수집) ──▶ 저장소 CSV/JSON + SQLite
        │                                              │
        ▼                                              ▼
오라클 클라우드 서버 (대시보드 · 공시 30초 감시 · cron)   Claude 예약 작업 (매시간 분석 노트)
        │
        ▼
폰 웹앱 (Tailscale 비공개망 · 다른 계정은 조회 전용)
```

**기술**: Python · pandas · SQLite · GitHub Actions · Oracle Cloud · cron/systemd · Tailscale · Vanilla JS · OpenDART · yfinance · 토스증권 Open API

**분석 기록**: [매일 노트](surge-study/notes) · [패턴 플레이북](surge-study/PATTERNS.md)

> 개인 프로젝트 소개이며 투자 권유가 아닙니다. 백테스트·패턴 수치는 과거 데이터 기준입니다.

---

## 🌐 Let's Connect

<p align="center">
  <a href="https://linkedin.com/in/jihun-profile" target="_blank">
    <img src="https://img.shields.io/badge/LinkedIn-Connect-blue?style=for-the-badge&logo=linkedin">
  </a>
  <a href="https://jjinueng.tistory.com" target="_blank">
    <img src="https://img.shields.io/badge/Blog-Visit-orange?style=for-the-badge&logo=blogger">
  </a>
</p>

---

<p align="center">
  <em>"Data is the new oil, and Python is the drill."</em>
</p>

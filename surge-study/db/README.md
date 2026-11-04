# surge.db — 장중 급등주 SQLite

CSV(원본)를 한 파일 DB로 묶어 SQL로 조회한다. `surge.db`는 git에 올리지 않고 명령 실행 때마다 CSV에서 새로 만든다(0.2초).

| 원본 CSV | DB 표 | 누가 쓰나 |
|---|---|---|
| `data/intraday/{kr,us}/날짜.csv` | `snapshots` | 수집 봇(20분마다) |
| `db/catalysts.csv` | `catalysts` | 장중 노트 작성 때 재료 판정 저장 → 같은 날 다시 검색 안 함 |
| `db/hypotheses.csv` | `hypotheses` | 한 줄 가설·채점 |

뷰: `daily`(종목·날짜별 첫 +10% 시각, 최고, 마지막, 스냅샷 수), `daily_full`(+ 반납폭·재료).
미국 `ok=1` = 주가 $2↑·시총 $3억↑.

```bash
python surge-study/db/surgedb.py now us          # 최신: 신규 +10%·진행 상황·재료 캐시 없는 종목
python surge-study/db/surgedb.py day us 2026-11-03
python surge-study/db/surgedb.py cat us 2026-11-04 DUOL Earnings "3Q 실적 상회" https://...
python surge-study/db/surgedb.py sql "SELECT catalyst, COUNT(*), AVG(in_last_snap AND last_chg>=10) FROM daily_full WHERE first_10 IS NOT NULL GROUP BY 1"
```

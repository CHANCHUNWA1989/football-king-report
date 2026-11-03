# UCL 2026-11-03：UEFA 官方比賽頁面 ID 實證核對

本階段是 [PR #387：9場賽事覆蓋審核](https://github.com/CHANCHUNWA1989/football-king-report/pull/387) 的**堆疊改進**。母 PR 只有官方賽程及本地研究 request ID；今次於 2026-11-03 從 [UEFA 官方九場賽程索引](https://www.uefa.com/uefachampionsleague/news/02a8-2174c9e9019d-f909a77bd77a-1000--2026-27-champions-league-all-the-league-phase-f/) **逐場按官方連結打開九個比賽詳情頁**，取得真正公開可查的 UEFA 比賽頁面編號。資料來源為 UEFA.com，不是盤口供應商原始報價。

| 香港時間 11月4日 | 對賽 | UEFA 頁面比賽 ID | 官方頁 |
| --- | --- | --- | --- |
| 01:45 | 薩克達 vs 士砵亭 | 2049613 | https://www.uefa.com/uefachampionsleague/match/2049613--shakhtar-vs-sporting-cp/ |
| 01:45 | 加拉塔沙雷 vs 史特加 | 2049614 | https://www.uefa.com/uefachampionsleague/match/2049614--galatasaray-vs-stuttgart/ |
| 04:00 | 馬體會 vs 拜仁 | 2049608 | https://www.uefa.com/uefachampionsleague/match/2049608--atleti-vs-bayern-munchen/ |
| 04:00 | 巴塞隆拿 vs 阿士東維拉 | 2049607 | https://www.uefa.com/uefachampionsleague/match/2049607--barcelona-vs-aston-villa/ |
| 04:00 | 飛燕諾 vs 國際米蘭 | 2049610 | https://www.uefa.com/uefachampionsleague/match/2049610--feyenoord-vs-inter/ |
| 04:00 | 波杜基林特 vs 里爾 | 2049611 | https://www.uefa.com/uefachampionsleague/match/2049611--bodo-glimt-vs-lille/ |
| 04:00 | LASK vs 施洛雲 | 2049615 | https://www.uefa.com/uefachampionsleague/match/2049615--lask-vs-s-bratislava/ |
| 04:00 | 曼聯 vs 羅馬 | 2049609 | https://www.uefa.com/uefachampionsleague/match/2049609--man-utd-vs-roma/ |
| 04:00 | 維拉利爾 vs 巴黎聖日耳門 | 2049612 | https://www.uefa.com/uefachampionsleague/match/2049612--villarreal-vs-paris/ |

### 所屬身份及可信界線

**四種身份不可互換**：
1. `local_request_id`：本系統9場審核的研究追蹤編號，不是官方 ID。
2. `uefa_match_id`：上述九個已實際打開的 UEFA 官方比賽詳情頁面 ID。
3. `source_event_id`（The Odds API）：供應商 API 若提供之原生事件 ID；**本階段全部未取得、未綁定、未核實**，即使數值剛好等於 UEFA ID 亦不能因此聲稱已完成 join。
4. `bookmaker_id` / 報價 ID：真正莊家雙邊報價及時間標識；本階段沒有。

九個 URL 係當天人工來源查核所見，並固定於 `config/ucl_md4_2026_11_03_uefa_match_links.json`，由 `ops/ucl_official_match_identity.py` 與固定來源覆核記錄比較。這是**離線靜態 link-to-fixture reconciliation**，**唔係**每次 CI 都真正進入 UEFA 官網、核對 TLS、驗證官方更新、更唔係第三方獨立來源認證。程式將 `uefa_live_page_response_authenticated=false` 保留在逐場報告。

### 舊版本與新版本區別

- 舊 PR #387：9/9 只有本地 request ID，官方頁 ID 缺席，公開市場快照六聯賽 h2h 不能支援歐冠報價。
- 本 PR：9/9 都有固定可追溯 UEFA 頁面ID、精確 URL、來源審查描述及本地請求身份配對；任何缺一、重覆、偽造ID、換成非 UEFA 域名、錯誤頁標題、錯場或不明格式，**整份 UEFA 身份證據 fail closed**。
- 本 PR **沒有**新增任何歐冠可成交盤口、賽前模型概率、官方即時正選、獨立結果認證或EV；報告必然 `HOLD / DISABLED`，亦不消耗免費 API 配額、不讀取 Secrets。

### 驗收

```bash
python -m compileall -q ops
python -m unittest discover -s ops/tests -p 'test_ucl_official_match_identity.py' -v
python -m unittest discover -s ops/tests -q
python ops/ucl_md4_nine_fixture_coverage.py \
  --uefa-evidence config/ucl_md4_2026_11_03_uefa_match_links.json \
  --output artifacts/ucl_md4_nine_coverage.json
```

`uefa_official_match_links_reconciled=9` 只表示已核對**官方賽事頁面身份**。即使報告含9個官方 ID，`source_fixture_ids_independently_authenticated=false`、`fixtures_with_verified_betting_quotes=0`、`bets_authorized=0`，而且正式投注維持 `production_recommendations=DISABLED`。

下一個真正外部依賴係合法供應商對**當季 UEFA Champions League**的 provider-native fixture IDs、資料使用授權、實際返回市場完整度及精確時間。之後需另立明確供應商 ID ⇄ UEFA ID 跨源核對，不能根據相似球隊名或者網址臆測。

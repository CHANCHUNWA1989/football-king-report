# 足球王者｜日本 J1 1X2 Shadow 零額度採集前置驗收

**2026-11-23 香港時間；研究限定，正式投注 HOLD / DISABLED。**

## 真實問題（來自已接通 GitHub 倉庫）

已存在 J1 免費市場 sidecar：`ops/japan_free_market.py`、`ops/japan_free_market_guard.py`、`.github/workflows/football-king-japan-free-market.yml`。本次唔會重複新增未獲授權 API，也唔會修改排程或消耗 The Odds API 計費額度。

截至查閱時，`market/japan_free_status.json` 的最後一個已保存快照為 **2026-11-22 08:43:24 UTC（香港時間 2026-11-22 16:43:24）**：

| 來源 | 存檔標記 | 數據真正代表甚麼 |
| --- | --- | --- |
| PropLine | `RESEARCH_ONLY`; `fresh_3way_event_count=7`、`upcoming_events=7`、`provider_daily_remaining=999` | **當日 J1 賽前 1X2／讓球／大小覆蓋觀察統計**；非現時實盤賠率、不是可成交或已被模型使用的原始報價 |
| TheRundown | `NOT_CONFIGURED` | 無已配置的來源 Key／無可用配對觀察 |
| The Odds API J1 | `HOLD`，`quota_remaining=141`、`requests_attempted=1` | 只已做零收費的 sports catalogue 檢查；J1 原始市場請求因保護額度而跳過，不能稱有 J1 1X2 已核實價 |
| 跨 API | `same_fixture_two_api_observations=0` | 沒有兩 API 同場配對；就算兩 API 各出一價亦不能代表兩個獨立持牌 bookmakers |

保留原 `japan_free_market.py` 保護線：`MAX_THE_ODDS_USED=260`、`MIN_THE_ODDS_LEFT=220`；而原六大聯賽 `ops/odds_market.py` 有自己更寬的月度最低額度保留線。最新存檔的 141 低於 J1 專項 220，**不可**因一次舊快照改動保護政策。已保存的 quota 值亦唔係當前帳戶實時餘額。

## 本輪新增，完全零 API 消耗

`ops/j1_shadow_zero_credit_preflight.py` 先用現有 `japan_free_market_guard.check` 核驗原始**去敏感**狀態文檔的完整 schema 及安全旗標，再施加比發布安全閘門更嚴格的「**最後兩小時內的研究覆蓋資訊**」診斷時效；這個兩小時限額**僅適用於覆蓋摘要**，不能當作個別 sportsbook 報價的容許 age，也唔會解除來源更新上游時間核查。

固定輸出：
- `status=HOLD`、`decision=HOLD`、`production_recommendations=DISABLED`；
- `requests_performed=0`、`api_credits_spent=0`、`new_odds_request_allowed=false`、`network_collection_allowed=false`；
- `shadow_model_scoring_eligible=false`、`same_instant_market_quote_verified=false`、`raw_market_bytes_available=false`、`positive_ev_verified=false`、`certified_forward_samples=0`；
- 即使快照的 quota value >220、PropLine 有7場覆蓋或跨 API 出現一個數值相符的配對，都不會自行認證市場可成交、模型校準或授權開始新查詢。

### 零費用使用方式

```bash
python ops/j1_shadow_zero_credit_preflight.py --status-file market/japan_free_status.json
```

命令只讀本地 JSON，打印**無原始盤口、無密鑰**的診斷摘要；總是以退出碼 `2` 表明不可直接推進自動採集／推薦。**唔好因命令退出碼 2 而重試 API 查價**。

`ops/tests/test_j1_shadow_zero_credit_preflight.py` 提供純合成測試，涵蓋 141/220/221 額度邊界、過期快照、假資料、同一賽事跨源匹配不足、模型／EV 注入及實際零請求（mock 網絡函式確認沒有被呼叫）。

## 下一個需要外部資料而非更多模擬程式

1. **先取原有每次排程已存在嘅官方 header 診斷**，不得從舊的 141 推斷目前 quota；繼續保留 J1 專項 220 與原六聯賽保護政策。若餘額不足，停止 J1 Odds API 市場查詢。
2. PropLine 7場係已存檔**覆蓋數量**，沒有同時提交 source-native fixture IDs、精確 kickoff/market-last-update/raw quote 到私密可核對前瞻包，所以不能將這7場算成認證前瞻樣本。要試點真正 Raw/Private capture，需另行核實供應商條款、資料留存權限及當時完整來源證據。
3. 先用源生賽事 ID 做 1X2 賽前 Shadow paired preflight，再比較同時間前瞻 model/市場，並在賽後用獨立原始證據封存 90 分鐘賽果。不能用 1X2 估算亞洲讓球、大小球的下注可成交 EV。
4. PR #554 研究來源權利/WE League/HKJC 閘門保持 Draft；日本 J League 1X2 同 WE League／HKJC 讓球主客和唔可以互相當同一個授權 scope。

## 驗收

```bash
python -m compileall -q ops
python -m unittest discover -s ops/tests -q
```

需 GitHub exact-head regression、安全、壓力、ledger、validate 全部綠燈及獨立 peer review，方可考慮研究 sidecar 併入 main。**程式通過測試不等於實盤資料已收集，更不等於模型有正 EV。**

官方關於 The Odds API v4：<https://the-odds-api.com/liveapi/guides/v4/>。Sports catalogue/`events` 不消耗 odds 配額；`odds` 端點以實際 region × markets 計價。即使 `/sports` 本身免費，仍須有有效 Key 才能核對當前帳戶狀態；本輪**未**直接查詢。

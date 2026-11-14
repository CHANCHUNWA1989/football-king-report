# Market coverage audit：修正「要求查詢 = 已有盤口」誤判（2026-11-07）

研究修復，不啟用投注。主工作原則：提供可追溯的缺口而非假正 EV。

## 錯誤重現

原 `ops/market_coverage_audit.audit` 將 `market/private_summary_latest.json` 的 `requested_markets` 直接當作 `observed`。如果輸入 `["h2h", "spreads", "totals"]`，即使市場報價數目為 0 或只有 1X2 去水概率，都輸出 `market_coverage_complete=true`、`handicap_available=true`、`totals_available=true`。

## 修復

- 將請求類型與實際觀察分開：`requested_markets` 只表示查詢意圖，`observed_consensus_markets` 僅按有有效樣本的公開 H2H 共識快照認定。
- `missing_markets` 列明實際未觀察市場；`requested_but_unobserved` 特別顯示有要求但未證實收到的市場。
- 現有私有摘要只存市場總報價數及六個聯賽，不包括讓球／大細的逐盤 identity、線、莊家及價格；**無論 `requested_markets` 點填，`market_coverage_complete` 仍為 false**。未來要有具來源、原件及時間戳的報價專用安全管道才能改變此資格。
- 保留輸出 schema 名稱供既有消費端兼容，任何 `verified` 或 `quotes_are_executable` 自稱旗標都不可令報告升格。
- 嚴格維持 `DISABLED`／HOLD，無額外 API 請求、配額成本、原始賠率公開或模型重新訓練。

## 驗收

`ops/tests/test_market_coverage_audit.py` 六組測試：只有 H2H、虛構全市場請求及 aggregate 報價、空快照、壞快照／來源狀態、錯誤市場類別、聲稱已認證的造假旗標。

```bash
python -m compileall -q ops
python -m unittest ops.tests.test_market_coverage_audit -v
python -m unittest discover -s ops/tests -q
```

## 仍未解決（不可假稱已修復）

1. 需取得正式授權、可用的原始亞洲讓球及大小球報價（獨立市場 ID、線、方向、decimal odds、博彩公司與逐筆 UTC 時間戳）；既有主市場快照 **只有 h2h 去水共識**。
2. 四分之一亞洲盤、大小球半贏／半輸結算及凍結賽前證據在 Draft #451/#453，尚未正式合併。
3. 合資格預賽前模型需要樣本外校準、逐場發佈前截數、獨立確認賽果，真實可成交性仍無證據；保留官方推薦停用。
4. #439 的主分支保護與獨立人手 review 仍是 release blocker。

此修正提升的是報告真實性，**不是新增已授權數據、提高命中率或認證正 EV**。

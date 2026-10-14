# 四模型 Shadow Mode 每日報告

此工作流程只作研究，不會執行交易或開啟正式推薦。

## iPhone 操作

1. 開啟 GitHub 儲存庫 → Actions → **Daily four-model shadow research**。
2. 正式合併並啟用工作流程後，可用 **Run workflow** 手動執行；或等待每日排程。
3. 打開該次執行 → Artifacts → **four-model-shadow-daily**，下載 JSON 報告。

## 資料契約

必須有以下兩份**真實**資料，才會嘗試評分：

- `shadow/verified_sealed_predictions.json`：JSON array，每筆有 `fixture_id`, `kickoff_utc`, `sealed_at_utc`, `market_snapshot_utc`, `model` 和 `market`；機率向量按主／和／客排序。
- `shadow/independent_ft_observations.json`：JSON array，每筆有 `fixture_id`, `status="FT"`, `provider_id`, `independent_group_id`, `published_utc`, `home_goals`, `away_goals`。

兩個不同來源群組必須就**同一場**全場入球一致。未有證據時輸出 `HOLD`，有效場數為零；不會從舊有單一來源結算自動升級成「獨立驗證」。

**重要：** 此 PR 尚未把既有封存及來源採集器轉換成上述契約；正式合併之前應檢查來源權限、時間戳、賽事身份、衝突隔離和 CI。排程只在合併到預設分支後生效。

報告中 `accuracy`、`brier`、`log_loss` 只對經核實樣本計算。未有有效樣本時為 `null`，絕不表示已達標或有盈利能力。

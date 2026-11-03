# KPL V11：逐局預測封存、時間防洩漏及BO樣本外評估

2026-11-03｜Research only, stacked on PR392 / PR391 / PR390.

## 目標與功能範圍

新增獨立標準庫 Python 研究模組 `research/kpl_v11_forecast_archive.py`，不更改現有足球、籃球及量化共享模組，亦不啟用市場抓取、網站部署、盤口或正式投注。

### 1. 預測封存的資料契約
一個觀測對應一個 **系列賽series_id＋game_number**，每個遊戲小局只封存一個預測，避免同一局多個時間點當成多個獨立樣本：
- `prediction_id`、`series_id`、`game_number`、雙方穩定 `team_ids`、`predicted_team_id`。
- `model_version`、`probability`、`phase`（PRE_GAME 或 BP_LOCKED）。
- `info_cutoff_at`、`forecast_at`、`game_start_at`，必須時區明確，截止 <= 預測 < 開局。
- `evidence` 每項包括 `source_id`, `kind`, `subject_game`, `published_at`, `captured_at`，必須來源發布 <= 擷取 <= 資訊截止。拒絕同場結果偷看、未來局數、同局BP未進入BP_LOCKED狀態、來源逾時及未知輸入欄位。
- `status` 強制 RESEARCH_ONLY。

資料欄位的時效能被結構驗證，但第三方提供的來源時間可能偽造，不能因此聲稱來源已受信任。已取得官方授權的資料供應者依然須另設簽章及獨立認證層。

### 2. 封存及完整性
`archive_forecast(path, row)` 採用獨立本地 JSONL 逐筆追加，每筆有 `previous_hash` 與 SHA256 `entry_hash`；`verify_archive(path)` 在讀取時計算雜湊鏈，拒絕斷鏈、修改、重複預測、重複局數、資料倒流及檔案不完整。透過本地 .lock 防止一般並發寫入；簡單鎖不保證分散式或所有檔案系統的原子性。

**SHA256不等於不可篡改**：有權改動整個檔案者可重算所有摘要，因此須把每次 head_hash 在外部可信服務持久錨定，才可能聲稱具外部防篡改證據。本PR未實作該服務。

### 3. 結算及回測
`chronological_holdout(forecasts, results)`：
- 只接受結果與預測ID、系列賽ID、局數一致，明確外部 verified=True，來源標記有效，完場時間早於結果觀測時間。此 verified 是供應者或人工輸入的**聲稱**，程式無法獨立證明真偽。
- 按 game_start_at 嚴格排序；資料按 **完整系列賽** 分組，禁止同一場 BO7 同時出現在訓練及測試，避免系列內英雄池與結果互相洩漏。
- 訓練結果 observed_at 必須嚴格早於最早測試預測 forecast_at，避免歷史結果實際遲於測試預測才公開的資料倒灌。
- 僅用訓練組 outcomes 計算固定機率 baseline；測試組只做評分。
- 提供 train/test Brier、Log Loss、5組 ECE及校準分桶、train-prior baseline。**無模型訓練、超參數選擇、真實KPL資料、正式勝率或回報率認證**。
- 輸出永遠 `status=HOLD`、`production_recommendations=DISABLED`、`live_execution_allowed=False`，資料真實性及授權狀態不由程式自行聲稱完成。

### 4. 已知限制與後續
1. 需要真實資料合法使用權、來源簽章驗證及不可變版本化原件；無權利前不可啟動外部採集器。
2. 許多比賽缺逐分鐘經濟與BP發布時間戳，目前只驗證已有的結構欄位。
3. 本地不可變性依賴外部hash錨點；未啟用雲端永久證據庫。
4. 單一局數1個預測，不包括賽中多個checkpoint，賽中版本須另外建立獨立時點標籤與賽局中情報截止。
5. 不代表V11模型已訓練，也沒有實際KPL樣本外準確率或EV。

## 驗證命令
```bash
python -m compileall -q ops research
python -m unittest discover -s ops/tests -p 'test_kpl_v11_forecast_archive.py' -v
python -m unittest discover -s ops/tests -q
```
全部 CI 通過與獨立審查之前保留 Draft。既有 `production_recommendations=DISABLED` / HOLD 不變。

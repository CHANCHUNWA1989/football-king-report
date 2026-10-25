# 報價證據 v2：完整語意綁定（研究用途）

舊 `canonical_quote_digest` 只雜湊六個欄位。相同賽事／市場 ID 下，改動
`line`、`selection` 或博彩公司不會改變摘要。合成重現不是實際報價或認證樣本。

## 新輸入契約

`canonical_quote_digest(quote)` 及 `research_evidence_record(quote)` 現在要求以下
完整欄位，缺漏或多餘欄位均拒絕，避免靜默忽略未綁定的別名：

- 非空字串：`fixture_id`、`market_id`、`source`、`source_quote_id`、`bookmaker_id`。
- `market_type`：`h2h`、`spreads`、`totals`；選項 `selection` 分別為
  HOME/DRAW/AWAY、HOME/AWAY、OVER/UNDER。
- `line`：h2h 必須明確為 null；spreads/totals 為有限數值四分之一球盤，totals 不可負。
- `decimal_odds`：有限數值且大於 1；布林值不作數值接收。
- 三項時區明確的 Python datetime：`bookmaker_updated_at_utc`（來源標示更新時間）、
  `observed_at_utc`（回應完整接收時間）、`kickoff_utc`（紀錄中的預定開波時間）。
  必須更新時間 ≤ 回應完成時間 < 預定開波時間；全部以 UTC 正規化後綁定。

摘要加入 `football-king-quote-evidence-v2` 格式標記，回傳紀錄明示
`independently_verified: false` 及 `production_recommendations: DISABLED`。
完整報價不能直接交給公開 artifact；此修復沒有增加資料採集、儲存或輸出路徑。

## 相容性及邊界

這是嚴格輸入契約更新；現有 main 只有本模組測試使用此介面，沒有生產管線消費者。
舊六欄輸入會拒絕；舊摘要不能與 v2 混用，亦不會事後重算或升格舊封存證據。
未合併草稿 PR 的未來消費者須先按此契約適配，不能假設舊介面仍獲支援。

SHA-256 只綁定提供的內容，不能證明來源、授權、博彩公司真實報價、實際開波、
新鮮度、模型校準或可成交性。此修復沒有接通私人跨工作流程封存、獨立賽果認證、
認證樣本統計或正式推薦；品質閘門及歷史預測不變，亦未證實預測表現提高。

## 驗證

先加入測試：舊程式 12 個測試出現 27 個子測試失敗及 1 個錯誤，包含盤線、
選項、博彩公司及時間未綁定。修復後驗證三類市場、欄位順序／UTC 等價、
逐項更改摘要、未知／缺失欄位、非法市場／盤線及時間倒序／無時區拒絕。
完整驗收結果、獨立覆核及 GitHub CI 以此修復 PR 的實際紀錄為準。

# 推薦能力修復工單｜2026-10-15

狀態：RESEARCH ONLY；production_recommendations = "DISABLED"；不得自動合併。

## 實際問題
公開盤口網頁參考價、莊家當時可成交價、第三方模型概率混用，導致候選方向無法升級；零正式推薦並非只因門檻過高。先處理資料完整性，不降低安全門檻。

## 實作次序（每項獨立PR）
1. 盤口快照：fixture_source_id、kickoff_utc、bookmaker、market、line、decimal_odds、bookmaker_updated_utc、captured_utc、source_license；缺欄位或晚於開賽即HOLD；不同莊家不可當同一報價。
2. 賽事全量掃描：列出指定日期所有已核對賽事，對每場輸出 AVAILABLE / STALE / MISSING / CONFLICT / STARTED，不得靜默略過。
3. 研究分級：A = 資料及獨立校準證據足夠；B = 方向觀察；C = 資料不足。A級研究亦不等於已批准真實投注。
4. 獨立評分：封存賽前模型、市場同一截止時刻、結算後Brier/log loss、校準圖、樣本量、置信區間、CLV；與市場基準比較。
5. 免費配額：API不足時顯示缺失及最後有效快照時間，絕不以舊價當即時價。
6. iPhone面板：顯示賽事覆蓋率、最後成功擷取、各場HOLD原因、研究候選與正式建議明確分離。

## 驗收條件
- 測試：有效賽前快照接受；過期、開賽後、來源衝突、賠率缺失及不同市場錯配全部拒絕。
- `python -m compileall -q ops`
- `python -m unittest discover -s ops/tests -q`
- GitHub Actions 全部受影響工作流程成功，核對真實輸出；只測試通過不代表預測有效。
- 保留 A/B/C 封存、原有安全閘門、API Secrets 與 HOLD。
- 不宣稱提升命中率、正EV或正式下注推薦，直至有獨立前瞻證據及人工批准。

# 其他足球系統：時序評估原則及本輪實作

## 本輪核對的專案

- [Reymes/football-match-prediction](https://github.com/Reymes/football-match-prediction)：核對固定版本 `3350be972ad7af0419dfc71134c8299ed5ae134a` 的 MIT LICENSE（Copyright 2026 Yassine）及 `match_predict/evaluation/backtest.py`。值得參考的部分是互斥的過去／validation／test 時間區間、只用先前資料校準、同場市場基準，以及分清數值較好與統計優勢。其 README 的績效數字未由本專案獨立驗證，不套用為本系統成績。
- [karimbabasf/world-cup-oracle](https://github.com/karimbabasf/world-cup-oracle)：README 的90分鐘／加時／互射十二碼分開處理可供後續研究；國家隊模型及作者自述成績未直接套入聯賽。未複製其程式、數據或預測。
- [szkkteam/soccer_fw](https://github.com/szkkteam/soccer_fw)：已核對 GitHub MIT 授權，但 README 只有簡介，未有足夠驗證資料，本輪未採用。

## 找到並修復的本地問題

`market_shrinkage.compare` 原先直接排序 kickoff 原件，再按筆數切分。不同 UTC offset 的字串會排錯先後；同一開球時刻的案例可分散在先前區間與 holdout；日期跨度亦按原始字串而非 UTC 日計算。

這與借鑑的嚴格時間區間原則不一致，並會污染留出集與覆蓋日期的研究判斷。現改用共用 UTC 排序 key，同一時刻跨邊界直接拒收；不自動移動案例、重選比例或按照輸贏改動留出集。

- 有時區 datetime 與 ISO 字串依 UTC instant 排序；等價 offset 視為同一 cohort。
- 保留舊有 YYYY-MM-DD 研究標籤為整日 cohort key；它不是開波時間證據，亦不會補寫到來源或封存資料。
- 完整 cohort 全部位於 holdout 可以通過；只有跨邊界才拒絕。
- holdout 日期覆蓋以 UTC 日計；完整但無時區的時刻、未知格式及 UTC 轉換錯誤拒收。
- `unified_research` 重用既有例外攔截，輸出 HOLD 及空缺的 holdout 評分，不產生錯誤的留出集結果。

本輪只借鑑已核對來源的時間分區原則，並沿用本地 `backtest_evaluation` 已有的同開球邊界拒收做法；沒有複製上游 Python 程式、模型、資料或第三方績效。

## 驗收與限制

先新增測試，觀察10個失敗案例；再最小修復。涵蓋同時刻跨邊界、等價 offset、真正的最後 UTC 案例、UTC 日期覆蓋、無時區拒收、完整 cohort 正例及 runner 的 HOLD 行為。

55項相關測試及唯一一次完整2,530項ops回歸成功、無skipped；compileall及diff檢查成功。遠端CI紀錄保留於原Draft PR #451最新HEAD說明。

不擷取供應商資料、不安裝依賴、不重算真實封存或已發表成績。候選權重、RPS、Brier、Log Loss 算式及正式閘門不變。互斥時序只是一項結構性條件，不能證明訓練原件、結果可得時間、來源授權或真實樣本外優勢；仍須獨立驗證。

維持 Draft #451／HOLD／DISABLED／POSITIVE_EV_VERIFIED=False；不合併PR、不部署、不投注。

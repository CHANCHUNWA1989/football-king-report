# 足球開源系統：本輪實際採用範圍

用戶授權直接判斷及更新；本輪只增強現有概率評估，沿用 Draft #451，不建立另一套預測系統。

## 搜尋及取捨

- [penaltyblog](https://github.com/martineastwood/penaltyblog)：核對 MIT 原文及固定版本 `6870f0e762e9cba35fa722dc14a8daeaf8bc6134`。Poisson、Dixon–Coles、亞洲盤及去水已有本地實作，沒有重複搬入；採用其累積概率／累積實際結果的 RPS 評分方法，統一本地共用函數。
- [EuropeanFootballLeaguePredictor](https://github.com/nickpadd/EuropeanFootballLeaguePredictor)：已核對 LICENSE.txt（MIT）；README 註明不再活躍維護。長短期球隊狀態可供後續研究，但沒有搬入舊模型、Kelly 注碼、資料或績效宣稱；其跨季評估仍需獨立核對資訊時間。
- [Football_Prediction_Project](https://github.com/mhaythornthwaite/Football_Prediction_Project)：README 的近10場統計差值可作特徵研究參考，但即時預測網頁已停用；本輪未複製其程式或需 API 授權的資料。
- 在先前籃球候選作者 kyleskom／nealmick 的帳戶搜尋足球專案，未找到匹配結果；因此改用上述足球專門專案。

## 最小接入

1. 提取本地原有 RPS 為 `market_shrinkage.ranked_probability_score`，適配已核對的 penaltyblog 累積計算法；保留完整 MIT 原文、作者、來源固定 SHA 及改動說明於 `third_party/penaltyblog/`。
2. 維持 home／draw／away 順序；分數除以類別數減一，越低越好。沿用本地概率型別／範圍／總和檢查，拒絕 boolean、NaN 及錯誤結果索引。可接受的四捨五入尾差只在函數內正規化，不修改輸入。
3. 原市場收縮及每日覆盤共用同一 RPS 函數；`model_evidence.evaluate` 對相同已結算案例新增 model_rps、market_rps、market_minus_model_rps。
4. 新指標明示 rps_is_descriptive_only=true；原 Brier、Log Loss、門檻及週區塊 bootstrap 不變。既有 difference_block_bootstrap_95pct_ci 仍屬 Log Loss，不是 RPS 信賴區間。

## 驗收及安全

先觀察缺少共用函數／RPS欄位的失敗，再實作；另以均等但總和0.999的概率先重現正規化尾差，修復後手算 0、0.5、1、0.145、1/9，以及模型／市場同場平均與差值均通過。

最終78項相關測試及一次完整2,524項ops回歸成功、無skipped；compileall、獨立package匯入與diff檢查成功。遠端CI以原Draft PR #451最新HEAD驗收紀錄為準。

本輪不執行真實資料重評、不重新選模型、不改固定權重、封存預測、賽果或已發表成績；不安裝 penaltyblog、NumPy 或 Cython，不呼叫任何供應商 API。軟件 MIT 授權不代表外部賠率／足球資料授權。

只有研究程式改進，不是新的模型優勢或正 EV 證據。維持 HOLD／DISABLED、POSITIVE_EV_VERIFIED=False；main／#439、真實來源證據及獨立人手審核仍未完成，不合併PR或部署。

# Paired Poisson / Dixon–Coles research uncertainty

The optional research pipeline is:

1. Validate target fixture IDs and final-result cohort.
2. Refit Poisson and Dixon–Coles separately at each target's `as_of_utc`, using only historical results recorded before that cutoff.
3. Compare the exact same target IDs, kickoff times, cutoff times and outcomes; fail the entire cohort on missing or duplicate forecasts.
4. Calculate 1X2 accuracy, Log Loss, Brier and calibration bins for both models.
5. Calculate per-fixture paired differences (Dixon–Coles minus Poisson in accuracy, Poisson loss minus Dixon–Coles loss in Log Loss and Brier); positive means Dixon–Coles is better on that metric.
6. For at least 30 paired fixtures, produce reproducible percentile 95% IID bootstrap intervals from 1,000 paired resamples by default.

## Strict limitations

- The 30-fixture threshold is a **minimum for reporting an exploratory interval**, not a claim of adequate statistical power. Real evaluation requires larger prospective cohorts and a predeclared sample plan.
- IID bootstrap assumes independent fixtures; same-team, same-league and same-matchday dependence can narrow intervals spuriously. Future work: league/date cluster bootstrap with adequate independent clusters, out-of-time validation and multiple-comparison controls.
- Calibration bins and ECE are diagnostic and unstable on small samples.
- `evidence/settled.json` does not provide independently verified results for its 82 fixtures. This pipeline has no verified real-match model winner, no bookmaker-executable odds and no proven EV or ROI.
- Local timestamps and boolean flags are not independent time or source attestation. Never automatically promote a model.
- This code does not write to main, execute bets, enable production picks or bypass Issue #439 independent review.

Research outputs remain `HOLD` with `production_recommendations=DISABLED`.

## 2026-11-16：既有開源模型接線修補（交接）
- 沿用 #458 已接駁的 MIT penaltyblog Poisson／Dixon–Coles 及 RPS；沒有重複搬入模型、複製外部源碼、安裝依賴或呼叫供應商 API。
- 重現同一開波時刻因 `Z`／`+00:00`／零小數秒／跨日 offset 字串不同，被 paired scoring 與 uncertainty 誤拒的單一相容問題。
- 兩處 guard 重用 `_timestamp` 比較精確 UTC instant；不加容差、不修改原始欄位、固定參數或封存資料；身份／共同 cutoff／防洩漏規則保留。
- TDD 先見 14 個 scorer／pipeline 失敗案例及 1 個 uncertainty 失敗；新增 7 個測試方法，覆蓋同時刻報告／bootstrap 完全一致、輸入不變、正負 1 秒及無時區拒收且無部分指標。
- 51 項局部測試成功；一次唯讀 QA 另驗 31 項成功、無可行動問題；助理覆核不是獨立真人發布批准。
- 已保留遠端 `89ffe8fd` 修改；完整回歸 2,869 項、0 失敗、2 跳過（本地未裝 penaltyblog 的真 RPS／soccerdata 的 constructor 測試）；compileall／diff --check 成功。
- 原 Draft #458，HOLD／DISABLED、positive EV=False；未合併／部署，未改正式 A/B/C；真實來源／賽前見證／獨立賽果及真人審核仍欠，測試未證實預測或盈利改善。

# Paired Poisson / Dixon–Coles research uncertainty

The optional research pipeline is:

1. Validate target fixture IDs and final-result cohort.
2. Refit Poisson and Dixon–Coles separately at each target's `as_of_utc`, using only historical results recorded before that cutoff.
3. Compare the exact same target IDs, kickoff times, cutoff times and outcomes; fail the entire cohort on missing or duplicate forecasts.
4. Calculate 1X2 accuracy, Log Loss, Brier and calibration bins for both models.
5. Calculate per-fixture paired differences (Dixon–Coles minus Poisson in accuracy, Poisson loss minus Dixon–Coles loss in Log Loss and Brier); positive means Dixon–Coles is better on that metric.
6. For at least 30 paired fixtures, produce reproducible percentile 95% IID bootstrap intervals from 1,000 paired resamples by default.
7. Separately, with at least 30 fixtures and 12 observed UTC ISO weeks, sample whole weeks with replacement for a weekly cluster sensitivity interval. Every metric uses the same selected paired blocks; weight each draw by its actual fixture count, not an average of week means. Use a separate seeded stream so IID results remain unchanged.

The assessment and pipeline expose `week_block_count`, `week_block_interval_status`,
`week_block_bootstrap_repeats` and `paired_week_block_bootstrap_95pct_intervals`.
Insufficient fixtures or weeks give a null weekly interval and zero weekly repeats.
These reporting floors do not establish adequate statistical power or independent weeks.

## Strict limitations

- The 30-fixture threshold is a **minimum for reporting an exploratory interval**, not a claim of adequate statistical power. Real evaluation requires larger prospective cohorts and a predeclared sample plan.
- IID bootstrap assumes independent fixtures; same-team, same-league and same-matchday dependence can narrow intervals spuriously. UTC-week resampling retains within-week dependence but still assumes independence across sampled weeks. Same teams across weeks, league dependence, sparse/separated weeks, out-of-time validation and multiple-comparison controls remain unresolved; neither interval authenticates a sample or establishes model advantage.
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

## 2026-11-16：逐場重訓 CLI 重複 JSON 欄位拒收（交接）
- 原 CLI 使用 JSON 最後一值覆蓋規則；現重用 bridge 的 `_unique_json`，頂層及任意巢狀同名欄位均在重訓前以 `DUPLICATE_JSON_KEY` 拒收。
- TDD 先重現 6 個失敗案例：模型欄位衝突／相同值重複、未來 cutoff 被覆蓋、布林比分被覆蓋、來源錯配被覆蓋，以及 Unicode 轉義後同名 event ID。
- 正常唯一欄位 CLI 報告與原直接呼叫一致；拒收時無模型建構、無標準輸出報告，原始輸入檔保持逐字不變；測試全為合成資料及假模型。
- 53 項相關測試成功；完整回歸 2,871 項、0 失敗、2 跳過（本地未裝 penaltyblog 的真 RPS／soccerdata constructor）；compileall／diff --check 成功。
- 僅改既有 CLI、其測試及本文件；沿用原 Draft #458，單一開發 Agent，無新模組／依賴／供應商 API／原始資料擷取，上一輪 UTC 修正保留。
- HOLD／DISABLED、positive EV=False；無修改封存／模型參數／真實成績，未合併／部署。Issue #452 授權及真實證據、#439 與真人審核仍待外部完成；未證實預測或盈利改善。

## 2026-11-16：模型比較新增 UTC 週組區間（交接）
- 新增每週整組配對抽樣及 pipeline 四欄輸出；至少30場、12個 UTC ISO 週才提供研究區間，門檻不代表足夠檢定力或已驗證獨立性。
- 同一組抽中週供三個指標共用，分母用該次實際抽中場數；獨立 RNG 保留原 IID 結果；5個合成 cohort 與原 HEAD 的舊欄位逐欄一致（解釋文字除外）。
- TDD 先重現9個缺欄失敗案例；61項相關測試成功，覆蓋門檻、UTC跨年、加權／重複抽樣、相關性敏感度、輸入不變及非法 cohort 無部分輸出。
- 保留遠端時間衰減候選後，完整回歸2,886項、0失敗、2跳過（本地未裝 penaltyblog 真RPS／soccerdata constructor）；compileall／diff --check 成功；一次唯讀QA無實作缺陷，已補強重複抽樣分母 oracle。
- 沿用 Draft #458；沒有新實作模組、依賴、資料採集或真實成績重算。預先規則及檢查表見 `docs/superpowers/plans/2026-11-16-paired-week-bootstrap.md`。
- 今輪週組功能只更新比較，未改既有模型權重／封存預測；時間衰減研究候選保留，正式模型替換仍受 #452 資料／授權、#439 及獨立真人審核阻塞。HOLD／DISABLED、正EV=False，未合併／部署，未證實預測或盈利改善。

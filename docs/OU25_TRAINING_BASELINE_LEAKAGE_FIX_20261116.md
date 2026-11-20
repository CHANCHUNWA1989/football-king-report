# 2026-11-16 — OU2.5 回測的測試集基準資料洩漏修正

## 原因／重現

原版 `ops/ou25_independent_backtest.py` 用 *本批已結算測試賽果* 計算：
`baseline = mean(actual_over)`；再用 `baseline*(1-baseline)` 作為比較基準 Brier。
該比較基準已讀取測試集結果，違反實際開賽前可用資料的規則。原輸出
`outperforms_constant_rate_baseline` 不可當成公平的樣本外比較。

新測試 `test_no_hindsight_baseline_from_heldout_results` 反映缺陷：沒有提供任何
早於賽事預測的訓練基準時，必須顯示 `None`，不許從測試資料推算。另測試截止
時間不得等於或晚於最早一個納入評分的 `sealed_at_utc`。

## 最小修正（不改原A／Poisson／Dixon–Coles模型）

- `audit(predictions, results, baseline=None)`：不帶基準時，**只評模型已結算 Brier**，
  `constant_rate_baseline_brier=null`，`outperforms_constant_rate_baseline=null`。
- 如需要公平比較，另傳不依賴測試賽果、測試預測之前已可取得的 JSON：
  `{"probability_over":0.53,"sample_count":250,"training_cutoff_utc":"2026-09-30T23:59:59Z","source":"prior-season-dataset"}`。
  以上數值**純為結構示例**，不是任何真實來源／已驗證預測。
- 基準固定機率須為有限0至1實數（布林不可）；訓練樣本不少於30；來源非空；
  UTC時間須帶時區，並嚴格早於所有納入的 sealed 預測。違反直接拒絕。
- 以固定先驗機率對每一場結果計算 `(prior - actual_over)^2`，不重新擬合先驗。
- CLI 新增 `--training-baseline path.json`，未提供不作基準模型優勢判斷。
- 訓練先驗之 `source` 與 `training_cutoff_utc` 仍然**只係自報資料**，
  `training_baseline_independently_authenticated=false`；不可視作第三方簽署證據。
- 已封存 A/B/C 預測、賽果、配重、研究原件及 production 閘門完全不改。
  `production_recommendations=DISABLED`；`market_odds_or_ev_verified=false`。

## 已存在的跨聯賽診斷（本PR不重算、不修改）

2026-11-16 另行獨立回放 OpenFootball 固定Git版本 `e6744429`：
10組完整球季日期切割／2,380場，1X2 Brier 約0.6183 vs 訓練球季弱基準0.6524；
大2.5 Brier 約0.2450 vs 訓練球季弱基準0.2446；BTTS約0.2484 vs 0.2455。
這些係**外部回放調查**，唔係本PR新CI結果、真實賠率收益或正式前瞻評級。

## 驗收條件

1. 無先驗：不輸出偷睇測試集的基準／優勢訊號。
2. 合法、早於預測的先驗：返回正確逐場配對 Brier。
3. 截止時間晚、天真時間、布林概率、布林樣本數：拒絕。
4. ≥100場只有測試賽果、無先驗：仍係 `AUDIT_READY_BASELINE_MISSING`。
5. 相關測試及全套安全回歸通過；如缺少可核對的CI不得宣稱通過。

## 尚未完成

- 真正外部來源權利與原始資料時間簽署；獨立兩源賽果、開賽前封存及當時可成交亞洲大小盤賠率。
- 比較 1X2 之外的實際勝負分布，修正大球/BTTS 低估，先用未知賽事做獨立校準與跨聯賽壓力測試。
- 未有真實正EV、ROI、CLV證據，亦不可提升正式投注權限。

# 開源系統對照審計與修正紀錄（2026-11-07）

## 比較對象（僅借鑑方法，未複製源碼）

- [martineastwood/penaltyblog](https://github.com/martineastwood/penaltyblog):
  可選 Poisson / Dixon–Coles 目標機率模型、多類評分與研究回測；
  本倉庫對應研究接口為 Draft PR #458。
- [R1ch1k/betting-backtester](https://github.com/R1ch1k/betting-backtester):
  重視事件順序、rolling walk-forward、時窗邊界排除數及不確定性；
  本 PR 的 expanding walk-forward 是獨立實作，僅對照方法。
- [本倉庫 ops/offline_1x2_holdout.py](../ops/offline_1x2_holdout.py):
  原有單一 chronological holdout + training-only outcome prior；
  不能單憑一次 70/30 切分推論長期可靠性。

## 已修復（此 Draft PR #460）

1. **重大信任邊界問題**：`paired_challenger_comparison.evaluate`
   過去會把 `independently_verified=true` 和
   `sealed_before_kickoff=true` 視為外部已核實，即使它們完全由
   CSV/JSON 提供方自行聲明，也回傳 `RESEARCH_ONLY`。
   現在即使數值有效，也只回傳 `HOLD` 與明確標記的
   `unverified_diagnostic_metrics`。未驗證 timestamp authority、
   原始賽果及市場報價時間，絕不升格。
2. **時間窗口與洩漏風險**：新增
   `ops/expanding_walkforward_audit.py`，以 kickoff 排序，前段
   train 後接無重疊測試窗口；每個窗口的訓練賽果必須早於窗口
   最早一筆 `forecast_at` 已可得。未完場或事後才可得的賽果
   不能進入該窗口基準。**有一個窗口缺少最低訓練量就整批 HOLD**。
   同一時刻開球的比賽不拆分；測試尾段不足標準窗口仍須納入，
   不可無聲無息刪除差的樣本。
3. **明確報告範圍**：逐窗口及全體計算 1X2 模型與
   training-only outcome prior 的 Brier、Log Loss、Accuracy，
   同時記錄窗口數、可得訓練筆數及尾段 test 筆數。
   只可視為輸入資料的**未核實診斷**。

## 尚未修復／不可宣稱

- 只稽核事先輸入的模型機率，**沒有重新訓練 Poisson/Dixon–Coles**；
  真正每個窗口重新擬合必須另建可核對的原始賽事、模型版本與特徵紀錄。
- 既有 `evidence/settled.json` 的 82 場
  `fixture_result_source_independently_verified=false`，
  不能視作有外部賽果見證。不得單用自填 boolean 代替原件或 TSA。
- 正式賠率必須保留 bookmaker、market、line、quote capture UTC、
  executable timestamp、limits、commission、market suspension 等資訊；
  現階段不能計算或宣稱 EV / ROI / 可成交價。
- 研究採集需合法來源、同一賽事來源原生 ID、
  外部時間認證、可重播來源修正紀錄、足夠樣本和
  群聚 bootstrap/配對不確定性，且檢視類別/聯賽偏差。
- Draft PR #458/459/460/461/462/463 尚未合併；
  Issue #439 的 main 分支保護與獨立人手審核仍屬 release blocker。

所有程式只作離線研究，`production_recommendations=DISABLED`；
任何研究改善不能被當成正式投注建議。

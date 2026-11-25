# 足球王者｜六聯賽 Shadow 輸入覆蓋診斷（2026-11-23）

## 實際問題與來源
2026-11-23 香港時間 17:43 左右，GitHub Actions #45149415323 的已封存 `shadow.json` 顯示 27 個研究預測全部係德甲；英超、英冠、西甲、意甲、法甲各 0 個。各來源的 `READY_RESEARCH` 只指來源 gateway 可提供研究資料，**不是**「有可用的精確開球時間」、「模型勝率合格」或「已認證的投注」。歷史個別賽事是否因哪一個原因被拒絕，原有 `sources[]` 不足以逐項區分。

## 改動範圍
- `ops/shadow_eligibility_diagnostics.py`：對**已有且不變的原始 fixture rows** 提供描述式分項計數。區分完場前史記錄、未賽場次、缺精確時分／時區、當地日期或時間窗錯誤、符合基本時間條件但仍缺合格模型輸出；只輸出可觀察資料。
- `ops/shadow_forecast.py`：每個 `sources[]` 新增 `input_eligibility_diagnostics`；預測機率、入球期望、訓練截止、原始 A/B/C 封存與所有模型權重均**不變**。
- 直播式產生流程可能在完成時計時排除預測；另提供 `predictions_retained_at_completion` 以防將之前產生但未留低的預測錯列成可用。
- `ops/tests/test_shadow_eligibility_diagnostics.py`：正向、缺開波時間、歷史不足、無賽程、錯 HK 日期、無時區、時間倒流、模型輸出不擅自升級投注，以及實際 `generate()` 六聯賽整合回歸。

## 安全界線與局限
- 本 PR **不增加一場真實賽事的預測覆蓋**、不補造任何 kickoff、不把單一來源賽果升為雙來源認證，也無法解決供應商額度問題。
- `prior_finished_score_rows` 只係觀察到嘅「row 數」，不是唯一賽事數，更不是兩個獨立來源確認的結算個案；即使 ≥30 亦不表示能形成有效訓練集。
- `NO_ELIGIBLE_PRECISE_KICKOFF_ROWS` 可以包含多種時間／資料品質不合格原因；須看個別數字，不可直接判斷全部來源都有錯。
- 每場模型仍未獨立校準，沒有已驗證可執行報價，正 EV、CLV、ROI 都未獲核實。
- 所有場次 `production_recommendations=DISABLED`，研究輸出 `HOLD / SHADOW_ONLY`，**不落注、不解鎖投注**。

## 驗收
```bash
python -m compileall -q ops
python -m unittest discover -s ops/tests -p 'test_shadow_eligibility_diagnostics.py' -v
python -m unittest discover -s ops/tests -p 'test_shadow_forecast.py' -v
python -m unittest discover -s ops/tests -q
```

合成測試成功只證明診斷不改動模型輸出，並非已取得五聯賽今晚新的預測。完成 PR CI、非作者獨立 review，再決定下一個**具授權真實賽前輸入**嘅接駁工作。保留 Draft 直至覆核。

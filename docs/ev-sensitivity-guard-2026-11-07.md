# 足球王者：多模型 EV 敏感度及排序防誤導修復（2026-11-07）

## 缺陷

既有 `ops/all_market_screen.py` 會顯示單一五結果分布計得的 `ev_per_unit`，並按 EV 大細將未獨立認證的 RESEARCH_ONLY 候選排序。當外部模型對同一亞洲讓球／大小球方向有重大分歧，正數 EV 容易被誤讀成信號。模型概率及賠率未認證、身份未核實、報價已過期等情況，原有正式推薦狀態雖然維持 DISABLED，研究排序仍可能引起誤解。

## 修正

- 新增純本地 `ops/ev_sensitivity.py`，用每單位投注的五結果（全贏、贏半、走盤、輸半、全輸）淨回報計算。
- `model_scenarios` 可提供不同 `model_id` 的同一市場/方向/線結果分布；最少兩組且必須完整、有效、互不重複。
- 呈現 `scenario_ev_min`、`scenario_ev_max`、`scenario_count` 及 `ev_sensitivity_status`：
  - `SCENARIO_SIGN_CONFLICT`：有模型估計正 EV，亦有模型估計非正 EV。
  - `ALL_SUPPLIED_SCENARIOS_NUMERICALLY_POSITIVE`：所有**用戶提供**情景數值為正，**唔代表獨立模型、統計置信區間或可下注認證**。
  - `NO_POSITIVE_NUMERIC_EDGE_IN_SCENARIOS`：全部非正。
  - `NOT_ASSESSED`、`INSUFFICIENT_SCENARIOS`：數據不足時不顯示情景區間。
- 非法模型 ID、缺失機率、重複情景、非有限機率、總機率不是 1，直接 `INVALID` 並禁止輸出研究 EV。
- `RESEARCH_ONLY` 不再按未驗證 EV 由高至低排序，改為穩定賽事／市場／方向排序。
- `positive_ev_verified` 恆為 false；禁止把情景範圍當做 95% CI、樣本外優勢或正式下注推薦。**不增加任何網絡請求或賠率來源，唔修改現有投注安全開關**。

## 驗收

新增七項 `tests/test_all_market_screen.py` 專項回歸：
1. 相同價格下兩個模型 EV 正負相反。
2. 全部提供情景為正，但不得變成正式 VERIFIED_VALUE。
3. 缺乏多模型情景時不能顯示 robust edge。
4. 只得一組情景時禁止顯示 min/max。
5. 重複模型、錯誤形狀、NaN/boolean/概率總數錯誤等拒絕。
6. 全部非正 EV 的情景不能提升資格。
7. 將正數未認證單點 EV 排首位的排序問題修正。

建議 CI：
```sh
python -m compileall -q ops
python -m unittest tests.test_all_market_screen -v
python -m unittest discover -s tests -q
python -m unittest discover -s ops/tests -q
```

## 不在本次改動範圍（依然 HOLD）

- 未取得獨立認證、授權及有逐筆時間戳的可成交大小球／讓球原始報價。
- 本次輸入的模型情景可能同源或存在資料洩漏；`scenario_ev_min/max` 並非 OOS 置信區間。
- #451/#453 亞洲四分之一盤等研究 PR、#454 收據時間驗證、#455 市場覆蓋報告仍待審核/合併。
- Issue #439：main branch 仍未完成保護及獨立人手 review；此 PR 不得繞過門禁合併或啟用投注。

**真實預測率及盈利無任何新增驗證證據。**

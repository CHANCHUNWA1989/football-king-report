# 足球王者｜OU2.5 偏差校準 Challenger 未通過樣本外驗證（2026-11-16）

## 本輪發現

上一輪 2,380 場跨聯賽回放：原版A預期入球推導之全場大2.5 Brier
0.24504，訓練年度頻率基準0.24455；原模型唔可以當成已證實較佳大小盤模型。

本輪提出**事先固定、無使用測試賽果調參**的簡單修正候選：

1. 用第 t-2 球季真實比分擬合原版A六場平滑入球率，產生 t-1 球季大2.5預測。
2. 用 t-1 球季預測與完場大2.5結果擬合 **單一帶 L2=25 正則化 logit 截距**，無球隊／盤口針對性調參。
3. 原版入球模型以 t-1 球季重新擬合，但**只使用已驗證在 t 球季之前的比賽結果**，對 t 球季未知場次預測。
4. 將步驟2預先擬合的截距固定套用到 t 球季預測，使用同樣全部合資格比賽比較原版／Challenger／更早訓練賽季固定頻率基準。
5. 有缺漏的整個訓練／驗證／測試球季直接排除；保留現有 ≥5 次出場門檻；對應資料未必已獲獨立校驗及實際開賽前封存。

資料來源：OpenFootball `football.json` Git commit
`e6744429ee395bc86f247348c6184bb08d4eb361`；
2022/23至2025/26英超、德甲、西甲、意甲及法甲。固定來源只使歷史重現有依據，**唔等於賽前簽署預測**。

## 逐季實際回放：嚴格日期切割、5組、1,234場

| 聯賽 | 測試球季 | 驗證數 | 測試數 | 原版大2.5 Brier | Challenger Brier |
|---|---|---:|---:|---:|---:|
| 英超 | 2024/25 | 272 | 272 | 0.25085 | 0.26857 |
| 英超 | 2025/26 | 272 | 272 | 0.24504 | 0.25000 |
| 德甲 | 2024/25 | 240 | 240 | 0.23570 | 0.23598 |
| 德甲 | 2025/26 | 240 | 240 | 0.24323 | 0.24345 |
| 法甲 | 2024/25 | 90 | 210 | 0.25388 | 0.25623 |
| **合計（按場數加權）** | | | **1,234** | **0.24566** | **0.25116** |

訓練賽季固定大2.5頻率基準約 **0.24218**（Brier越低越好）。
五組都**冇**證明簡單校準優於原版；候選模型反而更差，
不應以這個回放事後決定新權重再在同批測試數據聲稱提高準確率。

西甲、意甲2024/25訓練／測試相關球季資料不足完整380場，
法甲2025/26公開資料少於完整306場，依照固定完整賽季規則排除。

## 本 PR 改進

- 新增 `ops/ou25_shadow_calibration_veto.py`，只做 **離線Shadow** 校準與配對評分；
  不能改A/B/C封存概率，不能輸出真實可成交賠率或自動下注。
- Validation 與 test 必須至少各80場、賽事 ID 不可重複、
  validation 最後日期嚴格早於 test 第一日；基準訓練結束日期早於 test。
- 只使用 validation 結果擬合截距；test 結果只做 Brier／logloss 評分。
- Challenger Brier 較原版差時輸出 `REJECT_WORSE_THAN_ORIGINAL`；
  就算較好，仍維持 `HOLD_INDEPENDENT_FORWARD_ATTESTATION_REQUIRED`。
- 固定 `eligible_for_promotion=false`、`production_recommendations=DISABLED`、
  `betting_ev_verified=false`、`source_and_result_independently_authenticated=false`。
- 新增8個回歸測試，涵蓋異常值、資料洩漏、重複賽事、未來基準及不改原資料。

## 可重現CLI（資料須由合法且可獨立驗證之來源預備）

```bash
python -m ops.ou25_shadow_calibration_veto \
  --validation validation.json \
  --heldout heldout.json \
  --baseline baseline.json \
  --source-revision e6744429ee395bc86f247348c6184bb08d4eb361 \
  --output shadow_research.json
```

驗證與測試每個 JSON 陣列元素：
`{"league":"epl","fixture_id":"stable-source-id","match_date":"2025-01-01","original_over25_probability":0.55,"actual_over25":1}`，
欄位值只係**結構示例**，不是實際比賽紀錄。Baseline JSON：
`{"probability_over25":0.55,"training_end_date":"2024-12-31","sample_count":380,"source":"pinned-training-data"}`。
上述時間來源皆屬自報，不能當成可追溯賽前封存。

## 未完成

1. 尚缺有獨立時間戳與來源權利的真正前瞻 OU2.5 預測、雙來源完場比分；
2. 未有兩邊同時間可成交的大小盤賠率，未能驗證真實EV、ROI、CLV；
3. 尚未完成多市場 Poisson／Dixon–Coles 配對樣本外測試；
4. 不能從這個不通過的 Challenger 推論更複雜方法必然成功；
5. 此 PR 不合併、不啟用正式推薦，維持 HOLD／DISABLED。

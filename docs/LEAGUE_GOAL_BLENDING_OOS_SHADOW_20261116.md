# 足球王者｜分聯賽大小球固定混合概率研究（2026-11-16）

> **研究模式，從未授權實盤推薦。** 新固定25%混合方式係睇過歷史結果之後先形成的**探索性候選**。即使同一批資料 Brier 降低，也唔可以當成真正未見資料的獨立模型效能證明。保持 `HOLD / DISABLED`、永不自動放行。

## 已知問題及固定研究規則

上一輪2,380場完整賽季歷史回放發現原版A入球率推導的大2.5概率未跑贏訓練年度固定大球比例。

新**研究候選**：
- 資料來源：OpenFootball `football.json` 公開倉庫，固定 Git SHA：
  `e6744429ee395bc86f247348c6184bb08d4eb361`（版本固定不等於獨立來源簽署）。
- 以**上個完整球季**真實完場比分計算該聯賽大2.5、BTTS比例；使用 Jeffreys 平滑：`(positive + 0.5) / (training_games + 1)`。
- 以同一個更早球季數據擬合原版A六場 shrinkage Poisson 預期主/客入球，對下一完整球季日期切割比賽作回放。
- 大2.5 候選固定為 `0.75 * Poisson_Over25 + 0.25 * PreviousSeasonLeagueOver25`。
- BTTS獨立報告同一固定混合的診斷，但**不可以由大2.5改善推論 BTTS 同樣改善**。
- 只對比相同賽事的原版、訓練固定比例及混合 Brier。未含莊家開盤價、收盤價、實盤 ROI 或可核實EV。
- 如訓練／測試球季比賽場數或單隊主客場出場數不完整，該整個 cohort 排除。

## 實際探索性跨季回放結果

下表按場次加權；來源至 2026-05 結束的歷史賽季；原版A入球率重現需再核對源程式版本。

| 市場 | 原版A Brier | 訓練期固定比例 Brier | 固定25%混合 Brier | 結論 |
|---|---:|---:|---:|---|
| 大2.5 | 0.24504 | 0.24455 | **0.24273** | 歷史探索性結果較好 |
| 雙方入球是 | 0.24837 | **0.24548** | 0.24623 | 混合不優於弱基準 |

包含英超3組、德甲3組、西甲1組、意甲1組、法甲2組，合計 **10組、2,380場**。大2.5混合在7組優於原版A，但只有部分組別跑贏上一訓練季的固定頻率。

**不可事後用這10組選出更佳權重、然後宣稱仍係未見數據成績。** 25%候選曾經接觸這批歷史結果，必須先在未來真正新場次、固定賽前數據及來源完成獨立驗證。

## 新增研究程式與防資料洩漏關卡

`ops/league_goal_blend_shadow.py`：
1. 輸入完全分開的訓練/測試 JSON，每行獨立 league、fixture_id、match_date；
2. 訓練與測試不得有重複賽事，訓練最遲日嚴格早於測試最早日；
3. 不容許布林比分、NaN/Inf入球率、錯聯賽、重複跨組測試賽事；
4. 訓練期大2.5及BTTS先驗只從訓練期比分計算；測試期結果僅供Brier/Logloss計分；
5. 即使混合Brier較低，也固定 `eligible_for_model_promotion=false`、`status=HOLD`、`production_recommendations=DISABLED`；
6. `expected_home_goals` 和 `expected_away_goals` 都係**歷史重建/外部提供的研究輸入**，程式本身唔能證明它們於賽前已封存，亦不能假裝官方核實賽果。

CLI：
```bash
python -m ops.league_goal_blend_shadow --input research_cohorts.json --output goal_blend_shadow.json
```

輸入例子（純結構示例，並非真賽果）：
```json
{
  "source_revision":"e6744429ee395bc86f247348c6184bb08d4eb361",
  "folds":[{
    "league":"epl",
    "test_season":"2025-26",
    "training":[{"league":"epl","fixture_id":"provider:train-1","match_date":"2025-05-01","home_goals":1,"away_goals":0}],
    "heldout":[{"league":"epl","fixture_id":"provider:test-1","match_date":"2026-05-01","home_goals":2,"away_goals":1,"expected_home_goals":1.5,"expected_away_goals":1.0}]
  }]
}
```
實際程式最低要求每組訓練30場、測試20場。示例只有一筆所以應被拒絕。

## 固定真實賽果重現流程（新增）

`ops/league_goal_blend_real_replay.py` 利用固定的 OpenFootball 原件 Git SHA，讀取五大聯賽
2022/23–2025/26 每場已完場比分，檢查每個球季總場數、主客場場數、對賽唯一性；不完整季別整組排除。
然後對**上一完整球季以後**的每個目標比賽日，使用現有
`ops.shadow_forecast.predict_league`，只把訓練季比分傳入模型，目標日比賽一律 `score_ft=None`，
重新得到當年的主客預期入球。正式賽果只在模型輸出之後用作 Brier/Logloss 評分。

```bash
python -m ops.league_goal_blend_real_replay --output /tmp/league-goal-blend-real.json
```

**重要：** 由於來源無原始真實逐場開賽UTC時間，程式使用**虛構23:00香港時間**
僅作為歷史模型API適配器，絕不表示當時真正開賽時間或當日曾實際封存預測。
賽事識別碼亦只係本地導出，用於避免重複，絕不是比賽供應商原生ID。
CI會將固定公開原件每個JSON SHA256納入輸出，拒絕不完整球季，並要求
10組、2,380場同 `HOLD/DISABLED` 均符合檢查。

## 驗收與未完成

- 必須跑全套ops/tests、原版117測試、compileall、安全回歸；對安全及比分不作任何重新放行。
- 必須有獨立複核，保留Draft PR，不合併至 main。
- **未完成**：真實賽前凍結概率、OpenFootball之外第二獨立賽果來源、資料原件及權利、球隊身份固定ID、真實大小盤公司與報價時間、Brier信賴區間、CLV／ROI／EV；亦未完成真正未見過的全新前瞻 holdout。

## 研究結論

今次改進只係讓系統**正式識別並評分一個有初步前景的大小球候選**，並同 BTTS 弱點分開；不是已證明可實盤投注，亦不是對原版 A/B/C 模型的線上改動。

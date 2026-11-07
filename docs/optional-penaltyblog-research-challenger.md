# 可選 Penaltyblog 離線挑戰模型（研究專用）

本 PR 新增 `ops/penaltyblog_research_bridge.py`：只讀**使用者已持有且有權使用的離線歷史賽事**，可選用上游 `PoissonGoalsModel` 或 `DixonColesGoalModel`，回傳未認證 1X2 研究概率。**不修改原有 A/B/C、固定 Dixon-Coles 候選、封存預測、網站或自動採集流程。**

## 上游與可選安裝

- [Penaltyblog](https://github.com/martineastwood/penaltyblog)，MIT 授權；使用其公開 Python API，不複製原始碼。
- 可在獨立研究環境自行安裝指定版本：`python -m pip install 'penaltyblog==1.13.1'`（上游 2026-10-05 版本）。本 PR **不自動安裝**、不改既有 CI 依賴；缺少套件時 `HOLD / OPTIONAL_PENALTYBLOG_NOT_INSTALLED`。
- `SoccerData`（[專案](https://github.com/probberechts/soccerdata)）尚未自動接駁；使用 FBref、Understat 等來源前，必須核對資料權利、抓取條款、更新時間及原生賽事／球隊 ID，不能直接混合成已認證證據。

## JSON 輸入結構

頂層必須有 `schema=football-king-penaltyblog-offline-input-v1`、`production_recommendations=DISABLED`、`model=poisson`（亦可 `dixon_coles`）、`as_of_utc`、`target_fixture` 和 `historical_matches`。

`target_fixture` 只接受 `source_namespace,event_id,league_id,home_team_id,away_team_id,kickoff_utc`，不得有比分欄位。每筆歷史賽事須有同樣身份欄位，加上 `result_recorded_utc,home_goals,away_goals`。

- 所有訓練紀錄須與目標同一來源 namespace、同一聯賽；只以來源原生 ID 配對，**不按中文／英文球隊名稱猜測合併**。
- 最少 30、最多 2500 場合資格歷史賽事，目標兩隊各至少 5 場歷史紀錄；重複 event ID 或同場同時刻紀錄拒絕。
- 必須嚴格滿足 `historical kickoff < result_recorded_utc < as_of_utc < target kickoff`，一筆未完場、未能按截止時間獲得的賽果即 HOLD。
- 所有截止時刻、供應商來源及賽果仍由輸入方提供，**未經外部獨立認證**；合成測試通過不等於真人賽事或模型盈利優勢。不要把結果注入原 A/B/C 封存。

執行（隔離環境，純離線）：

```bash
python -m ops.penaltyblog_research_bridge --input research-input.json --output new-research-report.json
python -m unittest ops.tests.test_penaltyblog_research_bridge -v
```

報告使用只建立新檔、不覆蓋舊檔嘅安全寫入。模型可執行時只輸出 `RESEARCH_ONLY` 概率、ID、樣本數以及 `positive_ev_verified=false`；缺套件、無效資料或擬合異常均 `HOLD`，不輸出投注價、ROI 或 EV。**正式推薦永久維持 `DISABLED`，直到另有合資格獨立研究及人手審核。**

## 下一步

建立合法來源數據的獨立 ID 及時間證據，再於相同賽事、相同賽前資訊截止時間比較新候選與現有模型的 Brier、Log Loss 及校準。未有獨立封存、真實來源、可成交賠率和 `main` 分支保護 Issue #439 前，不合併／部署任何安全敏感推薦功能。

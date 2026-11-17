# 可選 Penaltyblog 離線挑戰模型（研究專用）

本 PR 的 `ops/penaltyblog_research_bridge.py` 只讀**使用者已持有且有權使用的離線歷史賽事**，可選用上游 `PoissonGoalsModel`、`DixonColesGoalModel` 或 `BivariatePoissonGoalModel`，回傳未認證 1X2 研究概率。**不修改原有 A/B/C、固定 Dixon-Coles 候選、封存預測、網站或自動採集流程。**

## 上游與可選安裝

- [Penaltyblog](https://github.com/martineastwood/penaltyblog)，MIT 授權；使用其公開 Python API，不複製原始碼。
- 可在獨立研究環境自行安裝指定版本：`python -m pip install 'penaltyblog==1.13.1'`（上游 2026-10-05 版本）。本 PR **不自動安裝**、不改既有 CI 依賴；缺少套件時 `HOLD / OPTIONAL_PENALTYBLOG_NOT_INSTALLED`。
- `SoccerData`（[專案](https://github.com/probberechts/soccerdata)）尚未自動接駁；使用 FBref、Understat 等來源前，必須核對資料權利、抓取條款、更新時間及原生賽事／球隊 ID，不能直接混合成已認證證據。

## JSON 輸入結構

頂層必須有 `schema=football-king-penaltyblog-offline-input-v1`、`production_recommendations=DISABLED`、`model=poisson`（亦可 `dixon_coles` 或 `bivariate_poisson`）、`as_of_utc`、`target_fixture` 和 `historical_matches`。

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

## 雙變量 Poisson 研究候選 — 2026-11-17

- 重用 MIT Penaltyblog 1.13.1 公開 API：[`BivariatePoissonGoalModel`](https://github.com/martineastwood/penaltyblog/blob/v1.13.1/penaltyblog/models/bivariate_poisson.py)。沒有複製上游源碼或增加套件依賴。
- 其假設為 `H=W1+W3, A=W2+W3`，三個 W 為獨立 Poisson；共享成分可描述非負入球相關性。不能描述負協方差，亦沒有因此證明優於獨立 Poisson／Dixon–Coles。
- 同一輸入結構改用 `model=bivariate_poisson`，成功時得到獨立 ID `penaltyblog-bivariate_poisson-offline-challenger-v1`；原有來源 namespace、原生 ID、聯賽、最少歷史樣本、可用時間、概率及安全寫入規則全部保留。
- 此階段只接單模型離線入口。`PAIRED_MODELS` 明確保留 Poisson／Dixon–Coles；既有雙模型前瞻封存、走步比較及時間衰減契約沒有自動擴大。
- 標準庫單元測試使用假模型，只驗接線及拒收行為；既有 real-dependency CI smoke 改為對全部註冊候選，以固定 `penaltyblog==1.13.1` 真正擬合合成資料。兩者都不是實戰盈利證據。
- 缺套件／擬合失敗／來源不符／截止後賽果／非法概率仍 HOLD；無賠率、EV、ROI、注碼或自動晉升。正式替換仍須授權真實資料、獨立封存／賽果及真人審核。

### 本輪交接（2026-11-17）
- 範圍：只新增可選雙變量 Poisson 離線候選；原雙模型流程不變。
- TDD：57項相關測試先出現5個失敗案例，接線後57項通過。
- 完整回歸：2,914項，零失敗；2項因本地缺 penaltyblog／soccerdata 跳過。
- compileall、git diff --check 通過；一次只讀助理覆核無阻擋問題，並非真人發布批准。
- 真套件擬合由既有固定版本 CI 驗證；最新 HEAD 結果見 Draft PR #458，未通過前不算驗收。
- 狀態：HOLD／DISABLED、positive_ev_verified=False；#439／#452及獨立真人審核仍阻塞正式替換。

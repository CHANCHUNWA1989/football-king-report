# 真實公開賽果：英超歷史研究樣本（2026-11-17）

本包已取得並保存 OpenFootball 英超2023/24、2024/25各380場、共760場實際賽果紀錄，重用現有 Poisson v2、近似 Dixon–Coles v5及歷史頻率基準作離線走步診斷。**已認證賽前樣本仍為0；正式推薦 HOLD／DISABLED、positive_ev_verified=False。**

## 來源、權利及身份

- 固定上游提交：[`e6744429ee395bc86f247348c6184bb08d4eb361`](https://github.com/openfootball/football.json/tree/e6744429ee395bc86f247348c6184bb08d4eb361)。原始兩季 JSON及當時 README 完整存於本目錄，SHA-256、來源 URL與檔案大小見 `provenance.json`。
- 上游 README 的 License 段落明確將 schema、資料及腳本奉獻公有領域，容許無限制使用。`UPSTREAM_README.md` 保存原文；這是上游權利聲明，不是獨立法律或賽果認證。
- `matches.csv` 只轉錄日期、球隊原文及 `score.ft`；`SourceSeason`／`SourceRow` 指向原 JSON 陣列位置。CSV行號只是本地診斷識別，**不是供應商原生賽事ID或跨來源身份映射**。球隊名稱不是跨供應商配對證據。
- 原始 `time` 欄位不作UTC推斷。CSV匯入的午夜只是日期標記，`kickoff_utc=None`、時間核實旗標為False；沒有補造歷史發布、擷取或賽前預測時間。
- CSV入口新增明確 `--source openfootball.football_json`，並由走步及manifest保留該來源；原有預設仍為 `soccerdata.MatchHistory`。來源名稱不會使資料自動獲認證；未知／混合來源拒收。

## 本次預先固定的流程

`experiment.json` 在本次計算分數前寫入：初始訓練為2023/24的380場，之後在2024/25按每一個有比賽的日期向前走步；每個日期只用更早日期的賽果。預設收縮、頻率平滑及rho網格沒有根據本次評估分數調整。較早評估日會進入後續訓練。

共109個評估日期、380場評分，訓練／測試無重疊，同日賽果不進入訓練。**這些是歷史重建的時間切分診斷，沒有當年資料可用時間的獨立證據；亦不保證這兩季從未在過往開發中被看過。** `experiment.json` 並非歷史賽前封存或獨立預註冊。

| 模型 | Log Loss | 多類Brier（H/D/A平方誤差之和） |
| --- | ---: | ---: |
| 歷史頻率基準 | 1.082314 | 0.656344 |
| 擬合球隊Poisson v2 | 0.997205 | 0.595663 |
| 近似Dixon–Coles v5 | 0.996683 | 0.595359 |

分數越低越好；完整結果及模型ID見 `comparison.json`。頻率基準不是市場賠率基準。沒有計算本包的校準誤差或信賴區間，不能把分數差當成統計顯著優勢、準確率提升或正EV。此處DC為兩階段近似修正，不是聯合最大似然估計。

## 重現

於本研究分支的儲存庫根目錄執行（不下載、不用密鑰）：

```bash
python -m ops.private_soccerdata_three_model_csv \
  --csv research/datasets/openfootball-epl-20261117/matches.csv \
  --source openfootball.football_json --min-train 380 --test-days 1
```

輸出的JSON應與 `comparison.json` 相等。原始到CSV的轉換規則為：依2023/24、2024/25順序讀取 `matches`，從每項提取 `date,team1,team2,score.ft[0],score.ft[1]`，另保留季份及原陣列索引；按日期、主隊、客隊排序，寫出UTF-8、LF換行的標題 `Date,HomeTeam,AwayTeam,FTHG,FTAG,SourceSeason,SourceRow`。沒有丟棄賽事、增補比分或模擬觀測。

`provenance.json` 保存六個輸入／設定／結果檔的原始雜湊與逐折日期／數量。雜湊只驗內容一致，不證明來源真實或當年已可取得。

## 尚欠的正式證據

真正前瞻樣本須由現在起，在開波前封存模型版本、訓練截止、概率及獨立時間證據，再配對已授權的實際盤口和獨立FT90結果。仍欠：逐筆博彩公司／盤口／方向／線／賠率及真實UTC更新／擷取時間、可信原生ID映射、獨立賽前封存與賽果、未經挑選的前瞻評估、市場基準／校準／不確定性，以及 #439 與真人審核。#452 保持未解除，沒有支付API或購買資料。

新增的可選雙變量Poisson入口要求明確UTC及歷史結果可用時間，本包只有日期，**不能送入該入口冒充合資格資料**；本次沒有訓練或評估該候選，也沒有更改A/B/C封存、正式模型設定、合併或部署。

## 本輪交接
- 完成：760場原始賽果及來源聲明封裝；380場、109折歷史走步診斷可重現。
- 修正：既有CSV／manifest保留明確OpenFootball來源，拒絕未知或混合來源。
- TDD：來源／CLI新案例先拒收，再修正；完整回歸2,921項，零失敗、2項可選套件跳過。
- 驗證：六檔雜湊、逐筆來源對照、逐折日期、重現結果、compileall及diff檢查通過。
- 一次只讀助理覆核無阻擋問題；不是獨立真人來源／發布認證。
- 下一步：取得已授權逐筆UTC盤口、獨立賽前封存及FT90；#439／#452維持阻塞，HOLD／DISABLED。

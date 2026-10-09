# 免費足球 API 真正覆蓋與下一步驗證｜2026-10-09

## 現有實際資料快照（GitHub main）

| 原有層 | 已確認或缺口 |
|---|---|
| `sources/latest.json` | TheSportsDB 53 個抽樣賽事；API-Football 已設定但 0 筆且 HOLD；football-data.org、Sportmonks 尚缺 Key |
| `sources/wide_latest.json` | OpenFootball／OpenLigaDB 合共 30 個資料批次 FETCHED |
| `market/latest.json` | The Odds API 120 條無水研究用市場項目；不是可下注報價 |
| `sources/weather_latest.json` | MET Norway 六城市預報成功 |
| `sources/research_extensions_latest.json` | StatsBomb 歷史目錄可用；OpenFootAPI 尚缺 Key |

不同 JSON 的擷取時間與統計口徑各異，不可將 53、30、120 直接相加當獨立賽事數。

## 新增零 Key 三類研究能力：10 個初始查詢，最多 13 個含備援

1. [TheSportsDB V1](https://www.thesportsdb.com/docs_api_guide) `lookuptable.php` — 六大聯賽，固定六次；**免費版最多五個球隊排名**，並非全聯賽榜。來源與既有 TheSportsDB 賽程屬同一供應商，不可當獨立賽果驗證。
2. [OpenLigaDB 官方 API](https://github.com/OpenLigaDB/OpenLigaDB-Samples) `getbltable` — 德甲、德乙、德丙各一個表格查詢。2026-10-09 真實運行發現三個回傳空陣列；已加入最多三次 `getmatchdata/{bl1|bl2|bl3}/{season}` 備援，只統計社群來源已完賽比分推導的球隊覆蓋，絕不假稱官方積分榜、跨源獨立驗證或賽前可用數據。
3. [Figshare 公開 API](https://docs.figshare.com/old_docs/api/collections/) `/v2/collections/4415000/articles?page_size=10` — 每次只擷取最多十個文章**目錄**作 2017/18 Wyscout 歷史傳射犯規研究索引；絕不抓數十 MB 的大型原始事件檔、不假稱當季即時球員狀態或現代 Wyscout 商業 API 免費。原研究資料：[Pappalardo 等 Figshare 歷史足球事件](https://figshare.com/collections/Soccer_match_event_dataset/4415000)。

所有資料只保留 `status`、`league`、有效紀錄**數量**、擷取 UTC、錯誤類別，不存原始賽事、表格、球員／博彩公司私人資料或 API Key。

### 執行方式

- `ops/free_football_depth.py`：初始十個、德國表格回空時最多額外三個、**全週最多 13 個 HTTP GET**（遇 429 停止同源請求），不調整主模型、資料封存或賠率。
- `.github/workflows/football-king-free-depth.yml`：每週一 UTC 04:41 執行；程式首次 merge 到 main 亦會執行一次。顯示 GitHub Action 成功，不代表該 provider 給出有效數據；要睇 artifact 內 `valid_sources` 同 `observations`。
- `ops/tests/test_free_football_depth.py`：無網絡、模擬固定回應、429 停用、無料可用時保留 HOLD，防止五隊免費榜單被冒充完整聯賽榜。
- 始終 `production_recommendations=DISABLED`，`current_team_probabilities_unchanged=True`。
- 真正接入任何模型特徵，先要按照捕獲時間點、球隊 ID、與已有源是否重複、跨週和聯賽樣本外 Log Loss/Brier、Shadow Mode 的預先註冊增量驗證。

## 拒絕為了增加數量而重覆／違規

- football-data.co.uk 網站免費 CSV 係私人研究下載，不允許用於商業或 AI 自動訓練／批量抓取。未獲書面授權，不設自動採集流程：[原始條款](https://football-data.co.uk/data.php)。
- ClubElo 舊公開 CSV API 已有近期停用報告，未核實恢復，不當作穩定免費來源。
- 商業 Wyscout API 與 Figshare 的 **2017/18 歷史公開研究資料**不可混淆。
- 按目前實際資料，傷停、預測正選、球員 xG、可執行即時賠率仍係根本缺口；更多積分榜 API 唔會自動填補。

## 2026-10-09 實際修復及上游驗收

- 舊版：7/10 初始研究查詢有有效資料，其中德國聯賽榜 0/3。
- 修復後：[GitHub Actions run 37936654205](https://github.com/CHANCHUNWA1989/football-king-report/actions/runs/37936654205) 真實取得 **10/10** 已驗證研究觀察；本輪使用 **13 次**無 Key 請求，當中德國 3/3 只屬來源社群比分推導之非官方統計。
- 完整原版回歸及 1,500 場合成壓力測試：[run 37936654326](https://github.com/CHANCHUNWA1989/football-king-report/actions/runs/37936654326) 通過。
- 新每日自動健康報告：[run 37936654199](https://github.com/CHANCHUNWA1989/football-king-report/actions/runs/37936654199)：**18 場未開賽前瞻封存、0 場超時未結算、0 場有效已結算樣本**。因此必須 HOLD；不能聲稱現時已知模型勝率、準確率或正 EV。
- 已加入壓縮歷史檔解壓大小限制（8 MB）、每檔樣本上限、舊資料時間／概率／賽果衝突驗證。正常存量保留，不會擅自更新原有賽前概率。
- 原網站更新、封存流程：[run 37936654269](https://github.com/CHANCHUNWA1989/football-king-report/actions/runs/37936654269) 通過。

**未完成：** 可靠即時傷停、首發正選、獨立六大聯賽賽果及合法可執行的賠率，仍需來源權利、配額及樣本外研究支持。CI PASS 不等於盈利能力。

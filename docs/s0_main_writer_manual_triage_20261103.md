# 足球王者 S0｜16 條存檔／寫入風險候選逐條核對（2026-11-03）

**基準：公開 GitHub 主分支 `70f14b400487921b0cc58ba22156bbe661755aaf`，`protected=false`。本報告記錄已讀取嘅 workflow 程式碼，唔係實際排程執行或完整 YAML/腳本依賴證明。仍然要獨立審核。**

## 實際發現

掃描原先辨識 **16 條有 GitHub 寫入權限或 mutation 指令嘅 workflow**。逐份核對原始 workflow 後：
- **15 條有明確 GitHub repository contents API PUT 或推送 `refs/heads/main` 程式路徑**。其中 Contents API 既有版本未指定 `branch` 時，按照儲存庫預設分支 `main` 執行（實際授權、條件、是否成功寫入仍要由運行日誌驗證）。
- **1 條 `purge-unsafe-market-artifacts.yml` 只係使用 `actions: write` 以 GitHub API 刪除特定舊 Actions artifact**，並冇對程式庫 `main` 寫入檔案；唔應該錯當「第 16 條 main 寫入者」。需保留該安全清理用途，唔可以為咗減少數量直接刪除安全流程。
- 兩條高風險工作流程（`football-king-iphone.yml`、`four-model-shadow-daily.yml`）明確有 `git -C "$worktree" push origin HEAD:refs/heads/main` 類操作；原版簡單 `git push` 正則可能漏檢 `-C` 形式，已在 PR #381 增加識別。
- 另有「直接從 workflow 引用嘅 Python 程式」潛在 mutation 指令，屬**待確認候選**；無法由單純文字出現次數證明嘅流程身份、方向及存取權限。

## 逐流程指向與已見到嘅消費者

| workflow | 程式碼中嘅寫入對象（非執行證明） | 已確認讀取／風險 | 遷移優先級 |
|---|---|---|---|
| `football-king-bsd-free.yml` | `sources/bsd_history/*`、`sources/bsd_status_latest.json`、有市場時 `sources/bsd_market_latest.json` | `football-king-iphone.yml` 直接讀 BSD 兩份 latest；Draft #382 已同步改 writer+reader，但未合併、未做真實 canary | **首個試點 P0-A** |
| `football-king-weather.yml` | `sources/weather_history/*`、`sources/weather_latest.json` | iPhone workflow `ops/met_weather_overlay.py` 直接讀 latest | P0-B |
| `football-king-japan-free-market.yml` | `market/japan_free_status.json` | iPhone workflow `ops/japan_market_overlay.py` 直接讀 latest | P0-B |
| `football-king-research-extensions.yml` | `sources/research_extensions_history/*`、`sources/research_extensions_latest.json` | iPhone workflow 直接讀 latest | P0-B |
| `football-king-wide-free.yml` | `sources/wide/history/*`、`sources/wide_latest.json` | iPhone workflow `ops/wide_overlay.py` 直接讀 latest | P0-B |
| `football-king-asia-apis.yml` | `sources/asia_api_latest.json` | 未在 iPhone workflow 直接用呢個字面路徑確認 consumer；須核對嵌入 JS/其他腳本 | P0-B，需要查明 reader |
| `football-king-german-live.yml` | `sources/live_germany/history/*`、`sources/live_germany_latest.json` | iPhone workflow 未見直接字面讀取；須查網頁 JS 動態讀取／網站刷新 | P0-B，需要查明 reader |
| `football-king-hkjc-free-research.yml` | `sources/hkjc_tipsme_free_latest.json` | 未確認公開頁面 reader；可作獨立元數據存檔，但唔可擅自刪除 | P0-B，需要查明 reader |
| `football-king-six-free-upgrade.yml` | `sources/six_league_quality_history/*`、`sources/six_league_free_latest.json`、`sources/seven_quality_gates_latest.json`、`sources/six_league_fixture_overlap_latest.json` | iPhone workflow 直接讀 `seven_quality_gates_latest.json`；其他 reader 要追索 | P0-C |
| `football-king-secondary-sources.yml` | `sources/history/*`、`sources/latest.json` | iPhone 多個步驟讀 `sources/latest.json`，亦用於結算及模型資料 | **高風險 P0-D** |
| `football-king-odds.yml` | `market/history/*`、`market/collection_status.json`、`market/latest.json` | iPhone `market_pair.py`、`league_coverage.py`、研究評估均讀 `market/latest.json`；要保住時間先後及配額限制 | **高風險 P0-D** |
| `private-all-market-research.yml` | `market/private_summary_latest.json`（安全聚合，唔係原始私人盤口） | iPhone 觸發及 Pages 讀取依賴；禁向公開 main/branch 洩漏原始商業盤口 | **高風險 P0-D** |
| `football-king-weekly.yml` | `reports/weekly/$REPORT_DAY.md` | `ops/weekly_digest.py` 讀 `evidence/settled.json`、`market/latest.json`；未見網站直接讀週報，需驗證實際消費者 | P0-C |
| `four-model-shadow-daily.yml` | NDR capture 及 OpenLigaDB capture 證據（helper 建立目的檔案），兩個 archive job 明確推送 `main` | 需要保留原始證據 hash、時間及跨工作流程驗證；遷移影響大 | **最後處理 P0-E** |
| `football-king-iphone.yml` | `forecast_provenance` 證據、研究快照及 `evidence/settled.json`；明確推送 main + Contents API PUT | 網站發布、研究封存與結算互相耦合，必須同步改全部 reader／triggers／回滾 | **最後處理 P0-E** |
| `purge-unsafe-market-artifacts.yml` | **Actions artifact DELETE，唔係 main contents 寫入**；固定 artifact ID 11668672186 並核對 name | 單次安全清除用途，唔應納入 main-archive 搬遷數目 | **獨立安全維護** |

### 有憑據嘅網站讀取關係

在主分支 `.github/workflows/football-king-iphone.yml` 可以直接找到：
- `sources/latest.json` → `ops/source_overlay.py`，以及多個 research、settlement 步驟。
- `sources/bsd_status_latest.json` + `sources/bsd_market_latest.json` → `ops/bsd_overlay.py`。
- `sources/weather_latest.json` → `ops/met_weather_overlay.py`。
- `sources/wide_latest.json` → `ops/wide_overlay.py`。
- `sources/research_extensions_latest.json` → 研究 extension overlay。
- `market/japan_free_status.json` → `ops/japan_market_overlay.py`。
- `market/latest.json` → `ops/market_pair.py` 與研究流程。
- `sources/seven_quality_gates_latest.json` → `ops/release_guard.py` 相關網站發布檢查。

呢啲係 workflow **明確字面路徑**；其餘 JS、Python 間接讀取、Python import、動態 gh api 路徑仍未全面證實。唔可以由「掃描見唔到」推斷「冇 consumer」。

## 遷移執行次序與停止條件

1. **先 #382 BSD 試點**：獨立 Reviewer 批准；喺受控免費配額下實際執行一次 collect→archive branch→iPhone Pages workflow_run，核對 ZIP artifact、archive/main commits、`as_of_utc`、`HOLD`、網站只讀來源。任何缺漏即停止，唔准默認回退 main。
2. **低耦合來源 P0-B**：每次只搬一組 producer+reader；測試新舊 branch 來源嘅最新快照排序、資料缺失保持 HOLD、網站刷新、權限最小化、canary 同回滾。
3. **中耦合 P0-C**：包含品質關卡／週報，同時核對其他 downstream；需要證明 reader 走新 branch。
4. **高風險 P0-D**：賠率／賽程／私人安全聚合，需要自動化、配額、期限、身份一致性及結算端到端演練；絕不搬出原始私人盤口。
5. **核心 P0-E**：四模型證據與 iPhone 發布封存最後處理；完成時再追蹤所有 writer 是否已隔離。
6. **最後才保護 main**：獨立 Reviewer、精確 commit CI／站點驗收、授權 branch protection API 讀回證據、禁止直接 push/force push，以及回滾演練。

### 明確未完成

- 以上靜態分析只證明寫入**程式路徑存在**，並非每條 workflow 近期都確實成功寫入 main；若要確證請逐條連到相應嘅 GitHub Actions 原始日誌及 commit。
- 未確認全部 Script/JS/間接 target，未取得獨立 Reviewer、未完成 #382 真實跨分支 canary。
- GitHub `main` 仍 `protected=false`，分支保護 API 對現有 integration 曾回覆 403，**唔可以謊稱已強制啟用**。
- `production_recommendations=DISABLED`、研究 `HOLD`；唔可以將測試/盤點當成正 EV 或前瞻模型認證。

追蹤：[總路線圖 #383](https://github.com/CHANCHUNWA1989/football-king-report/issues/383)｜[發布阻塞 #56](https://github.com/CHANCHUNWA1989/football-king-report/issues/56)｜[BSD 試點 #382](https://github.com/CHANCHUNWA1989/football-king-report/pull/382)。

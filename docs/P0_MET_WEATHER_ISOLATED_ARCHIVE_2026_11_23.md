# P0｜MET Norway 免費天氣封存：獨立分支 Writer + iPhone Reader（Draft / HOLD）

**日期：2026-11-23 HKT。** 只係研究中的程式候選，絕非正式更新或投注放行。

## 原本可核實的問題

原本 `.github/workflows/football-king-weather.yml` 的 `archive` job 有 `contents:write`，使用 `gh api -X PUT repos/$GITHUB_REPOSITORY/contents/...`，無顯式 `branch` 欄位；按 Contents API 會更新預設 `main`。更新目標包括 `sources/weather_history/YYYY/MM/DD/RUN-ATTEMPT.json.gz` 及 `sources/weather_latest.json`。嚴格啟用 main PR-only 前必須先移動 writer。

原本 `.github/workflows/football-king-iphone.yml` 同時有 `workflow_run` 聽天氣工作完成，但製作研究網頁時把 **checkout main** 的 `sources/weather_latest.json` 傳入 `ops/met_weather_overlay.py`。只移動 writer，reader 就會變成一直讀舊資料。天氣只為城市中心（並非球場實測）之非博彩研究，對勝率、即時賠率及模型權重沒有影響。

## 本 PR 改動

1. 建立隔離目標 `research/met-weather-archive`：由當時 main commit `3ce493fbeb9bfea29af1b93064a085afe8efb280` 預建，沿用已存在的歷史天氣檔及當時 latest，**無新真正 MET Norway 來源採集、無改寫原 bytes、無改 main**。目前尚未保護此分支。
2. 新 `ops/met_weather_isolated_archive.py`：固定 repo/ref/path、GitHub bearer token 網絡無 redirect；來源交由原有 `met_weather_guard.validate` 驗證 6 個城市、source/CC BY 4.0 attribution、captured UTC、HOLD/DISABLED、無盤口或模型特徵。先以固定 run ID/attempt 的 **create-once** gzip 寫 `weather_history`，已有相同 bytes 視為重跑，不同 bytes → `WEATHER_HISTORY_IMMUTABLE_COLLISION`。再用來源時間比較 `weather_latest.json`，只對較新的快照使用 GitHub Contents `sha` compare-and-swap 更新；相同時間但不同資料 → HOLD，舊來源永不蓋新。每一個成功 PUT 後必須對固定隔離 ref 重新 GET，驗證 raw bytes、Git blob SHA。
3. 天氣 workflow 的 `collect`、免密 MET Norway API 次數限制、排程、來源 guard 及 failure/close Issue jobs 不變；只將 `archive` 由沒有 branch 欄位的 main PUT 改成明確 isolated branch writer。checkout 使用已 pin SHA 並 `persist-credentials:false`。
4. iPhone `publish` job 保持 `contents:read`，僅用 `ops/met_weather_isolated_archive.py read` 固定分支 GET `sources/weather_latest.json`，驗證 GitHub file metadata + blob + source guard + 36 小時 freshness；成功先傳入 `met_weather_overlay`。讀不到、403、篡改、來源過時 → 不再 fallback 到 main，直接顯示 optional weather overlay `HOLD`，**網頁其他研究功能不會因此自動使用捏造天氣**。
5. 新離線測試 `ops/tests/test_met_weather_isolated_archive.py`：create-once、重跑冪等、不同 bytes 衝突、老來源阻止退化、CAS 更新、讀取過期/未授權、run ID 注入、固定 URL 與拒絕 301/302/307/308 轉址、workflow 不回退 main、mock 完整 GitHub HTTP workflow。

## 不能過度解讀的證據

- **RED**：新測試先行時，實際 GitHub CI 缺少 `met_weather_isolated_archive` 模組而 fail，證明當時尚未實作新隔離路徑。這不是 production 故障。
- GREEN 必須以**最終 HEAD** 的真實 GitHub CI、原始安全回歸日誌確認，不能只看舊版本。
- 此 PR 的 publisher/reader GitHub HTTP 邊界測試只會使用 in-memory/fake API，**不會改任何真正 source/archive data，也不會自行調用 MET Norway**。僅建立預備 archive branch；真正 scheduled Actions publisher→archive branch→iPhone Pages reader→Issue 通知 end-to-end **未執行**。
- 即使 API readback + Git blob SHA/SHA256 正確，也唔等於可信外部時間見證、Sigstore/Rekor、公正賽果核實或正式可交易賠率。
- `GITHUB_TOKEN contents:write` 屬 repo 權限；腳本限定 destination 不等於 GitHub admin 強制只許寫某 branch。**main 同隔離 branch 的 enforceable required ruleset、非作者 reviewer、14 條其他 writer 的 migration 尚未完成。**
- **不得合併本 Draft、不可提早啟用 main protection 中斷資料封存、不可更改已 sealed 來源、不可聲稱正 EV。** `production_recommendations=DISABLED`、`source_data_used_in_model=false`、`verified_betting_advantage=false`。

## 後續人工驗收條件

- 獨立 reviewer 審核本 PR 的 archive 寫入路徑、來源 guard、正反測試與 iPhone 缺資料 HOLD；檢查同其他原有 workflow/PR 冇衝突。
- 管理員為 isolated writer 與未來 main branch ruleset 制定 no-bypass；唔使用高權限 PAT 繞過 review。
- 經批准後才使用受控資料跑一次真實 Actions writer + readback + Pages consumer canary；比對既有 main baseline latest、實際 xG/盤口無參與，以及定時報表連續性。
- 確認其他 main writers 遷移後，再考慮真正主線 PR-only protection 和 release 閘門。未達要求一直 `HOLD/DISABLED`。

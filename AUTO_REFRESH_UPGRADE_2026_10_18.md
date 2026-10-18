# 足球王者｜來源完成後自動刷新網站（2026-10-18）

## 今輪修復

五個已由手機網站讀取的資料來源，採集完成後用 `GITHUB_TOKEN` 將最新資料存入儲存庫，但原本未列入網站的 `workflow_run` 訂閱。GitHub 不會因為這類 token 產生的資料提交再觸發一般 `push` 工作流程，所以網站要等其他已訂閱來源或下一輪六小時排程才刷新。

本次只補齊來源完成到網站發布的接駁，不改模型、採集頻率、API 配額或封存研究數據。

| 採集流程 | 網站現有輸入 |
| --- | --- |
| BSD 免費足球賠率與賽程後備 | `sources/bsd_status_latest.json`、`sources/bsd_market_latest.json` |
| 挪威官方免費天氣研究資料 | `sources/weather_latest.json` |
| 全球大小聯賽免費 OpenFootball + OpenLigaDB | `sources/wide_latest.json` |
| 兩個新增免費研究 API 核驗 | `sources/research_extensions_latest.json` |
| Japan Free Odds Source Audit | `market/japan_free_status.json` |

## 驗收標準

- 五個來源成功完成後，可以啟動現有網站更新流程；原有三個來源仍然適用。
- 只接受本儲存庫預設主分支的成功來源任務；失敗、取消、其他分支及其他儲存庫來源不發布。
- 來源任務觸發發布時使用預設分支的程式，不 checkout 來源任務的任意提交；checkout 不保留 Git 憑證。
- 原有手動更新、主分支程式更新與每日四輪定時更新繼續可用。
- 網站發布的並行控制、安全測試及發布閘門照常執行；不額外執行上述五個採集流程。
- `production_recommendations = DISABLED` 及 HOLD 規則維持原樣。

## 驗證與界線

修復前的既有 `ops/tests` 共 1,256 項全部通過。新增連接回歸測試首先重現五個來源訂閱缺漏（五個子測試失敗），修復後通過。事件測試直接讀取實際發布條件，以受限布林比較解譯檢查成功、失敗、取消、非主分支、其他儲存庫及缺少來源身份的事件；這是離線模擬，不是已驗收新接駁的線上觸發。

本地驗證：

- `python -m compileall -q ops`：通過。
- `python -m unittest discover -s ops/tests -q`：1,263 項通過，包含 7 項新增測試。
- 現有私人盤口 CI 涉及的九個測試檔：44 項通過。
- 原版 V4.1 ZIP SHA-256 與既定值一致；按既有相容修正跑 117 項原版測試通過，封存 ZIP 未修改。

另以既有主分支流程完成一次網站更新及封存：[GitHub Actions 39129650972](https://github.com/CHANCHUNWA1989/football-king-report/actions/runs/39129650972)。2026-10-18 13:03:26 UTC 的網站獨立健康檢查為 PASS，三份公開狀態、樣本計數一致性及市場時間檢查全部 OK。這次更新使用既有流程，並非本 PR 新接駁已生效的證據。

這是更新流程可靠性修復，不代表預測命中率改善。缺少來源密鑰或資料的流程仍會如實顯示 `NOT_CONFIGURED`／HOLD；採集任務成功不等於市場資料已齊全。

此修改透過獨立研究分支與 PR 保留驗收紀錄，通過相關 CI 後合併發布；新接駁須以主分支的實際運行再確認。

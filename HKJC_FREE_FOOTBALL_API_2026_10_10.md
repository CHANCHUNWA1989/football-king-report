# 足球王者：香港賽馬會足球盤口免費研究接駁（2026-10-10）

## 資料來源與重要界線

- 官方 HKJC 參考頁：https://bet.hkjc.com/ch/football
- **實際 API 供應商是第三方 Tipsme，不是賽馬會官方 API。**
- Tipsme 公開 API 文件：https://tipsme.hk/zh-HK/developers/docs/odds
- 免費方案：https://tipsme.hk/zh-HK/developers/pricing （HK$0，一般 API 每日30次，另有每日50次賽程請求；額度與權限可能更改，以供應商最新條款及實測為準）
- 申請私人 Key：https://tipsme.hk/zh-HK/developers/dashboard/keys
- **歷史舊檔（main，遷移後將停止更新）**：`sources/hkjc_tipsme_free_latest.json`；**唔可以再單憑呢個舊路徑判斷最新盤口或資料可用性**。
- **擬遷移嘅新狀態檔（PR #442 / #443 仍係 Draft，未合併）**：固定隔離分支 `research/hkjc-free-metadata-archive` 嘅 `sources/hkjc_free_metadata_archive/latest.json`。未有第一次真正成功嘅封存前可能係404，必須 `HOLD`。
- GitHub 測試：https://github.com/CHANCHUNWA1989/football-king-report/actions/workflows/football-king-hkjc-free-research.yml

## 最短設定（只需用家一次）

1. 用瀏覽器註冊及登入 Tipsme，申請其免費開發者 API Key，**毋須付費**。
2. 在 https://github.com/CHANCHUNWA1989/football-king-report/settings/secrets/actions 按 `New repository secret`：
   - **Name**：`TIPSME_API_KEY`
   - **Secret**：複製剛獲發的完整私人 Key，按 `Add secret`。
3. **目前 PR #442／#443 未合併時**：到上方 GitHub Actions 查看已成功完成嘅 `football-king-hkjc-tipsme-free-metadata` **7日保留 Artifact**；唔好將 main 舊JSON當最新資料。呢個動作可能使用你已經設定嘅 Key，請留意免費請求額度，毋須為此增加頻率。
4. **將來經獨立審核及合併後**，用 `python ops/hkjc_isolated_reader.py --no-auth` 讀取獨立分支（公開metadata毋須任何新 Key）。此檢查器預設任何輸出都係 `status: HOLD`，用非零退出碼防止任何自動化當作投注放行；`metadata_recent=true` 只代表封存捕獲時間距檢查時刻不超過30小時，**唔代表有即時賠率、正式授權或成交可用性**。
5. 真正嘅資料收集流程一旦回傳 `configured=true`／`RESEARCH_ONLY`／有效市場計數，只能證明當時有基本格式及時間條件通過嘅**第三方研究摘要**；GitHub CI 綠燈同捕獲計數都唔等於來源獨立、授權、可成交盤口、準確率提升或正 EV。

切勿將 Key、馬會帳戶名稱、密碼、登入資訊、任何私人憑證貼在聊天或 GitHub 公開 Issue。需要聯絡供應商確認授權範圍時，由用家自行處理。新資料只用於私人研究摘要，不會抓取或鏡像 HKJC 網站、不重新發布供應商原始賠率或賽事名單、不會連接馬會投注帳戶、更不會落注。

## 工程保護

- 沒有 Key 時請求數 **0**，狀態 `NOT_CONFIGURED`。
- 用到 `GET /v1/football/matches` 同特定比賽 `/odds/hkjc`，支援賽前十進制價格和盤線驗證。主客正負四分之一讓球盤必須互補；其他只有雙邊有效報價才計數。
- 每次最多 **2次賽程 + 4次特定賽事 HKJC 賠率 = 6次請求**，保留最後至少7個一般額度。
- 只採用明確標示 `isHkjc = true`、開賽前10分鐘以上、過去20分鐘內更新嘅市場。無法證明更新時刻的行一律剔除。
- 香港時間每日13:18自動試一次（GitHub 排程可能延遲）。
- 公開 GitHub 只儲存按聯賽計數，無比賽ID、球隊、博彩公司、原始賠率或供應商返回正文，唔會自動落注、計 EV、改模型或解鎖博彩建議。
- 現有足球王者六聯賽及日職 API 不受影響。只有港馬會官方賠率頁可供人類直接查看：HKJC 係第三方 Tipsme 資料嘅上游對象，但兩邊並非兩個獨立博彩公司。
- Tipsme 方案即使公開列明賠率一般可試用，如賽事回傳 `403`、`404` 或超額，將 HOLD；不得以非公開 endpoint、無授權爬蟲或增加帳戶迴避授權或配額。

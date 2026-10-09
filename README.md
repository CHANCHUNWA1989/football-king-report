# 足球王者 V4.1｜iPhone 每日足球研究報告

> 研究用途，並非正式投注建議。未有經驗證嘅市場賠率、校準模型、樣本外紀錄之前，正式投注推薦維持 **停用（HOLD）**。

## 現時部署狀況（2026-10-09，香港時間）

- ✅ 原始 V4.1 程式 ZIP 已完整上傳：`packages/football_king_v4_1_iphone_verified.zip`
- ✅ 原始檔案 SHA-256：`12e46fb527c012598f76eadcae8b04c41bf20b9345920dd59cd3a2cd40af7c8e`
- ✅ GitHub Actions 已建立：`.github/workflows/football-king-iphone.yml`
- ✅ 首次雲端測試：117 項單元測試通過，網站報告產生及安全檢查通過
- ✅ 公開資料連線：英超、英冠、德甲、西甲、意甲、法甲六項聯賽，`NETWORK_DATA_PASS: True`
- ⏳ **網站發布尚未完成**：GitHub Pages 須由帳戶持有人首次啟用「GitHub Actions」為發布來源

[查看首次雲端測試紀錄](https://github.com/CHANCHUNWA1989/football-king-report/actions/runs/37880369570)

## 只欠一次手動啟用

打開 [儲存庫網站發布設定](https://github.com/CHANCHUNWA1989/football-king-report/settings/pages)，在「Build and deployment（建置及部署）」下，將「Source（來源）」選成 **GitHub Actions（自動執行）**。

完成後告知 ChatGPT「Pages 已啟用」。ChatGPT 會協助重新觸發、核實網站及檢查報告內容。

## 自動化安排

- 每日香港時間約上午 **09:17** 由 GitHub 雲端執行。
- 更新工作流程或者 V4.1 ZIP 時，可自動觸發測試及網站發布。
- 每次對 ZIP 做 SHA-256 完整性校驗，再解壓運行原始 V4.1。
- 每次執行 117 項單元測試、採集免費公開賽程、生成繁體中文網頁和檢查 HOLD 風控。
- 執行失敗或資料不足，不會憑空製造比賽、即時賠率或投注建議。

## 已知限制

目前公開資料連線不等於賽事獨立核實。尚未接入已授權嘅即時多公司賠率、完整 xG／傷停／正選資料，亦未完成真實樣本外盈利及概率校準驗證。所有「正式投注建議」保持停用。

> 專案只使用公開來源作研究，任何資料異常應查看 [Actions 執行紀錄](https://github.com/CHANCHUNWA1989/football-king-report/actions)。

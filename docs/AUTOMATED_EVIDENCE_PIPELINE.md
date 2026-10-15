# 足球王者：自動研究證據驗收

研究分支加入每日 UTC 02:50（香港時間 10:50）的 GitHub Actions 排程。排程只在工作流程合併到預設分支後正式生效。

## 每次執行
1. 執行輸入審計、獨立賽果配對及離線研究整合測試。
2. 如果儲存庫存在 `research/inputs/forecasts.json` 和 `research/inputs/results.json`，使用兩份封存資料產生研究評分及繁體中文報告。
3. 如果缺任何一份，使用空資料執行安全拒絕，輸出 `HOLD`、零接受樣本及中文報告，**不會**冒充成功回測。
4. 無論有無資料，驗證 `production_recommendations=DISABLED`，然後上載 14 天保留的報告 artifact。

## 重要限制
- 這不是外部數據自動採集器。兩份輸入需要來自合法、獨立、已封存及可核對來源。
- `independently_verified` 目前仍是資料提供者的聲明旗標，並非第三方自動審計證明。
- 不自動下注，不發出正式推薦，不公開私人盤口或 API 金鑰。
- 綠色 CI 只證明流程及安全約束運作，**不代表**預測命中率或市場優勢達標。
- 手機用戶可在 Actions 頁面查看「足球王者｜自動研究證據驗收」並下載 `football-king-independent-evidence-report`。

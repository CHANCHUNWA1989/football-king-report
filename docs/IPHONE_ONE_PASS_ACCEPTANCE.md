# 足球王者｜iPhone 單次整合驗收

本流程只用儲存庫已封存的資料，**不會憑空生成預測或賽果**，亦不會開啟投注推薦。

## 從 iPhone 執行
1. 打開 GitHub 儲存庫 → Actions →「足球王者｜繁體中文整合驗收」。
2. 如果工作流程已經在預設分支啟用，選擇 Run workflow。
3. 執行完成後，下載 `football-king-zh-hant-mobile-report`。
4. 檢查報告「資料時效」、「獨立核實賽果」及「正式推薦：未開放」。

**重要：** 此流程目前仍在 PR #188 的研究分支；GitHub Actions 的手動按鈕和每日排程通常要在工作流程進入預設分支後才能正常使用。PR Checks 已能測試分支上的推送觸發流程。

## 進階：完整離線研究批次
當真正存在兩份已封存 JSON（賽前預測及賽後獨立核實賽果）時：

```bash
python ops/run_research_pipeline.py \
  --forecasts path/to/forecasts.json \
  --results path/to/results.json \
  --consensus market/latest.json \
  --summary market/private_summary_latest.json \
  --gates sources/seven_quality_gates_latest.json \
  --output-dir output/research
```

輸出 `shadow_score.json`、`index.html`。輸入驗收失敗會 HOLD 並隱藏該批次表現指標。

## 尚未完成的外部依賴
- 全球合規賽程、賠率及結果 API 的實際連接與額度核實。
- 預測時間戳不可回寫的封存證據，以及結果來源真正獨立的審計。
- 足夠樣本量的時間分段樣本外回測、概率校準、相對市場基準的增量價值。
- 審核 PR、合併到預設分支、部署及實際驗收每日排程。

**切勿**把 CI 綠燈解讀為預測命中率已獲證實。

# 足球王者｜整合驗收狀態與未完成依賴（2026-10-15）

## 已核實
- `3bb1639` 提交後，足球王者安全回歸、Regression and Failover、繁體中文整合驗收三條 CI 全部成功。
- 離線研究入口 `ops/run_research_pipeline.py` 可將兩份 JSON（賽前預測及賽果）配對、評分、輸出繁體中文 HTML。
- `ops/reconcile_shadow_results.py` 拒絕重複賽事、缺來源、未標記獨立核實、非 FINAL 狀態及時間錯誤的記錄。
- 推薦開關仍為 `DISABLED`；成功執行 CI 不代表存在可用預測優勢。

## 尚未完成
1. **資料來源**：建立合規、穩定、可追溯的全球賽程、開賽前獨立預測及最終比分來源；驗證實際供應商可用性、授權及配額。
2. **資料溯源**：驗證結果來源與預測來源真正獨立，不能單靠 `independently_verified: true` 宣告。
3. **長期驗證**：封存不可回寫的賽前概率，賽後獨立核實，完成跨聯賽及時間分段樣本外評分，與市場基準比較並做概率校準。
4. **三市場**：獨贏、亞洲讓球、大小球各自完整、雙向、賽前時間有效的數據覆蓋；未獲授權的即時盤口不應公開。
5. **部署**：PR #188 仍需人工審查；排程工作流程在預設分支生效前，不能宣稱已每日自動運作。

## iPhone 操作
打開 https://github.com/CHANCHUNWA1989/football-king-report/pull/188
檢查 Files changed 和 Checks。通過 CI 後再決定是否合併。
如需查看報告附件，打開 https://github.com/CHANCHUNWA1989/football-king-report/actions ，
選擇「足球王者｜繁體中文整合驗收」成功執行記錄，從 Artifacts 下載。

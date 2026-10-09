# 足球王者 V4.1｜2026-10-09 實際部署及驗收

## 已證實的操作與數據

- GitHub Secret `THE_ODDS_API_KEY` 已經成功用於 The Odds API V4 的**真實免費聯賽目錄查詢**。六大聯賽 active。
- 真實市場採集最初取得六大聯賽共120場、完整可比較 1X2 去水共識概率；截至 2026-10-09 約12次積分已使用、488積分剩餘（不保證之後仍然一樣）。
- 首輪27場未校準模型候選，只在嚴格身份、時間、賠率先於模型預測均符合時成功配對7場，其餘20場排除。
- 首輪德甲雙來源272個身份配對、29場雙方有賽果、未見比分差異；不能推論其他聯賽也核實。
- 原始 V4.1 ZIP 的117個原版測試仍通過；額外市場、資料品質、歷史及網站風控測試需以最新 GitHub Actions 當次成功紀錄核對。
- 先前歷史存檔曾發現 GitHub 同時寫入衝突及 shell loop 範圍問題，已經修正為受控重試及獨立一次性證據寫入；須持續觀察定時執行。
- 現有 Shadow/Market 初步比較均為未完場研究，已結算的可比較樣本目前為0；**正式模型驗證維持 HOLD**。

## 網站及資料安全設計

1. GitHub Pages 中文報告自動部署，資料過期十小時會顯示 HOLD；缺可見安全提示亦阻止正常發布。
2. 獨立網站監控每六小時檢查主狀態、品質、shadow、derived market、嚴格賽事配對及安全旗標。
3. The Odds API 賠率查詢僅 EU 地區 h2h 1X2，每月使用360／500積分或保留不足140時停止扣額操作，不自動升級收費。
4. API Key 限定在賠率採集／驗證的必要 GitHub Actions 步驟，不進入網站 HTML、公開 JSON、原始 ZIP 或研究快照。
5. 公開儲存庫不保存原始 bookmaker 價格／明細，只存供研究用的衍生去水概率及必要來源時間。不得將其充作可執行下注價格。
6. 模型一律註明未校準；勝平負研究概率不是投注推薦。沒有足夠前瞻樣本、CLV及盈利性證據前不會自動啟用正式建議。
7. 結算後的獨立研究評分選每場最早的封存預測；在已確認完場及過了最短賽事時間之後，才納入 Brier／Log Loss。

## 目前仍不能承諾完成

- The Odds API 免費方案不能無限制獲取歷史市場賠率或高頻刷新全聯賽。
- 沒有真實、可執行的當時下注價，不能合格證明 EV、CLV、ROI。
- 無完整合法傷停、正選、xG及原版 V2.8 程式；其他五聯賽需獨立賽果驗證，仍有部分賽事欠精準開賽時間。
- 預測需要真實已結算樣本。即使樣本達300場，也可能與市場一樣或更差，必須維持 HOLD。
- GitHub Issues 警報依賴 GitHub 平台，iPhone 主動推送及真正故障自癒需獨立通知渠道／額外用戶設定。

## 實證連結

- [API Key 真實供應商驗證成功](https://github.com/CHANCHUNWA1989/football-king-report/actions/runs/37885181200)
- [首次120場賠率、6積分採集](https://github.com/CHANCHUNWA1989/football-king-report/actions/runs/37884320644)
- [有7場嚴格市場配對的初次發布](https://github.com/CHANCHUNWA1989/football-king-report/actions/runs/37885797396)
- [第一輪完整前瞻自動結算部署](https://github.com/CHANCHUNWA1989/football-king-report/actions/runs/37885856008)
- [最新各項自動運作](https://github.com/CHANCHUNWA1989/football-king-report/actions)
- [iPhone 足球王者中文網站](https://chanchunwa1989.github.io/football-king-report/)

**RESEARCH_ONLY 代表供研究用；HOLD 代表未有足夠投注決策能力。不得混淆。**

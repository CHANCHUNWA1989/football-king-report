# 足球王者：六大聯賽免費API與七項質素驗收 — 2026-10-10

本升級零月費，僅使用用戶已配置的 PropLine Free API Key。The Odds API、TheSportsDB、OpenFootball、OpenLigaDB 和 BSD 不被更改，亦不會混入沒有授權的付費報價。新流程每日香港時間11:27及人工觸發，每次最多7次請求；因首輪真實採集全市場回應過大，現只查四間指定莊家的全場主市場；英冠必須喺官方 sports catalogue 出現認可代碼才查詢，供應商未提供則保留 HOLD 而不偽稱覆蓋。如果官方每日配額剩餘小於或等於75次，停止後續六聯賽請求。

官方文件：https://prop-line.com/docs 。官方條款：https://prop-line.com/terms 。PropLine 許可內部研究及合適的衍生資訊，但禁止大量公開原始賠率、批量鏡像與轉售。公開 GitHub 只儲存聯賽市場覆蓋數量、驗證狀態、配額及時間戳；不保存個別莊家名稱、實際原始賠率、私人 Key 或完整原始資料。其他來源有獨立下游授權要求，不能憑 PropLine 授權代替。

## 七項完成準則

1. **六聯賽賽事身份／UTC**：每個有效市場需有合法 UTC 開賽時刻、已識別主客隊及聯賽，距離開賽至少10分鐘；最終 PASS 需逐場另有獨立賽事來源交叉驗證。
2. **來源時間／配額／授權**：記錄捕獲時間、來源狀態、免費請求次數、官方剩餘配額和授權來源；未逐個來源證明合法資料權限只作 PARTIAL。
3. **雙邊讓球和大小球**：同一個莊家、同一個完整全場市場、同一盤線的主客讓球正負互補，或相同大小球線的 Over/Under 同時存在，才計合格；不把單邊或不合法四分之一盤算作覆蓋。
4. **莊家去重**：同一來源的重複莊家不能增加有效莊家數；不同 API 不等於不同莊家。跨供應商獨立身分未核實前保留 PARTIAL/HOLD。
5. **時間點防洩漏**：使用既有賽前模型／市場封存及最早預測配對邏輯；新報告只接受開賽前、未過期資料，較舊採集不能覆蓋較新報告。尚未覆蓋所有模型輸入只作 PARTIAL。
6. **樣本外模型評估**：維持 HOLD，直到累積至少300場獨立、真正前瞻封存並賽後結算的樣本，完成 Brier Score、Log Loss、校準及對市場基準的同場比較；資料回填及同盤重複不算樣本。新來源不得自稱提高命中率或 ROI。
7. **模型升級安全**：所有新增資料只供獨立 Shadow Mode 研究，永久維持 DISABLED，禁止自動投入正式投注建議。需要另行授權審批才能改變主模型。

機器狀態分為 PASS / PARTIAL / HOLD。PARTIAL 不是完成；對缺少證據的項目不會作虛假 PASS。即使七項安全工程全面實裝，也不能把未累積嘅前瞻結算樣本視為達標。

## 結果與操作入口

六聯賽採集 workflow：
https://github.com/CHANCHUNWA1989/football-king-report/actions/workflows/football-king-six-free-upgrade.yml

六聯賽免費市場覆蓋檔（成功執行後產生）：
https://github.com/CHANCHUNWA1989/football-king-report/blob/main/sources/six_league_free_latest.json

七項真實驗收狀態檔（成功執行後產生）：
https://github.com/CHANCHUNWA1989/football-king-report/blob/main/sources/seven_quality_gates_latest.json

The Odds API 六聯賽舊有 1X2 基準：
https://github.com/CHANCHUNWA1989/football-king-report/blob/main/market/latest.json

未有的私人 football-data.org、OpenFootAPI 或 TheRundown Key 需要擁有人申請並安全存入 GitHub Secrets；並不因工程接駁完成就虛稱現時有合格盤口。正式投注權限維持關閉。

## 2026-10-10 真實六大聯賽驗收第二階段：免費雙來源逐場核對

已增設 `ops/six_league_fixture_overlap.py`，只使用 GitHub 已保存的 The Odds API 1X2 賽事時刻、TheSportsDB／API-Football／football-data.org 合規研究摘要，**零額外 API 請求**。每場必須按六聯賽、已知隊名身份、主客身份及 UTC 開賽時刻（±45分鐘）嚴格配對。相同供應商重複觀測不算兩個來源；同場來源開賽時刻明顯矛盾時不計通過。上游資料可能互相轉載，因此兩個 API 同意並不等於兩個獨立賽果證明。

報告：`sources/six_league_fixture_overlap_latest.json`。逐聯賽只保存匹配／未匹配／時間衝突等**總數**，不會公開原始個別莊家報價、球隊列表或憑證。來源研究資料過時（36小時）、市場研究快照過時（26小時）都立即 HOLD，舊成功報告不可偽裝成今日通過。從本次起七項關卡會讀入真正逐場二來源 UTC 比對統計；不再僅憑市場本身就聲稱第二來源已驗證。已封存前瞻賽果 `evidence/settled.json` 只列候選數，未獨立證實前不能解鎖校準。

### 不可用作虛假覆蓋嘅英冠盤口

已正式確認 PropLine free sports catalogue 未列英冠，TheRundown 公開免費足球聯賽表也未列英冠。因此 **英冠亞洲盤及大小球保持未覆蓋**；仍可使用既有 The Odds API 英冠合法賽前1X2衍生基準及 TheSportsDB 賽程觀察。未取得合法完整兩側免費報價前，絕不設計虛構後備。

## 賽前研究歷史證據（自動安全封存）

六聯賽免費監察每次執行，都先將三份**不包含原始博彩公司盤口、莊家名稱或 API Key**嘅研究報告 gzip 封存到 `sources/six_league_quality_history/YYYY/MM/DD/GITHUB_RUN_ID-RUN_ATTEMPT/`，每份歷史檔案只新增、不覆寫。其後才有條件更新 `sources/*_latest.json`。呢個做法可以保留真正於當時已知嘅資料來源狀態、六聯賽可用性及跨出版者比賽時間一致性，便利後續防資料洩漏檢查。封存狀態並**不等於**封存到可下注原始賠率、全部 xG 特徵、已校準概率或真實獨立賽果；不能因此宣稱 CLV、EV、命中率或完整樣本外驗收已經合格。

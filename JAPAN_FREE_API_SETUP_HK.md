# 足球王者｜日本 J1 免費盤口與賽果 API 接駁（2026-10-10）

## 已建立的專項研究接駁

- The Odds API：已存在 THE_ODDS_API_KEY；新側鏈每日檢查日本 J1 h2h，僅在官方返回賽事啟用及免費配額充足時，做兩間以上博彩公司之已去水 1X2 比較。與原六大聯賽主市場嚴格分離。當 API 已用 >=260 credits 或餘額 <=220，不再額外消耗 J1 研究信用額度；月度授權及方案實際限制依提供者回應為準。
- PropLine：新 ops/japan_free_market.py 採用官方免費批次 GET https://api.prop-line.com/v1/sports/soccer_japan_j_league/odds?markets=h2h,spreads,totals ，只需 1 次請求；認證使用 X-API-Key HTTP 標頭，不會把 Key 拼接在 URL。Free 官網標稱 1,000 次／UTC 日。免費並不包含完整 odds/history、odds/closing 或成績 API。
- TheRundown：新側鏈用 X-TheRundown-Key 標頭，先查 GET /api/v2/sports/dates，再查 J1 sport 19 的單日 /api/v2/sports/19/events/YYYY-MM-DD?market_ids=1,2,3&affiliate_ids=19,22,23&main_line=true 。最多兩次請求。Free 20,000 data points／日、200,000／月（不是「次請求」），只包括三間博彩公司約五分鐘延遲的賽前主盤，不能當即場盤或已確認可買報價。

官方資料：
- https://www.prop-line.com/docs
- https://therundown.io/soccer-odds-api
- https://therundown.io/pricing/api
- https://the-odds-api.com/

## 尚需你本人啟用的兩條 Key

請在供應商免費方案自行申請、閱讀個人／商業用途以及保存／展示許可。**不要在 ChatGPT、Issue、程式碼或截圖貼出 Key**。

在 GitHub：
https://github.com/CHANCHUNWA1989/football-king-report/settings/secrets/actions

選 New repository secret，分別設置：
1. PROPLINE_API_KEY —— PropLine 官網 https://www.prop-line.com/ 免費登記所得；
2. THERUNDOWN_API_KEY —— TheRundown https://therundown.io/api 免費登記所得。

現有 THE_ODDS_API_KEY 無需重新加入；OPENFOOT_API_KEY 與 FOOTBALL_DATA_ORG_TOKEN 仍屬獨立可選接駁，前者只供已存在的免費日職資料採集，後者免費賽果主要覆蓋歐洲部分比賽，不能當作 J1 獨立比分保證。

**密鑰狀態檢查（只列 PRESENT / MISSING，不讀取、不印出值）：**
https://github.com/CHANCHUNWA1989/football-king-report/actions/workflows/football-king-free-api-keys-check.yml

**直接執行 J1 研究採集：**
https://github.com/CHANCHUNWA1989/football-king-report/actions/workflows/football-king-japan-free-market.yml

或等 GitHub Actions 每日自動採集：UTC 01:35（香港 09:35、日本 10:35）。
工作流程用最少權限：僅 collect job 有私人 API Key；archive job 不持有 API Key，只寫入合法可公開之去敏感元數據 market/japan_free_status.json。

## 新加入的資料保護

1. 只評估比賽開始至少 10 分鐘以前的賽前市場，最多 14 日前瞻；嚴格分開 in-play／已完成。
2. PropLine 與 The Odds API 每間參考博彩公司在收集時間前最多 20 分鐘更新；TheRundown Free 本身五分鐘延遲，亦設 25 分鐘觀察上限。
3. 同一來源同一博彩公司不能當兩個獨立投票。兩個 API 報價相同博彩公司，亦不能宣稱獨立的兩個可執行莊家。
4. 研究由完整三路 1X2 去水概率及獨立亞洲讓球／大小球覆蓋數據組成；公開網站**只有來源覆蓋、時間有效性、去水概率跨源差異摘要**。原始單間 bookmaker 盤口、價格及相關持牌敏感資料不會散播至 GitHub、GitHub Pages 或工件。
5. 沒有新 Key／API 無權限／已達免費額度／當日 J1 沒有開放市場時，顯示 NOT_CONFIGURED 或 HOLD，不會發明賠率、收益或推薦。
6. 新來源不能自行提升足球王者 J1 模型資格、EV、CLV 或正式投注資格。日職 2025 歷史資料與 2026/27 新賽制保持分開。任何理論價格邊際仍只是 Shadow 研究。
7. GitHub CI 成功只代表代碼測試成功，不代表供應商授權有效、免費數據必定覆蓋或可成交。

## 資料流程

新接駁：ops/japan_free_market.py
-> 去敏感發佈防護：ops/japan_free_market_guard.py
-> 每日免費採集：.github/workflows/football-king-japan-free-market.yml
-> 無 raw quote 公開元數據：market/japan_free_status.json
-> 手機研究頁防護：ops/japan_market_overlay.py
-> app/site/japan_free_market.json
-> iPhone 網頁日職 API 狀態面板。

原有主要六大聯賽 market/latest.json、獨立日期封存、production_gate.py 及 betting_readiness.py 都不會由此專項流程修改。正式投注推薦永久維持 DISABLED，直到取得獨立前瞻樣本、授權價格及人工風險驗證，並且另外明確批准。

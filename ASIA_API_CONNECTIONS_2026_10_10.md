# 足球王者：2026-10-10 API 接駁及授權指引

此文件區分「程式已備」、「真實數據已成功採集」及「需要 API Key」；綠色 CI 並不代表資料供應商正式授權。

## 已有接駁（保留原安全流程）

| 來源 | Secret 名稱 | 工作流程 | 現況 |
| --- | --- | --- | --- |
| The Odds API | THE_ODDS_API_KEY | football-king-odds.yml | 已有實際市場來源；免費額度保護 |
| BSD Football | BSD_FREE_API_TOKEN | football-king-bsd-free.yml | 已備程式，欠 Key |
| PropLine | PROPLINE_API_KEY | football-king-japan-free-market.yml | 已備程式，欠 Key |
| TheRundown | THERUNDOWN_API_KEY | football-king-japan-free-market.yml | 已備程式，欠 Key |
| football-data.org | FOOTBALL_DATA_ORG_TOKEN | football-king-secondary-sources.yml | 已備程式，欠 Token |
| OpenFootAPI | OPENFOOT_API_KEY | football-king-research-extensions.yml | 已備程式，欠 Key |

上述未配置的 API 依然是 NOT_CONFIGURED。免費方案可能不包括當季、目標聯賽、免費盤口或可公開轉發權限。

## 本輪新增 Open-Meteo：無 Key 亞洲天氣

- 程式：ops/asia_sources_connect.py
- 工作流程：.github/workflows/football-king-asia-apis.yml
- 只查首爾、釜山、水原、大阪、橫濱、名古屋六個近似**市中心**位置，最多72小時、每3小時抽樣天氣；每日最多6個公開天氣請求
- 成功採集及封存之後只發佈到 sources/asia_api_latest.json
- 署名：Weather data by Open-Meteo.com (CC BY 4.0)
- 條款：https://open-meteo.com/en/terms
- **免費 Open-Meteo 僅供非商業用途**；如需商業用途，必須先確認商業授權
- 非球場現場觀測、上游發布時間未知，不會改模型概率或投注資格

## 本輪新增 K League 官方 API：待合作伙伴授權

- 官方文檔：https://api.kleague.com/docs/index.jsp
- 認證：KLEAGUE_API_KEY GitHub Actions Secret
- 只用一次 GET https://api.kleague.com/api/leagueInfo.do?meet_year=2026（年份自動切換）
- 認證金鑰用 authKey HTTP 標頭，**不會放 URL 或日誌**
- 官網技術文件列出賬戶、每日配額、允許 IP／域名、合作伙伴授權等限制，不能保證人人免費取 Key
- 未配置 Key 時零請求；有 Key 時只驗證當年**聯賽目錄**存取，不會誤稱已接通官方比賽、球員、xG、賠率

## iPhone 設定

1. 自行到供應商官方網站申請、閱讀條款、取得 Private Token 或 Key。
2. 到 https://github.com/CHANCHUNWA1989/football-king-report/settings/secrets/actions → New repository secret，逐條填入上表完全一致嘅名稱。
3. 進入 https://github.com/CHANCHUNWA1989/football-king-report/actions/workflows/football-king-free-api-keys-check.yml → Run workflow → Summary，核對 PRESENT／MISSING。流程**只顯示有冇設定**，不讀取 Key 內容。
4. 使用 https://github.com/CHANCHUNWA1989/football-king-report/actions/workflows/football-king-asia-apis.yml 進行新亞洲側鏈驗證，舊來源用各自原本 Workflow 驗證實際免費權限。

千祈唔好將私人 Key 貼喺 ChatGPT、公開倉庫、GitHub Issue 或截圖。

## 研究風控

所有新資料均是獨立研究側鏈，明確保留 model_inputs_changed=false、market_odds_changed=false、production_recommendations=DISABLED。不得把採集成功當成改善命中率的證據，也不可在未取得可執行盤口、時間有效前瞻驗證和風險審核前解鎖正式投注建議。

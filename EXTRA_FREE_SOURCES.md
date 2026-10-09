# 足球王者 V4.1｜免費足球 API 真實接駁狀況

更新：2026-10-09（香港時間）。正式投注建議仍為 **HOLD / DISABLED**。呢份報告區分「程式已接入」同「供應商真係有提供你個戶口可用嘅資料」，絕不假稱全部已接通。

## 最值得用嘅免費渠道：七個來源

| 優先 | API／數據源 | 免費戶口／Key | 實際狀態與用途 |
|---|---|---|---|
| 1 | [The Odds API](https://the-odds-api.com/) | `THE_ODDS_API_KEY`（**已設定**） | 已實測六聯賽120場1X2市場衍生去水概率；500免費月積分受限，不能當可執行下注報價 |
| 2 | [OpenFootball football.json](https://github.com/openfootball/football.json) | 免Key | 已實測27個今季／歷史賽季檔案；無時區標記的開賽時間**不能冒充UTC**；有歷史資料限制 |
| 3 | [OpenLigaDB](https://www.openligadb.de/) | 免Key | 已實測德甲、德乙、德丙三聯賽資料；可補精準 UTC 開賽時間／部分賽果，獨立核實需另做 |
| 4 | [TheSportsDB 免費V1](https://www.thesportsdb.com/docs_api_guide) | 公開免費測試Key `123`，**已接通** | 首次6場，擴展後 **2026-10-09 實測28場**六聯賽免費樣本；每天最多24請求（最近／下場／今明兩日）。免費版數據截斷，唔係全聯賽日曆 |
| 5 | [football-data.org](https://www.football-data.org/pricing) | `FOOTBALL_DATA_ORG_TOKEN`（**未設定**） | 六聯賽賽程／延遲賽果、積分榜；免費12項競賽、10次／分鐘；**目前最值得你補申請嘅Key** |
| 6 | [API-Football](https://www.api-football.com/pricing/) | `API_FOOTBALL_KEY`（**已設定**） | 免費100次／日，但 **2026-10-09 真正API回傳免費計劃不支援當季資料**，只查1次即停止；不可以當今年免費1X2後備 |
| 7 | [Sportmonks Free](https://www.sportmonks.com/football-api/free-plan/) | `SPORTMONKS_API_TOKEN`（**未設定**） | 可連免費丹麥超聯、蘇格蘭超聯沙盒，**不包括主要六聯賽**；對六聯賽推薦嘅實際增益低 |

## 已成功實證

- [四額外API最新真實採集及安全存檔](https://github.com/CHANCHUNWA1989/football-king-report/actions/runs/37918598937)：TheSportsDB **24次合法免費請求取得28場唯一賽事**。API-Football：Key存在，但免費2026球季拒絕，**只做1次查詢，沒有繼續探測賠率**。另外兩個供應商正確標示 `NOT_CONFIGURED`。
- [全球30個來源／賽季檔案實際採集](https://github.com/CHANCHUNWA1989/football-king-report/actions/runs/37916957821) 已成功；30個資料組合唔等於30個互不重複嘅今季聯賽。
- [手機研究網站](https://chanchunwa1989.github.io/football-king-report/) 顯示獨立來源覆蓋，同模型／市場候選分開；新資料須等下一輪成功的網站發布才會顯示。
- [完整程式及資料稽核](.github/workflows/football-king-secondary-sources.yml) 包括24次 TheSportsDB、API-Football最高12次但當季被拒即停、football-data.org最多6次、Sportmonks最多2次。全部維持免費方案，不自動付款。
- 來源資料不會自動當成可下注賠率、未經核實嘅模型訓練資料、可驗證盈利或正式投注建議。

## iPhone：真正啟用尚缺嘅免費 API Key

只有你喺供應商網站建立帳戶，同意其服務條款，先可以取得專屬免費 Key。我無法代你申請或憑空建立密鑰。**唔需要將 Key 貼入 ChatGPT、GitHub Issue 或公開程式。**

1. 最優先到 [football-data.org](https://www.football-data.org/pricing) 註冊免費戶口，取得 API Token。進入你個 [GitHub Repository secrets](https://github.com/CHANCHUNWA1989/football-king-report/settings/secrets/actions)，按 **New repository secret**，名稱精確填入 `FOOTBALL_DATA_ORG_TOKEN`，Value 填你個 Token。
2. 如果另外想擴展蘇超／丹麥聯賽，可以到 [Sportmonks Free](https://www.sportmonks.com/football-api/free-plan/) 開免費戶口，再新增同一頁嘅 `SPORTMONKS_API_TOKEN`。如只在意六大聯賽，呢項可延後。
3. `THE_ODDS_API_KEY` 同 `API_FOOTBALL_KEY` 已經存在，**唔需要重新設定**。API-Football免費季別限制不能靠更換同一免費Key繞過。
4. 到 GitHub **Actions → 足球王者｜四個免費後備來源獨立採集 → Run workflow** 執行一次；下次每日自動查詢亦會識別已設好嘅 Key。憑工作紀錄確認 `PARTIAL_COVERAGE` 或其他誠實嘅狀態，不能單憑 Secret 存在宣稱覆蓋成功。

## 風險同限制

- OpenFootball、OpenLigaDB、TheSportsDB、football-data.org 主要幫你補賽程、部分比分、時間與交叉核驗，**唔等於免費可執行的博彩公司1X2實時報價**。
- [football-data.org 免費方案](https://www.football-data.org/pricing) 提供延遲比分，**1X2 賠率 Add-On 另外收費**，因此此系統唔會自動用佢當免費賠率。
- [API-Football 官方免費方案](https://www.api-football.com/pricing/) 寫有 Odds 端點，但明示當季限制。用真正帳戶測試被拒後系統停止，唔會假造資料。
- [TheSportsDB 免費端點](https://www.thesportsdb.com/docs_api_guide) 下一場、最近一場每聯賽只回傳1場；按日最多3場；唔係完整聯賽賽程。
- 每個資料來源都有時效、準確性、使用條款同再發布限制；只封存有限身份資料與適當署名，不轉售或公開原始商業賠率。
- 模型仍未經足量前瞻驗證，沒有可靠EV、CLV及ROI。推薦只屬有明確標籤嘅研究方向；**正式投注仍然HOLD**。

## 程式及資料

- [免費來源連線及每供應商配額限制](ops/secondary_sources.py)
- [免費資料安全存檔驗證](ops/source_publish_guard.py)
- [六大聯賽來源交叉核對](ops/source_overlay.py)
- [全球／小型聯賽公共來源](ops/wide_sources.py)
- [最新四個來源真實採集](sources/latest.json)
- [新來源每日 GitHub Action](.github/workflows/football-king-secondary-sources.yml)

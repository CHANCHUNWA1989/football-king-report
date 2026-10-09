# 足球王者 V4.1｜四個新免費來源接駁

更新日期：2026-10-09。全部屬 RESEARCH_ONLY，正式投注建議仍然係 HOLD。

## 四個渠道

| 來源 | 免費範圍 | GitHub Repository Secret | 系統功能 |
| --- | --- | --- | --- |
| [TheSportsDB 官方免費版](https://www.thesportsdb.com/docs_api_guide) | V1 公開測試 key 123；每聯賽下一場通常最多回傳1場 | 無需 Key | 六聯賽基本賽程與開賽時間核對，非賠率 |
| [API-Football 免費方案](https://www.api-football.com/pricing/) | 100 requests/day，當季可查範圍受免費方案限制 | API_FOOTBALL_KEY | 每日最多6次賽程及6次賽前 1X2 賠率覆蓋探測，只統計存在與否，不公開原始報價 |
| [football-data.org](https://www.football-data.org/pricing) | 12個賽事，延遲賽果，最多10 calls/min | FOOTBALL_DATA_ORG_TOKEN | 六聯賽賽程及延遲賽果核對，無即時1X2賠率 |
| [Sportmonks Free](https://www.sportmonks.com/football-api/free-plan/) | 只包丹麥超聯及蘇格蘭超聯 | SPORTMONKS_API_TOKEN | 免費帳戶驗證／獨立沙盒；**對現有六大聯賽冇直接免費覆蓋** |

## 首輪真實測試

2026-10-09 TheSportsDB 已經透過 GitHub Actions 真正取得六聯賽各一個賽程樣本，合共六場。其餘三個供應商喺未放入自己嘅 Key 之前會顯示 NOT_CONFIGURED，而唔會聲稱連線成功。

[首次四來源免費採集及存檔紀錄](https://github.com/CHANCHUNWA1989/football-king-report/actions/runs/37907231790)

## 用 iPhone 加入三個免費 API Key

開啟 [GitHub Repository secrets](https://github.com/CHANCHUNWA1989/football-king-report/settings/secrets/actions)，按 New repository secret，分別填寫：

- API_FOOTBALL_KEY — 在 API-Football 官網申請免費 Key
- FOOTBALL_DATA_ORG_TOKEN — 在 football-data.org 官網申請免費 Token
- SPORTMONKS_API_TOKEN — 在 Sportmonks 官網申請免費 Token（免費戶口只得丹麥及蘇格蘭聯賽）

**唔需要喺對話提供任何 Key；亦唔好放入公開 GitHub Code、Issue 或 GitHub Variables。** 只要設成 Repository secrets，已建立好嘅程式就會喺獨立採集步驟使用。

TheSportsDB 官方公開 key 123 唔需要自行新增 Secret。

[四來源每日採集流程](.github/workflows/football-king-secondary-sources.yml) 設定香港時間每天05:43運行（GitHub排程可能延後）；亦可以打開 Actions → 足球王者｜四個免費後備來源獨立採集 → Run workflow 手動測試。

## 安全及使用限制

- 每日最多查 TheSportsDB 6次、API-Football 12次、football-data.org 6次、Sportmonks 2次；沒有認證資料嘅來源完全跳過。
- 各來源分開計數，不會借用 The Odds API 的500積分，不會升級成付費套餐。
- 只保存必要賽程身份、UTC開賽時間、合法的完場比分同來源狀態；**不會把原始博彩公司價格、商業報價、私人 Key 或供應商完整回應放到公開網站**。
- 出現403無權限、429限額或缺少賽事會清楚標記，唔會自動改用其他收費來源。
- 免費 API-Football 即使聲稱提供賽前賠率，亦須真實驗證該季聯賽、市場、授權和報價可用性，才可研究比較；目前不當作已接通可執行市場。
- 六聯賽獨立賽果核驗、模型準確度及ROI不會因為新增四個來源而自動變成已證明。
- TheSportsDB 免付費開發用途受 [官方條款](https://www.thesportsdb.com/docs_terms_of_use.php) 規管；勿移除來源署名，勿在冇適當許可下轉售資料或發行付費App。

## 新增程式

- [ops/secondary_sources.py](ops/secondary_sources.py)：4個來源的安全網路擷取、每個供應商獨立限次、資料正規化。
- [ops/source_publish_guard.py](ops/source_publish_guard.py)：防止私密 Key、原始賠率、時間倒流、錯誤宣稱六聯賽核驗完成。
- [ops/source_overlay.py](ops/source_overlay.py)：將來源覆蓋與時間核對整合到現有 iPhone 網站。
- [sources/latest.json](sources/latest.json)：公開可查的最新四來源採集狀態。
- [extra_sources.json](https://chanchunwa1989.github.io/football-king-report/extra_sources.json)：網站公布的安全核對結果。

**足球王者 V4.1 核心 The Odds API、Shadow Mode、研究首選方向保留原本規則；新增渠道目前只補充可核實數據，不會自行變成正式下注建議。**

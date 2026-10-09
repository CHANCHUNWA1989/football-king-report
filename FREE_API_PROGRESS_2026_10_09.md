# 足球王者 V4.1｜免費足球 API 真實進度與新增來源

**查核日：2026年10月9日（香港）**  
**原則：只用免費合法來源。接駁成功唔等於得到當季數據；歷史目錄唔等於即時賽事，賽程唔等於博彩公司市場賠率。**

## 一、已接入主程式或獨立免費流程

| 來源 | 實測狀態 | 具體功能及限制 | GitHub 密鑰 |
| --- | --- | --- | --- |
| [The Odds API](https://the-odds-api.com/) | **已接通：120場、6聯賽1X2去水市場概率**；當次記錄24／500積分已使用、476剩餘 | 每日2次、限免費額度；只發衍生無水概率，並非可買價格 | `THE_ODDS_API_KEY`（已設） |
| [TheSportsDB](https://www.thesportsdb.com/docs_api) | **已接通：最新28場免費賽程樣本** | 每日24次有界查詢，今／明兩日及最近／下一場有限樣本；非完整六聯賽或1X2市場 | 無需個人密鑰 |
| [API-Football](https://www.api-football.com/pricing/) | **Key 已設，但現季免費授權被限制**；當次只探1次，得0場 | 官方標示免費100次／日及Odds端點，但Free限制季數；程序發現現季拒絕即停止，唔重複試錯或假稱可用 | `API_FOOTBALL_KEY`（已設） |
| [football-data.org](https://www.football-data.org/pricing) | 已編寫接駁，**未有Key** | 免費12項賽事、最多10次／分鐘、比分或賽程有延遲；**冇合法免費1X2原始賠率** | `FOOTBALL_DATA_ORG_TOKEN`（未設） |
| [Sportmonks](https://www.sportmonks.com/football-api/free-plan/) | 已編寫接駁，**未有Key** | 免費僅丹麥超及蘇超，不涵蓋原有六大聯賽；優先級低 | `SPORTMONKS_API_TOKEN`（未設） |
| [OpenFootball](https://github.com/openfootball/football.json) | 已接通，自動查核27個公共領域聯賽／季節檔 | 多個為舊賽季，來源時間／精確開賽時間未完全提供，唔能夠假定當季實時 | 無需 |
| [OpenLigaDB](https://www.openligadb.de/) | 已接通，德甲／德乙／德丙3聯賽資料 | UTC賽程核對，社群資料需交叉驗證 | 無需 |
| [OpenFootAPI](https://openfootapi.com/pricing) | **已完成安全接駁及測試；未設定自己的Key** | Free Starter：每月5000次、最多60次／分，基本賽程／賽果／積分榜；每日最多3次檢查；xG、陣容及衍生Odds屬收費方案，**非 The Odds API 免費1X2替代品** | `OPENFOOT_API_KEY`（未設） |
| [StatsBomb Open Data](https://github.com/hudl/open-data) | **成功讀取80個歷史比賽／賽季目錄項目** | 免費歷史球員與事件資料（有些賽季舊），適合研究及歷史驗證；須遵守其署名、標誌及授權限制；尚未投入現時模型 | 無需 |

最新實證：
- [四來源真實免費採集與封存](https://github.com/CHANCHUNWA1989/football-king-report/actions/runs/37918598937)
- [OpenFootAPI+StatsBomb 新增研究接口、80項官方目錄、成功封存](https://github.com/CHANCHUNWA1989/football-king-report/actions/runs/37920170058)
- [手機網站完整發布](https://github.com/CHANCHUNWA1989/football-king-report/actions)
- [公開新版免費研究 API 狀態摘要](sources/research_extensions_latest.json)

以上數量都只屬相關一次採集嘅記錄。配額會隨時間改變；每個來源冇實測數據時都會保留 `NOT_CONFIGURED` 或 `HOLD`。

## 二、另外搵到，暫時未直接加入自動模型嘅研究數據

**[Wyscout／Pappalardo 公開事件數據集](https://doi.org/10.1038/s41597-019-0247-7)**：2017–18 英、西、德、意、法五大聯賽，另有2018世界盃及2016歐國盃，合計約1,941場、三百多萬事件。論文確認 CC BY 4.0，正確署名下對歷史模型實驗有潛力。但只限舊球季，**無法充當2026年賽前即時資訊**。可能先在離線模型驗證中試用。

**[Impect 開放歷史數據](https://github.com/ImpectAPI/open-data)**：2023／24德甲比賽事件、陣容及球員評估指標，免費公開但受個別授權及標誌署名要求約束。**尚未驗證對今日預測有獨立增量貢獻**，不可盲目引入模型。

**暫不接入 [Football-Data.co.uk](https://football-data.co.uk/contact.php) 自動抓取**：來源網站清楚限制自動化 AI／訓練及商業用途；即使歷史CSV免費下載，都唔代表你公開 GitHub 模型可無限制自動使用。

**暫不依賴 ClubElo 舊版免費CSV端點**：近期資料顯示公開API不可用或轉為身份驗證，唔可當可靠免費服務。

## 三、你用 iPhone 完成最後必要 Key

唔使交 API Key 俾 ChatGPT。只需去 [你嘅 GitHub Repository Secrets](https://github.com/CHANCHUNWA1989/football-king-report/settings/secrets/actions)，將新供應商私人 Key 貼入相同名稱的 **Actions repository secret**。目前最值得你申請：

- **首選：`OPENFOOT_API_KEY`** — [OpenFootAPI 免費註冊方案](https://openfootapi.com/pricing)；揀 **Free Starter $0**。加入後按 [免費研究來源流程](https://github.com/CHANCHUNWA1989/football-king-report/actions/workflows/football-king-research-extensions.yml) → **Run workflow**，檢查是不是 `FREE_STARTER_SAMPLE_ONLY`；冇數據／權限時唔會冒充成功。
- **次選：`FOOTBALL_DATA_ORG_TOKEN`** — [football-data.org 免費註冊](https://www.football-data.org/client/register)，補充當季精準賽程／延遲賽果。

[一鍵檢查Key有冇設定（唔會消耗供應商請求）](https://github.com/CHANCHUNWA1989/football-king-report/actions/workflows/football-king-free-api-keys-check.yml)

## 四、正式推薦與安全邊界

**正常模式**繼續用已封存、合格時間點 The Odds API 市場＋Shadow模型；其他免費賽程只能幫助比賽身份、開賽時間及賽果核對。免費市場合成概率不是可下注真實報價，資料仍不足以驗證盈利能力。若免費賠率不足只可降級「純模型低證據觀察」，**正式投注資格一直 `HOLD／DISABLED`**。

來源的上游授權有各自要求，第三方聚合API唔能夠代替原始資料著作權人授權。公開數據目錄成功讀取並不代表無限制轉售／商用。未證明可持續提升Brier Score/Log Loss前，不將新資料自動灌進既有預測模型。


## 2026年10月9日晚上｜新增免費後備 API，真實測試結果

**MET Norway** 官方氣象免費API：完全毋須Key，已真實讀取六個城市的免費預報，只使用六次請求；足球王者獨立配對5場影子研究候選的預報背景。只係城市中心近似預報，唔係球場實測，冇加入主和客模型概率。官方 CC BY 4.0 署名會在 iPhone 網站展示。採集、存檔成功：https://github.com/CHANCHUNWA1989/football-king-report/actions/runs/37922248257

**Bzzoiro Sports Data (BSD)** 官方免費足球API：官方提供 7,500 次／日，免費足球包括賽程、xG研究及1X2共識報價。網站授權明確容許研究及發佈不可重建原始資料的衍生結果，但禁止大量轉發原始API資料。免費版只有共識報價，冇可執行的個別博彩公司報價。官方註冊 https://sports.bzzoiro.com/register/，官方授權 https://sports.bzzoiro.com/docs/api-license/。

我哋已加入獨立安全採集、封存、嚴格賽前雙來源配對與手機狀態：
- 採集程式 ops/bsd_free.py；安全檢查 ops/bsd_guard.py；獨立對照 ops/bsd_overlay.py。
- 自動更新 .github/workflows/football-king-bsd-free.yml，每日香港07:09，只准最多三次免費查詢，冇Key就零請求。
- 秘密金鑰名稱：BSD_FREE_API_TOKEN，只放入 GitHub Repository Actions Secrets，唔可以貼入聊天。
- 主 The Odds API 永遠唔會被新來源靜默覆蓋；新市場只限第二研究基準，正式投注建議保持 HOLD。

**實際現況**：目前BSD密鑰未設定。首輪真實雲端 workflow 成功，但只產生 NOT_CONFIGURED、0次API請求、0場BSD市場配對。唔能夠將「接駁程式完成」當作已得到BSD實際賠率。

實際執行：https://github.com/CHANCHUNWA1989/football-king-report/actions/runs/37923493224
手機網站驗收：https://github.com/CHANCHUNWA1989/football-king-report/actions/runs/37923812942
當輪117項原版＋272項額外測試＝389項全部通過；網站與存檔成功。

### 用iPhone完成BSD免費Token（毋須付款）

1. 開 https://sports.bzzoiro.com/register/ → 註冊免費戶口 → 電郵驗證 → 複製Token。
2. 開 https://github.com/CHANCHUNWA1989/football-king-report/settings/secrets/actions → New repository secret → 名稱填 BSD_FREE_API_TOKEN → 貼Token → Add secret。
3. 開 https://github.com/CHANCHUNWA1989/football-king-report/actions/workflows/football-king-bsd-free.yml → Run workflow。
4. 檢查真實免費權限及數據覆蓋；即使流程成功，若未有同場同時市場配對，研究方向仍不能升級。

其他合法免費接駁 football-data.org（FOOTBALL_DATA_ORG_TOKEN）同 OpenFootAPI（OPENFOOT_API_KEY）亦已存在，但需要你自行申請各自免費API Key。Sportmonks免費支援聯賽同現有六聯賽唔同，API-Football現季免費權限被拒絕，不應靠反覆查詢硬闖限制。

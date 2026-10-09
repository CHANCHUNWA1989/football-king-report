# 足球王者 V4.1｜香港繁體中文自動足球研究平台

**[最新免費 API 接駁進度、當季免費季別限制及額外研究來源（2026年10月9日）](FREE_API_PROGRESS_2026_10_09.md)**

- **OpenFootAPI 免費 Starter**：已寫入可選安全接駁，需你自己加入 `OPENFOOT_API_KEY`；免費5,000次／月，主要提供賽程／賽果，唔係免費可執行賠率
- **StatsBomb Open Data**：已真正接通80項**歷史**賽事／賽季目錄紀錄；尚未當作現季即時xG或模型證據
- [免費市場來源定時運行](https://github.com/CHANCHUNWA1989/football-king-report/actions)；唔會因為添加免費研究渠道而關閉原本免費賠率 API



## 免費 API Key 自助申請與一鍵確認（iPhone）

**[中文申請全流程：API-Football、football-data.org、Sportmonks](FREE_API_KEY_SETUP_HK.md)**

- API-Football：`API_FOOTBALL_KEY` **已配置**，但2026/27季Free權限實測不包括；不能視為可用賠率備援
- football-data.org：免費方案 → `FOOTBALL_DATA_ORG_TOKEN`（免費賽程及延遲賽果，無免費賠率）
- Sportmonks：Free Forever → `SPORTMONKS_API_TOKEN`（免費丹麥、蘇格蘭聯賽，不是六大聯賽後備）
- TheSportsDB：官方免費開發者Key `123`，**已接通毋須申請**
- **[GitHub Repository Secrets 設定](https://github.com/CHANCHUNWA1989/football-king-report/settings/secrets/actions)**：私人 Key 只放 Secrets，絕不貼進公開倉庫或聊天。
- **[一鍵 Key 是否已設定檢查（零 API 用量）](https://github.com/CHANCHUNWA1989/football-king-report/actions/workflows/football-king-free-api-keys-check.yml)**：右上 Run workflow → Summary，僅顯示已設定／未設定，唔顯示 Key。
- **[四來源真實免費採集](https://github.com/CHANCHUNWA1989/football-king-report/actions/workflows/football-king-secondary-sources.yml)**：每日自動按額度採集，未設定 Key 自動跳過；唔會改變既有 The Odds API。

> **2026-10-09 最新實測：** TheSportsDB 已收集28場有限賽程；API-Football **Key已加入，但Free方案不允許當季賽事（已安全停止繼續扣額查詢）**；football-data.org、Sportmonks尚無 Key。另已接通無Key的 StatsBomb 歷史資料目錄（80項）；OpenFootAPI 免費 Starter 每月5,000次請求，已備妥程式、等 `OPENFOOT_API_KEY`。配置Key不代表免費季別已獲授權；請看真實採集狀態。


**研究模式 / 非投注建議。** 現時模型概率未經校準，沒有證據顯示可持續跑贏市場。所有正式投注建議維持 `DISABLED／HOLD`。

## iPhone 直接使用

- [📱 足球王者中文網站](https://chanchunwa1989.github.io/football-king-report/)
- [GitHub 雲端自動運行](https://github.com/CHANCHUNWA1989/football-king-report/actions)
- [最新部署與技術限制](DEPLOYMENT_STATUS.md)
- [📱 免費 API Key 三間供應商申請與一鍵驗證教學](API_KEYS_IPHONE_SETUP.md)
- [一鍵安全驗證已加入的 API Key](https://github.com/CHANCHUNWA1989/football-king-report/actions/workflows/football-king-api-key-check.yml)

## 實際已接通的免費賠率 API

- The Odds API V4 的 GitHub Secret 為 `THE_ODDS_API_KEY`；GitHub 雲端已成功使用該 Secret 驗證 API。
- 官方免費方案為每月 500 用量積分。雲端首次聯賽驗證顯示 500/500 及 6/6 聯賽可用；並已**真實採集六聯賽 120 場 1X2 多公司去水市場共識概率**。
- 免費額度係動態數值：2026-10-09 香港時間約13:05 當次測試為已用24、尚餘476／500積分。請以 [最新市場JSON](market/latest.json) 內的 quota 為準。
- 賠率採集香港時間 09:07、21:07 嘗試執行（GitHub 排程可能延遲），僅限一個 EU 地區及 h2h 1X2 市場。
- **硬性額度保護：** 當月已使用達360積分、餘額不足安全保留140積分或配額標頭缺失，停止扣額查詢。此機制會佔用目前每月500免費積分的一部分，但不會自動升級收費。
- 只在 `market/` 保存衍生去水概率、賽事來源及擷取時間，**不保存或公開原始博彩公司賠率與報價明細**；不包含可供直接下注的價格。
- 來源官網：[The Odds API 官方資料及條款](https://the-odds-api.com/terms-and-conditions.html)。

## 自動化系統組件

| 組件 | 現時運作 |
| --- | --- |
| 免費公開賽程 | 英超、英冠、德甲、西甲、意甲、法甲；香港時間每日 03:17／09:17／15:17／21:17 |
| 安全及品質 | 10小時頁面過期警告、失效HOLD、必須顯示研究風險、資料上游時間不明警告 |
| 德甲雙來源 | 2026-10-09 首輪272場身份配對、29場完場賽果可比較、0比分衝突；**唔代表其他五聯賽已獨立核實** |
| 賽前影子模型 | 27場符合研究時序、具準確開賽時間的未校準 Poisson 概率候選 |
| 免費市場基準 | The Odds API EU 地區 h2h 1X2，首次120場市場樣本 |
| 嚴格賽事配對 | 首輪27影子候選只配對7場；20場不一致或無符合時間市場，均排除 |
| 歷史快照 | `history/`、`shadow/`、`market/history/`、`research_pairs/`；按 GitHub 運行編號存檔 |
| 後驗前瞻評分 | `ops/forward_validation.py` 結合**已封存的預測＋較後時間確認完場賽果**，選每場最早一筆，避免重複及偷睇結果 |
| 市場評估 | 自動樣本外 Brier／Log Loss 比較；未有足夠實際已結算配對時 `HOLD` |
| 網站獨立巡檢 | 每6小時驗證頁面、品質、模型、安全旗標、市場新鮮度及配對完整性 |
| 失敗通知 | 嘗試建立 GitHub Issue 並於後續成功後結案；**未經實證可確保推送到 iPhone** |

## 免費版本特別注意

1. 免費額度有限：唔會每場 T-180、T-60、T-20、T-10 分鐘都即時刷價，亦唔會取所有市場或所有博彩公司地區。
2. 市場無水概率唔等於實際可買的賠率；**現時不能可靠計算可執行 EV、CLV 或真實 ROI**。
3. 目前大部分公開賽程唔提供可信準確開賽時刻；2026-10-09 首次檢查207場近期賽事，僅27場可進精準賽前候選。
4. 配對20場失敗時唔會用模糊球隊名或者假定比賽時間硬湊。真正改善需要源資料一致及驗證過的隊名映射。
5. 某些來源缺真正上游發布時間，抓取成功同抓取時間唔能夠證明資料新鮮。
6. GitHub 存檔有 commit 歷史與 SHA，但 GitHub 管理者仍有權更改 Git 歷史，唔可以稱為外部不可篡改記錄。
7. 陣容、xG、傷停、授權賠率歷史（免費回溯）以及完整 V2.8 源碼仍然未有，唔好假稱已解決。
8. 儲存庫係公開，不可上傳 API Key、私人資料或沒有授權嘅原始商業數據。

## 重要程式

- [賠率免費額度及驗證](ops/odds_market.py)
- [嚴格市場／影子配對](ops/market_pair.py)
- [前瞻賽後驗證](ops/forward_validation.py)
- [手機網站發布閘門](ops/release_guard.py)
- [免費賠率自動流程](.github/workflows/football-king-odds.yml)
- [賽程與研究網站流程](.github/workflows/football-king-iphone.yml)
- [網站完整性健康監控](.github/workflows/football-king-watchdog.yml)

**最重要：任何模型評分及市場差異都必須通過足量、前瞻式樣本外驗證，先有資格被考慮用於正式決策。**

## 最新自動修復驗收（2026-10-09）

- 原有117項測試及新增86項測試已全部通過，合計203項。
- 免費賠率批次時間戳改為整批擷取完成時間；並保留各市場自身更新時間，禁止時間倒流或賽中資料。
- GitHub長期證據庫支援重新取最新版本合併、重複賽事去重、矛盾賽果拒絕及同時寫入重試。
- 市場歷史改用 .json.gz 壓縮格式，舊JSON仍可保留；最新市場數據不容許被舊快照反向覆寫。
- 避免程式提交時自動消耗賠率API額度；定時免費採集維持每日日間及夜間各一次。
- iPhone Safari 長開頁面、重新切換頁面及停用JavaScript都有相應嘅資料過期提示。
- 7個嚴格配對只屬未結算研究；未有可靠已結算樣本或足夠樣本外證據，投注決策繼續HOLD。
- [免費賠率及存檔成功驗收](https://github.com/CHANCHUNWA1989/football-king-report/actions/runs/37886933756) ｜ [203項測試及網站部署](https://github.com/CHANCHUNWA1989/football-king-report/actions/runs/37887001630) ｜ [獨立網站監控](https://github.com/CHANCHUNWA1989/football-king-report/actions/runs/37887081704)

## 主動候選推薦功能（2026-10-09 新增）

- iPhone 首頁已有 **「今日研究首選｜主勝・和局・客勝」**：自動從同一時間點、嚴格市場配對的 Shadow Mode 預測揀出有解釋的候選方向，另設觀察名單；聯賽篩選與球隊搜尋會同步更新。
- 輸出 [research_selections.json](https://chanchunwa1989.github.io/football-king-report/research_selections.json)，每場包括主勝／和局／客勝研究選向、未校準模型概率、首選與次選差距、是否與市場無水共識同向、個別原因、賽前時間戳與資料品質。
- **啟用條件**：只有符合預測早於開賽、賠率早於預測、完整三方向市場、報告未過期及嚴格配對的賽事，才有候選資格。模型最高概率至少46%、領先次選至少9個百分點，且市場最高方向一致，才進入「研究首選」。門檻係風控初步篩選，不是經驗證的勝率閾值。
- 免費市場合成概率**不是可執行下注賠率**，模型未經校準，故不提供下注金額、盈利保證、EV或 ROI；`production_recommendations` 永遠 `DISABLED`。
- 2026-10-09 首輪 13 場嚴格市場配對產生 **4 場研究首選、2 場觀察**；其餘因時間或其他資料限制棄權，會按當次運行改變。最新站內以即時輸出為準。
- Safari 分頁持續開啟時會每分鐘重檢時效，研究候選超過10小時自動隱藏，顯示 HOLD。
- 相關程式：[解釋型候選引擎](ops/research_recommender.py)｜[手機顯示](ops/mobile_dashboard.py)｜[風險發布閘門](ops/release_guard.py)｜[獨立健康監控](ops/watchdog.py)。
- [首次成功4場研究選向及網站發布雲端證據](https://github.com/CHANCHUNWA1989/football-king-report/actions/runs/37897181579)，原版117+新增146項測試共263項通過。

**研究首選唔等於正式投注建議。** 正式投注資格必須另有已結算樣本、前瞻驗證、真正可執行賠率及人手確認，目前繼續 HOLD。

## 免費賠率用盡時嘅自動後備選向（2026-10-09）

系統已接入**三級免費研究後備模式**，絕不因配額不足而偽造即時賠率：

1. **正常市場對照**：有合法且時間有效嘅 1X2 免費賠率時，仍用「模型＋市場方向一致」選出研究首選。
2. **緩存賠率**：到達免費配額安全保留線或供應商沒有新賠率，賠率採集流程保存本次額度狀態到 `market/collection_status.json`，**唔會用空白 HOLD 覆蓋最後一份有效的 `market/latest.json`**。原快照只可以喺其真實時間有效範圍內使用。
3. **純模型低證據觀察**：若再冇合資格市場配對，`ops/research_recommender.py` 會自動從仍然新鮮嘅 Shadow Mode 賽前候選選出最多5場觀察方向（模型首選至少60%且比次選高18個百分點）。在 iPhone 顯示於**獨立嘅「免費賠率不足｜純模型低證據觀察」**欄，絕不混入有市場確認嘅首選。

不論三種模式，**如賽事開波不足60分鐘、候選本身過期逾10小時、身份或機率異常、缺開賽時間、資料風控HOLD，均自動棄權**。60%同18百分點係研究保守篩選參數，**唔代表經統計驗證的真實勝率**。不顯示可下注賠率、投注金額、推算 ROI、聲稱正EV或盈利保證；正式推薦狀態繼續 `HOLD／DISABLED`。免收費資料並非合法可用嘅任意賠率替代品，唔會私下爬取博彩公司網站。

系統開發驗收：原版117項＋附加156項＝**273項測試成功**；真實網站及歷史存檔已成功發布。**配額耗盡後切換嘅路徑已經過模擬回歸測試，但當日實際賠率配額未耗盡，因此不能聲稱曾真實耗盡配額並經現場驗收。** [驗收紀錄](https://github.com/CHANCHUNWA1989/football-king-report/actions/runs/37898870712)

## 四個額外免費足球渠道（2026-10-09）

已加入四個來源嘅獨立 GitHub Actions 自動採集、安全存檔及 iPhone 接駁。

- TheSportsDB：**已實際連線**，初輪6場；2026-10-09擴展查詢後六聯賽取得**28場**免費賽程樣本，毋須自行設定 Key；屬截斷免費資料，唔係完整賽程。
- API-Football：**API_FOOTBALL_KEY 已設定**；2026-10-09真實測試回覆免費戶口無當季球季存取權，因此資料0場，程式檢測到後只查一次即停，唔再白扣另外11次，亦唔假稱係可用免費賠率。
- football-data.org：已預備六聯賽賽程／延遲賽果（每天最多6次），待 Secret：FOOTBALL_DATA_ORG_TOKEN。
- Sportmonks：已預備免費聯賽權限檢查（每天最多2次），待 Secret：SPORTMONKS_API_TOKEN；免費方案只包丹麥同蘇格蘭聯賽，**唔能夠補齊現有六聯賽**。
- 所有新來源只供賽程及來源核對，唔會將欠缺時間戳或未授權報價當成已驗證投注價值。現有正式投注資格仍維持 HOLD。

[四來源詳細接駁說明、iPhone API Key 操作及實際限制](EXTRA_FREE_SOURCES.md) ｜ [四來源每日工作流程](.github/workflows/football-king-secondary-sources.yml) ｜ [最新真實來源狀態](sources/latest.json)

## 全球／小型聯賽公共領域資料（2026-10-09已實測）

**已真正加入兩個無密鑰來源：** [OpenFootball JSON](https://github.com/openfootball/football.json)（CC0資料）及 [OpenLigaDB德國免費API](https://api.openligadb.de/)；同 The Odds API 賠率查詢完全獨立，唔會扣其免費500積分。

- OpenFootball：**27／27賽季檔案成功讀取**。當中9個目前對應2026-27（巴甲2026）賽季，涵蓋英超、英冠、德甲、西甲、意甲、法甲、荷甲、葡超、巴甲。另18個屬**歷史賽季**，包含德乙、英甲、英乙、意乙、法乙、西乙、奧甲、奧乙、比甲、蘇超、希超、土超、阿根廷甲、巴乙、中超、哥倫比亞甲、日職J1及美職聯；**不可當作今季實時賽程**。
- OpenLigaDB：2026賽季德甲／德乙／德丙三個接口全部成功，分別取得306／306／380項賽季賽程紀錄，帶來源所提供嘅 UTC 時間。即使已取得比分，都唔代表已雙來源獨立驗證。
- 合共**30個聯賽／賽季／供應商來源組合，30／30成功下載**；其中德甲、德乙可能有兩個來源，唔代表30個互不重複嘅今季聯賽。
- **自動後備：** 香港時間每日約07:33進行免費採集，保留 `sources/wide_latest.json` 及日期壓縮歷史，iPhone 中文網站新增全球及小型聯賽覆蓋清單、德國近期 UTC 備用開賽時間、今季與歷史分組。
- **時間安全：** 自動跨年切換2027-28等新賽季來源，舊檔只能歸類歷史。OpenFootball 沒有標記時區的本地開球「time」唔當UTC，亦唔會自動餵入預測、當賠率或正EV證據。
- API-Football有你已存放嘅Key，但免費當季資料仍未獲實測成功；football-data.org同Sportmonks新Key可按需日後自行申請，**唔好喺對話貼任何密鑰**。本次30組免費來源唔需要額外Key。
- [30／30真實採集成功](https://github.com/CHANCHUNWA1989/football-king-report/actions/runs/37916957821)｜[335項測試、網站部署成功](https://github.com/CHANCHUNWA1989/football-king-report/actions/runs/37917633950)。

**上述係免費賽程／歷史研究後備，唔等於正式投注賠率或模型能夠預測所有小聯賽。正式建議繼續HOLD。**

**四個額外API最新驗收：** TheSportsDB 28場／24次免費請求；API-Football Key 已存在但免費2026球季不開放；football-data.org、Sportmonks兩個私人Key仍未設定。真正最值得下一步啟用係 [football-data.org 的免費賽程及延遲賽果](EXTRA_FREE_SOURCES.md)，並唔係另一個可免費獲得即時實盤賠率嘅替代品。[真實採集成功紀錄](https://github.com/CHANCHUNWA1989/football-king-report/actions/runs/37918598937)。

## 2026-10-09 免費賽程覆蓋擴充／時間一致性防護（最新實測）

- **TheSportsDB 無需私人Key**：六大聯賽免費V1從「各聯賽下一場、上一場、今明兩日」擴大為**四日有界滾動窗口**，每日香港時間05:43及17:43各自採集一次，亦可以由iPhone在Actions頁面按 Run workflow 手動更新。每次最多36次請求，無限流時實測**47場**獨立賽程樣本，英超8、英冠6、德甲7、西甲9、意甲9、法甲8；供應商新鮮度會隨排程變動。之前快速連查曾喺第31次遇429並令法甲取得0場；**採集已加約2.35秒間隔**，再測36次成功、無429。此數值係某次快照，唔係每日固定保證。
- 新增 `ops/fixture_consensus.py`：將TheSportsDB等合法來源，同OpenLigaDB嘅**精準UTC開賽時刻**交叉核對；來源過期、只有本地日期或賽事身份配唔準都唔當已核實。某場如出現45分鐘以上、7日內嘅開賽時間差異，**即從市場研究首選與純模型後備觀察名單剔除**。只用於「顯示當刻安全棄權」，絕不事後改封存模型概率。
- **首輪實測**：27場具精準開賽時間候選，發現5筆外部UTC時間一致觀察、0場須隔離嘅時間衝突；不代表全27場已獨立核實、更唔代表賽果獨立核實。
- 重新建立先前遺失嘅 `ops/tests/test_secondary_sources.py` 測試，包括免費API季別限制、無Key跳過、供應商限流、不得外洩密鑰、六聯賽公平輪流查詢；網站獨立巡檢亦檢查隔離過嘅賽事唔會重新變成研究推薦。
- **免費限制仍在**：API-Football Key雖已加入，但當季Free權限未開；football-data.org、Sportmonks、OpenFootAPI仲要用戶自行建立相應Secrets；免費TheSportsDB係截斷賽程資料，唔提供可直接下注嘅實時1X2報價。The Odds API既有免費賠率繼續獨立維持配額保護。
- [開啟手機網頁](https://chanchunwa1989.github.io/football-king-report/)｜[免費來源採集workflow](https://github.com/CHANCHUNWA1989/football-king-report/actions/workflows/football-king-secondary-sources.yml)｜[首輪獨立跨來源網站驗證](https://github.com/CHANCHUNWA1989/football-king-report/actions/runs/37926667170)｜[實測47場免費來源資料](https://github.com/CHANCHUNWA1989/football-king-report/actions/runs/37926722487)

**網站及賠率屬按排程更新，並非秒級即時。想即刻再查，可由iPhone打開Actions、選擇上述免費來源workflow、按Run workflow；之後等網站下一輪發布刷新。**

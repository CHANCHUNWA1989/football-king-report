# 足球王者 V4.1｜2026-10-09 實際部署及驗收

## 已證實的操作與數據

- GitHub Secret `THE_ODDS_API_KEY` 已經成功用於 The Odds API V4 的**真實免費聯賽目錄查詢**。六大聯賽 active。
- 六大聯賽真實採集120場1X2衍生市場概率；2026-10-09 香港時間約13:05 最後一次驗證已用24積分、尚餘476／500積分。最新餘額以 [市場數據紀錄](market/latest.json) 為準。
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

## 最新自動修復驗收（2026-10-09）

- 原有117項測試及新增86項測試已全部通過，合計203項。
- 免費賠率批次時間戳改為整批擷取完成時間；並保留各市場自身更新時間，禁止時間倒流或賽中資料。
- GitHub長期證據庫支援重新取最新版本合併、重複賽事去重、矛盾賽果拒絕及同時寫入重試。
- 市場歷史改用 .json.gz 壓縮格式，舊JSON仍可保留；最新市場數據不容許被舊快照反向覆寫。
- 避免程式提交時自動消耗賠率API額度；定時免費採集維持每日日間及夜間各一次。
- iPhone Safari 長開頁面、重新切換頁面及停用JavaScript都有相應嘅資料過期提示。
- 7個嚴格配對只屬未結算研究；未有可靠已結算樣本或足夠樣本外證據，投注決策繼續HOLD。
- [免費賠率及存檔成功驗收](https://github.com/CHANCHUNWA1989/football-king-report/actions/runs/37886933756) ｜ [203項測試及網站部署](https://github.com/CHANCHUNWA1989/football-king-report/actions/runs/37887001630) ｜ [獨立網站監控](https://github.com/CHANCHUNWA1989/football-king-report/actions/runs/37887081704)

## 主動推薦功能的最新驗收（2026-10-09）

- 解釋型研究候選引擎 `ops/research_recommender.py` 已經接入每日網站發布流程，無需額外扣 The Odds API 積分。
- 真實 GitHub Actions 運行已完成 **117 原有 + 146 新增 = 263 項測試全部通過**，Pages 發布、研究歷史封存及故障恢復皆成功。
- 當輪 `market_comparison.json` 中有13場嚴格賽前市場配對，`research_selections.json` 成功輸出4場研究首選、2場觀察，其餘未符合新鮮度／時間或選向門檻。
- 公開手機頁面有「今日研究首選｜主勝・和局・客勝」，同時寫明概率未校準、未驗證正EV、沒有可執行賠率、不提供下注金額。
- 網頁超過10小時未更新，包括 iPhone Safari 長時間保留分頁時，研究推薦區會顯示 HOLD 而不繼續列出過期選向。
- 發布前 `ops/release_guard.py` 核對推薦必須來自有效市場配對、數量相符、明確安全旗標及推薦區塊存在；獨立 watchdog 亦會檢查網站公開 JSON，避免虛構賽事或可下注宣稱。
- [263項測試、推薦輸出、Pages 實測](https://github.com/CHANCHUNWA1989/football-king-report/actions/runs/37897181579)。
- **正式投注仍 HOLD**：累積已結算前瞻市場配對樣本0場，未有證據證明模型優於市場。每日研究方向可供觀察，不可視為盈利保證或真正可執行投注建議。

## 2026-10-09 免費配額不足後備研究選向

- `ops/research_recommender.py`：配額保留線觸發或沒有嚴格市場配對時，啟用額外 `MODEL_ONLY_LOW_EVIDENCE` 名單；最多5場，必須仍有新鮮賽前模型、60%以上未校準首選機率、首選與次選相差至少18百分點；列明無市場證據、非下注建議。時間不合或模型品質異常時不推薦。
- `market/collection_status.json`：免費 Odds API 採集成功／HOLD及免費剩餘額度獨立保存；採集失敗或保留額度時，不以空檔覆蓋最後一次合資格市場概率快照。只會利用仍然符合時間點要求嘅已封存賠率。
- `ops/mobile_dashboard.py`：iPhone 研究首選同低證據純模型觀察**分兩個區域**，兩者跟隨聯賽篩選；Safari 分頁超時會清空舊方向。
- `ops/release_guard.py`＋`ops/watchdog.py`：新增純模型降級時嘅重複賽事、假稱有市場確認、金額提示及自動啟用投注嘅拒絕規則。
- 雲端一次完整發布驗收 **273／273 測試通過**，網站及存檔成功。參考：[GitHub Actions 37898870712](https://github.com/CHANCHUNWA1989/football-king-report/actions/runs/37898870712)。
- 當次實際仍有免費餘額，**配額見底路徑係模擬試驗通過，尚未有真實耗盡額度後嘅長期運行觀察**。正式投注仍 HOLD。

## 2026-10-09：全球／小型聯賽免費資料備援實測

- [OpenFootball 公共領域JSON](https://github.com/openfootball/football.json)：27／27個賽季／聯賽檔案真正成功讀取，包括**9個目前對應2026-27或2026現季檔**及**18個舊賽季檔**（不可稱當季實時）。
- [OpenLigaDB API](https://api.openligadb.de/)：德甲bl1、德乙bl2、德丙bl3 全部成功，當季賽季資料各306／306／380筆。可用於備用賽程核對（按來源提交 UTC），但賽果未完全獨立驗證、免費資料存在社群編輯風險。
- 總共30個來源／聯賽檔組合，首輪**30／30已下載**，歷史與重複來源分開計數；唔係30個保證今季實時嘅聯賽。
- 全新無密鑰工作流程 `.github/workflows/football-king-wide-free.yml` 每日香港時間07:33採集，獨立 `sources/wide_latest.json` + `.json.gz` 歷史存檔、衝突重試、故障通知；**零 The Odds API 額外積分，毋須使用者新Key**。
- 以 `ops/wide_source_guard.py` 強制驗證季別、時間戳、30項來源身份、無水市場價格禁宣稱、每次最大請求數和未核實賽果限制；`ops/wide_overlay.py` 提供手機可展開式今季與歷史聯賽清單、德國UTC備用賽程。安全閘門及 watchdog 亦新增隔離。
- **335項自動測試通過**（117原版+218新增），最後網站部署成功；GitHub有獨立成功證據，未作所有 iPhone 裝置實機點擊驗收。
- 免費供應商更新唔保證真實賽事資料每日日更。OpenFootball 當地無時區 `time` 不能假稱精準UTC，不會直接變成影子模型證據或實盤選向。
- 本次實際驗收：[30項免費資料採集／封存](https://github.com/CHANCHUNWA1989/football-king-report/actions/runs/37916957821)｜[335項測試＋網站部署](https://github.com/CHANCHUNWA1989/football-king-report/actions/runs/37917633950)。
- 正式投注繼續 `HOLD`；跨國免費賽程備援唔等於市場賠率備援，亦唔等於新小聯賽已完成模型訓練、時間點驗證及校準。


## 2026-10-09：六個 API／資料供應商真實接駁及新增免費研究資料

**最新驗證結果：原版117＋附加235＝352項測試全部通過；網站發布及獨立研究歷史封存成功。**

- The Odds API：仍有六聯賽120場已封存去水1X2概率；當次歷史配額報告476／500剩餘，非即時查詢。未提供真實可下注價。
- TheSportsDB：24次有限免費查詢取得28場賽程樣本，已有2場開賽時間可與原候選一致核對；非六聯賽完整資料。
- API-Football：`API_FOOTBALL_KEY` 已存在，實際Free回應 `FREE_CURRENT_SEASON_NOT_ENTITLED`，當次只試1次就停止。**唔可以聲稱當季免費賠率接通。**
- football-data.org：`FOOTBALL_DATA_ORG_TOKEN` 尚未設置，接駁程式存在，無可用資料。
- Sportmonks：`SPORTMONKS_API_TOKEN` 尚未設置，免費範圍只有丹麥及蘇格蘭指定賽事，不屬六大聯賽賠率備援。
- OpenFootball + OpenLigaDB：既有27個歷史／當季來源檔與德國三聯賽備援已成功；資料年份、精準UTC時間及上游發佈日期仍須如實標示。
- [OpenFootAPI 免費Starter](https://openfootapi.com/pricing)：新增`ops/research_extensions.py`安全接駁、最多3個免費基本請求／日，需 `OPENFOOT_API_KEY`（目前未設）。免費方案5,000請求／月，基本賽程、賽果、排名，**xG及衍生賠率不在免費方案**，無憑據不會使用共用Demo Key做定時資料。
- [StatsBomb Open Data](https://github.com/hudl/open-data)：**真正下載官方80個歷史competition-season目錄**，無需Key；只用於供應商可用性及歷史覆蓋研究，尚未啟用賽事事件特徵；發布／署名必須遵循原站授權。
- 還發現合法歷史研究集：[Pappalardo／Wyscout CC BY 4.0 2017-18五大聯賽](https://doi.org/10.1038/s41597-019-0247-7)、[Impect 2023-24 德甲歷史事件資料](https://github.com/ImpectAPI/open-data)；**只完成來源研究，尚未加作當季預測變數**。
- 已修正GitHub Key檢查包含OpenFoot，並喺iPhone網站新增「新發現免費研究來源」及「四個額外免費資料渠道」兩個有別的資訊區；正式投注安全資格照舊HOLD。
- API使用條款／上游權利不會因聚合服務免費而消失；特別不以Football-Data.co.uk未獲許可的自動AI抓取作備援。
- **全流程驗收**：[352項測試及新API狀態網站發布](https://github.com/CHANCHUNWA1989/football-king-report/actions/runs/37920902436)｜[StatsBomb 80項目及OpenFoot免費Key檢測](https://github.com/CHANCHUNWA1989/football-king-report/actions/runs/37920170058)｜[四供應商真實採集](https://github.com/CHANCHUNWA1989/football-king-report/actions/runs/37918598937)。
- 最新完整進度及iPhone操作：[FREE_API_PROGRESS_2026_10_09.md](FREE_API_PROGRESS_2026_10_09.md)。實時更新結果以 GitHub Actions 最近成功運行為準。


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

## 2026-10-09 最新免費來源覆蓋／獨立開球時間守門（新增）

- 六聯賽可免費讀取嘅 TheSportsDB V1 賽程樣本由28提升至47；實際36次請求已成功、0次429，六聯賽現有樣本8/6/7/9/9/8（英超、英冠、德甲、西甲、意甲、法甲），係當次查詢窗口而非完整當季覆蓋。
- 曾快速執行36次導致約第31次出現429，採用有界4日滾動查詢、約2.35秒節流及輪流公平查詢；有節流仍可能因公共服務負載而遇429，會保留PARTIAL並停止後續索取，唔用假資料。
- 新增加 `fixture_integrity.json` 公開資料：同TheSportsDB、OpenLigaDB等來源比對UTC開賽時間，只有身份、精準時間及合法近期快照符合，先可顯示一致觀察；時間差異45分鐘以上且位於7日內，隔離研究首選/模型後備。
- 第一輪有27個影子候選、5筆獨立時間一致觀察、0個已確認時間矛盾。唔可以用呢個數據宣稱所有賽程已核實，亦冇獨立核實六聯賽全部完場賽果。
- iPhone網站已顯示免費來源狀態、跨來源時間核對及要人工覆查嘅名單；GitHub獨立監控會擋住已隔離賽事意外出現在推薦中。
- **暫未解決**：六聯賽完整時區可靠開波時間、法定可發布嘅實時賠率備援、API-Football Free當季季別權限、其他供應商Key、前瞻樣本長期累積。所有正式投注依然HOLD。
- [完整網站部署驗收](https://github.com/CHANCHUNWA1989/football-king-report/actions/runs/37926667170)｜[47場四日免費來源實測](https://github.com/CHANCHUNWA1989/football-king-report/actions/runs/37926722487)

## 2026-10-09 免費資料快速更新與來源核對驗收

- **德國足球快速更新**：已加入 OpenLigaDB 社群API，德甲、德乙、德丙每小時嘗試查詢當前輪次（最多3次公開請求，無需Key），獨立封存資料到 sources/live_germany_latest.json 及壓縮歷史。OpenLigaDB 屬 ODbL 社群資料，唔係官方保證即秒更新。
- **兩來源資料準確度**：用TheSportsDB已保存的時間有效資料核對開賽時間與球隊名稱白名單，仍然唔會用一個單一來源宣稱已核實。當次28場（德甲9、德乙9、德丙10），其中6場有兩個出版者的開賽時刻一致，22場僅一個來源，沒有觀察到時間衝突；沒有完整六聯賽賽果獨立核驗。
- **iPhone首頁新賽程面板**：有自行刷新、三德國聯賽篩選、香港時間、社群來源及ODbL署名；從本公開GitHub倉庫動態取檔，快照超過150分鐘自動HOLD，避免Safari長開見到過期賽況。
- **六大聯賽覆蓋**：TheSportsDB免費下一場／上一場＋逐日查詢範圍由4日擴闊至6日，48次有延時請求（仍每分鐘少於30次），最新取得53筆賽程觀測（之前47筆），但是官方每次免費日查詢只限三場，所以唔可以話已覆蓋全部賽事。
- **既有研究模型真實限制**：主報告207場，只有27場具模型可用精確開賽時間；最新嚴格賽前市場配對18場；前瞻已結算市場可比較樣本仍為0，未能核實盈利能力。API-Football已設定Key但免費帳戶無權讀取當季；football-data.org仍需擁有者自行加入免費Token；免費版比分會有延遲。
- **驗收證據**：原V4.1 117項測試＋322項獨立測試全部成功；網站、存檔、四來源與德國快速資料流程已實際執行成功。詳情：
  - https://github.com/CHANCHUNWA1989/football-king-report/actions/runs/37928738267
  - https://github.com/CHANCHUNWA1989/football-king-report/actions/runs/37928539272
  - https://github.com/CHANCHUNWA1989/football-king-report/actions/runs/37928026687
- **安全政策**：所有新來源只係資料覆蓋、時刻或歷史結果核對；OpenFootball沒有可信時區的場次不得假定UTC；唔會偽造即時可買賠率、已驗證EV、ROI或正式投注資格。正式下注推薦繼續HOLD／DISABLED。

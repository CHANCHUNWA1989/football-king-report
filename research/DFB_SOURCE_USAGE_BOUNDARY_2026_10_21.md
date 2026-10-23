# DFB 特定來源用途限制及停止自動擷取（#303）

本輪處理父工單 #274 的一項實際來源使用缺口：現有 collector 與 CI／每日流程會直接請求 DFB Datencenter 的德甲 2026–27 當前輪次頁面，沒有已確立的自動擷取及公開原件封存許可。此修補不認證賽果，不實作 admission，亦不增加正式資格樣本。

## 新查明的官方文件與範圍

2026-10-21 本輪兩位助理分別讀取 [DFB 官方 Nutzungsbedingungen](https://www.dfb.de/nutzungsbedingungen)。獨立研究紀錄的讀取時間為 19:00:40Z；Firecrawl `maxAge:0` 處理結果回報 HTTP200。這是 processed 文件閱讀，不是原始 HTTP bytes、永久簽封或新的 Sigstore 證明。正文及 metadata 未明示生效日期，不能把讀取時間當成條款生效日。

- §1.1 說明 DFB portals／apps 的一般適用範圍；§1.2 明確保留特定 portal／app 條款優先或補充。本輪未取得適用於專案的自動採集／公開 raw archive 許可或例外。
- §5 的未授權介入項目明列「automatisierte Verfahren zum Abgreifen von Daten, wie Datencrawling und Datenscraping」。
- §7.1 對受保護內容的私人用途及其他用途事先同意分開處理；其私人、非商業 widget 例外不等於准許本專案自動擷取並公開封存原件。
- §7.3 明列職業足球 Liveticker（包括 Bundesliga、2. Bundesliga、3. Liga 等）資料的獨家權利在 SID Sport-Informations-Dienst GmbH。這是比一般新聞 imprint 更具體的產品類別權利人聲明；它不是逐場原始採集審計，不能證明 SID 是本場實際採集者，亦不能證明 NDR／OpenLiga 同源或互相獨立。
- 同一 §7.3 的 DFBnet／FUSSBALL.DE 路徑說明屬業餘足球資料，不能移植成職業 Liveticker 的來源鏈。

工程處置只針對既有固定 `datencenter.dfb.de/de/competitions/bundesliga/seasons/2026-2027/matchday/current` 自動請求。這不是對所有 DFB 產品、個別事實或所有資料用途的法律結論。之後如取得適用許可，仍須另行覆核具體範圍及程式；caller 旗號不能自行開啟。

## 當季採集規則的新實查，仍未連到本場 feed

官方 [2026/27 Medienrichtlinien 執行細則](https://media.bundesliga-gruppe.de/sites/2/2026/07/Durchfuehrungsbestimmungen-Medienrichtlinien-2026-2027-2026-07-01-Stand.pdf) 封面為2026/27 Version1.1；官方索引／檔名／metadata標示 Stand:01.07.2026，本文不把這個日期冒充正文另列的生效條款。第9頁 §2.3 現已讀取正文，並非只看目錄：與 Sportec Solutions 或 Bundesliga e.V. 有協議的服務商，可為場內官方事件／位置資料採集取得認證；另列 Sportradar 的資料第三方授權及非攝影方式場內採集。這是當季認證／採集資格規則，比2016歷史公告更具體。

該段不證明任何供應商已在83212該場實際採集、不證明特定 NDR／OpenLiga feed 的上游、不授予本專案免費 API 或公開原件重用權，亦不保證兩條資料流互相獨立。第10–11頁對 audio／新聞記者另有不同認證安排，不能把 §2.3 擴大成所有報道都只有兩家來源。

本輪一次有界、拒絕轉址的原始 PDF 請求，requested19:03:29.404554Z／completed19:03:30.972404Z，HTTP200、`application/pdf`、911667 bytes、SHA256 `24bb81a843f26f977f131423adf99da8b659cdce82ddb9366213258bdc2a435b`。原件只在本地作政策閱讀，沒有公開再發布或新的永久 Sigstore 證明；未將它補入任何舊 seal 或認證樣本。後續要取得的是具體產品與賽事的實際採集、來源關係及允許用途原件。

## 程式界線與可驗收行為

`collect()` 在呼叫依賴注入 getter 前略過 DFB；`fetch()` 直接接收該 DFB URL 時，在建立 opener／發出請求前固定拒絕。沒有使用者參數或環境變數解鎖。原 `SOURCES` 身份表保留，只供精確歷史身份及原件重播使用。

新的 collector manifest 使用 `football-king-external-raw-evidence-v3`。DFB 的 `SKIPPED_POLICY` 記錄固定原因與上述條款網址；`requested_utc`、`completed_utc`、`final_url`、`http_status`、`redirect_policy` 全為 null，沒有虛構 GET／HTTP／原始 bytes 證據。NDR 繼續原有最多一次、有界、拒絕轉址的 index 請求；這不新增 NDR 使用許可或獨立認證。

v1／v2 原件及原有 schema 語義不變；v2 仍要求原先兩個真實嘗試收據，不能塞入新略過紀錄。新 v3 只接受精確 DFB 略過形狀，拒絕 fetched DFB、假略過時間／原件／額外欄位、未知政策及升格聲稱。新 manifest 與 NDR 原件照既有內容重播，不改寫舊簽封。

驗收包括先失敗後修復的 DFB 零請求正反例、NDR 成功／失敗／轉址及時間邊界、v3 形狀與版本隔離、舊原件重播、獨立覆核及相關完整 CI。實際測試數、精確 commit、原生發布與讀回結果以 PR 驗收紀錄為準，不預先把尚未完成的檢查寫成通過。

## 正式推薦仍欠甚麼

本輪沒有取得合格獨立第二來源、固定跨源 fixture／team 橋接、actual kickoff 或獨立 regulation 90 分鐘加補時 FT 原件。凍結 `result_sources_v1.json` 及其 SHA256 `33abd884142cc8000844d82cf9886446e4fe27a823f95577d06e4f8d232c6463` 不變；這次用途調查不升格成來源獨立政策。

仍需用實際原件完成首場可信 admission，再取得足夠同場前瞻校準及市場優勢證據。0 場已認證、0 合資格週，原最低 300 場／12 合資格週／4 聯賽等門檻不變；完整四方同場的未認證樣本只有 6。不能承諾正式推薦日期，亦沒有證據顯示本輪提高命中率。HOLD／DISABLED。

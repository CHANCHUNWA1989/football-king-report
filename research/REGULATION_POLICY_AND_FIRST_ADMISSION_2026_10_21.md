# 十二碼圖示政策及首場可信驗收缺項（2026-10-21）

本輪工單 #291 修正一般十二碼圖示被當成互射十二碼的觀察誤判。這不認證賽果，不新增已認證樣本，亦不完成正式推薦資格。父工單 #274 的來源、實際開波及獨立90分鐘賽果驗證仍未完成。

## 可重驗缺陷及版本界線

永久原件 `ndr_capture_provenance/2026/10/21/39534272252-1/ndr-capture.tar.gz` 的固定 NDR 賽事5988頁面，原始 HTML SHA256 為 `1d6af817ecf2c48700056d2c2d4d43e75fdef755cc77b3e7554cdaed124e0b0b`。原有規則因普通射入／射失十二碼圖示的 `Penalty` 文字而隔離該頁。

新政策 `NDR_REGULATION_EVENT_ICONS_V2` 只容許兩組完全相符的圖示路徑及 alt，且須位於同場自身事件、可見、只有圖示及空白的獨一 subhead，以及有效自身事件時鐘內。明示互射十二碼／加時、未知圖示、錯誤 alt、隱藏或跨範圍圖示、晚於完場時鐘及比分矛盾仍拒收。獨立覆核發現的 subhead 夾帶互射十二碼文字，亦有先失敗後修復的負例。

新擷取明文使用 completion report／manifest **v3** 及新 parser policy。v1／v2 永久固定舊 `NDR_COMPLETION_DISPLAY_V1` 語義；不能以修正後政策重寫舊簽封的觀察或隔離結果。舊原件5988仍隔離，新的同 bytes 解讀只可產生獨立、未認證觀察。認證、評分、正式資格旗號全部維持 false，HOLD／DISABLED。

## 本輪官方文件調查

以下為2026-10-21 UTC有界 HTTP 文件調查，並非新的永久簽封或當次 Sigstore 驗章。兩組調查各6個官方文件／發現請求，沒有新增體育資料 GET。

### OpenLigaDB

- 官方首頁連至 API；API UI 的 `index.js` 指定 [實際 OpenAPI 規格](https://api.openligadb.de/swagger/v1/swagger.json)。HTTP200，擷取完成07:44:59.846948Z，44,677 bytes，SHA256 `ca2eb416a4c68f234c1d0989302c0d9ee3ae5fffce175d02a05cdb599f44577b`。先前猜測路徑404不表示官方文件不存在。
- `/getresulttypes` 明列 `HalfTime`、`After90Minutes`、`AfterExtraTime`、`AfterPenalties`、`Unknown`；`MatchResult.resultTypeKind` 為 nullable string。這支持 provider 聲稱的期間分類，不認證結果真偽。不能只憑 typeID2、陣列次序或「完場」升格為90分鐘真賽果。
- 首頁直接連出的 [官方 Samples README](https://github.com/OpenLigaDB/OpenLigaDB-Samples/blob/master/README.md)，07:44:59.781592Z 經 GitHub default-branch README API 取得；decoded SHA256 `0c15eeba23970c2434f25b90c7dbf7f8f29225a3a59a4565badb31748b1be9b3`，Git blob `1f2e98fcb293b7b05557438ce41dd3e963bf8b16`。其原文：

  > Anders ist es bei den Spielergebnissen, diese können von JEDEM angemeldeten User editiert werden. Nach einer Zeit von 6 Tagen nach Spielende ist das Editieren der Ergebnisse nur noch dem Administrator der Liga möglich.

  社群編輯權限不是特定 bl1/2026 賽果的原始採集或上游審計，亦不證明與 NDR 獨立。
- 公開 Match schema 及 endpoint 清單沒有逐場採集者、upstream、修改者審計或獨立 actual kickoff 證據。這是本次公開文件的缺項，不能推定私下沒有紀錄。`matchDateTimeUTC`／`lastUpdateDateTime` 不能自行當成實際開波。
- 規格列 ODbL1.0、免 key，但要求節省讀取及每 IP 每分鐘60次；免費不等於無限制或所有內容均獲公開重用授權。既有 ODbL 保存、署名及其他權利界線繼續生效。
- 已封存 bl1/2026 原件306行、54行 provider-claimed finished／typeID2 `After90Minutes`，raw SHA256 `280f2e8d7383fda61167224bfe2a9098f71f6f01a9984313cc0611560b7a01c3`。文件只補足期間欄位的語義；不補來源獨立、實際開波或真實比分認證。

### NDR／HEIM:SPIEL

- [NDR imprint](https://www.ndr.de/service/impressum)，HTTP200，07:44:30.787725Z，SHA256 `18fd7f441b00d10b6b769a544495932ae7a7ddf7926157a24369a2244e425f57`，只列通用 `Nachrichtendienste: AFP, dpa, epd, KNA, Reuters, sid`，沒有指定 Bundesliga90分鐘 feed 的採集及上游。
- [HEIM:SPIEL imprint](https://heimspiel.de/legal/imprint/)，HTTP200，07:44:32.587097Z，SHA256 `146f1bfaa2c24e7e879318516ae70bb74c643a420389c1344241cf4bb2b11bad`，說明公司／編輯責任，未提供特定 NDR 賽果產品、賽季、期間及原件保存重用授權。
- HTML 的 `heimspiel_shorthand` 是技術 tracking ID；不同 URL、網站名、hash、通用 SID credit 或搜尋沒有結果，都不能證明獨立採集。原件5946只有2026 metadata；本文不由文字提及其他賽事推斷較早年份。

兩來源關係仍 **UNKNOWN**。沒有新增來源政策的 VERIFIED 分類。

## 首場驗收所需具體輸入與輸出

可先準備前瞻證據收集案：OpenLiga matchID **83212**，teamIDs **16／87**，原記錄 scheduled kickoff **2026-10-23T18:30:00Z**（香港24日02:30）。此為未認證身份線索，並非推薦或正式啟用日期；不得改寫原封存。既有同 provider ID 連結不等於跨源配對。

| 缺項 | 必須取得的原始輸入 | 合格前狀態 |
|---|---|---|
| 來源身份及用途 | 指明該 feed／賽季／結果期間的出版社聲明、允許用途及採集審計 | UNKNOWN |
| 上游獨立 | 兩方明確原始採集／上游依賴原件，覆蓋該場90分鐘結果 | UNKNOWN |
| 固定跨源身份 | 原件支持的 fixture／team ID 橋接及矛盾隔離 | UNAUTHENTICATED |
| 實際開波 | 獨立 actual kickoff 原件；不能只用賽程或修改時刻 | UNVERIFIED |
| 90分鐘完場 | 同場、同期間、確實獨立的比分原件及擷取／永久驗章鏈 | UNVERIFIED |
| 原封存連結 | 當次 CLI 重驗原預測封存，配合上述身份／實際開波 | INCOMPLETE |

取得肯定證據後，需另開版本化可信 admission 工單，輸入原件、逐次擷取 metadata、簽封、精確身份及範圍化來源政策，輸出逐條可重驗通過／拒絕原因、證據引用及認證 cohort。未知、衝突、錯場、錯期間、共享上游、過時或改寫原件均拒絕。現有 `recommendation_readiness` 仍明文 `TRUSTED_EVIDENCE_VERIFIER_NOT_IMPLEMENTED`；本輪沒有偷偷加一條認證捷徑。

## 正式推薦仍未達標

本輪唯讀審計的底層 settled 資料時間為2026-10-20T22:09:47.305936Z：45個未認證研究紀錄、0個獨立認證、0個正式資格樣本；完整 A／B／C／市場同場 cohort 只有6個未認證樣本。模型命中22/45（48.89%），市場28/45（62.22%）；模型 logloss1.007721／Brier0.608050，市場0.968024／0.577453，模型仍較差。

原有300場、12個合格週、4聯賽各40場及市場優勢／校準／不確定性要求不變；獨立 four-model1000 門檻亦不變。研究紀錄的日曆週數不是合格週數。先完成首場真實認證及可信 admission，再累積足夠同場前瞻證據；不能由今日開始倒數12週、保證命中率，或把本輪工程測試當成預測提升。

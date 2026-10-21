# 特定賽果 feed 證據與有界覆蓋（#274）

本輪把可立即修正的採樣缺口與仍待外部原件支持的認證條件分開記錄。來源政策、舊預測／賽果／ledger 及正式門檻不變。本文記錄調查及工程驗收條件；實際發布與原生驗收結果另以本輪 PR／Actions 記錄為準。

## 原站調查：有混合來源線索，沒有逐場獨立採集證明

2026-10-21T02:33:42.915513Z 至 02:33:44.079684Z 讀取 [heimspiel 官網](https://heimspiel.de/)，HTTP 200、原始 HTML 219,547 bytes，SHA256 `e9a41633b29ad613bb1648d75c7e58902cda57e2f2009ce06d8dbbe338d1abb4`。官網「EXTENSIVE SPORTS CONTENT」原文：

> We combine the data from our own editorial team with more than 100 official data sources. This data is merged, processed, enriched and made usable for our customers.

這是產品整體的混合資料來源聲明，沒有指明 NDR、德甲 2026/27、特定賽事、90 分鐘賽果或逐場上游。頁面的一般編採服務說明，亦不能證明特定 NDR feed 的比分由自家記者獨立採集。NDR 原件中的 heimspiel 技術識別、一般客戶標誌、網址或追蹤 ID，不能自行補足這個關係。結論維持 `upstream_relationship=UNKNOWN`，不能從沒有找到關係推定獨立，亦不能由這段聲明認定特定兩個 feed 共用上游。

凍結來源政策 `ops/policies/result_sources_v1.json` 仍只把 [NDR imprint](https://www.ndr.de/service/impressum) 列作一般新聞供應 credit 線索；本輪沒有新增特定結果 feed 的採集證明或開放原件再發布授權。該政策的 SHA256 保持 `33abd884142cc8000844d82cf9886446e4fe27a823f95577d06e4f8d232c6463`。可讀取網頁與可公開再用原件的權利仍須分別核對。

本輪只做四次有界官方文件請求，沒有新增體育 API 或比賽詳細頁 GET。`https://www.heimspiel.de/` 的 301 指向上述 canonical URL，轉址沒有自動跟隨，而是以另一個有界請求讀取。OpenLigaDB 的兩條候選文件路徑 `https://api.openligadb.de/swagger/index.html`（02:32:51.505194Z）及 `https://api.openligadb.de/openapi/v1.json`（02:33:44.909131Z）均回覆 404。因此本文不把先前的 OpenAPI／Samples README 線索當成本輪已重驗的官方文件，也不聲稱已核實編輯期限。請求 metadata 及成功原件在本次工作區 `/tmp/feed-evidence-20261021/`；沒有將整個第三方頁面重新發布到儲存庫。

## OpenLiga 原件：明確的 provider 自報期間，仍非獨立賽果

本輪本地有界檢視 main `8b1ecb4f1345818fe0d0afc5c0288fe43d31ed79` 既有永久原件 `openliga_capture_provenance/2026/10/21/39531429507-1/openliga-capture.tar.gz`，沒有再呼叫體育 API。tar SHA256 為 `2a31bfe56b7453358fa2b7021c83c9bae4bf04a488a0a0cb86611691879f0f18`，其中原始 `openligadb.json` SHA256 為 `280f2e8d7383fda61167224bfe2a9098f71f6f01a9984313cc0611560b7a01c3`。

原件有 306 行，54 行自報 `matchIsFinished=true`；這 54 行各有一項 `resultTypeID=2`，其 `resultTypeKind` 均為 `After90Minutes`。這可具體記錄為 **provider 聲稱的結果期間**，不能單靠字串、type ID 或 `matchIsFinished` 布林值認證完場真偽、實際比分或獨立採集。這次本地結構檢視亦不冒充新一次密碼學驗章；後續使用仍須按既有規則執行當次真正的 CLI 重驗。

原件提供 `matchDateTime`、`matchDateTimeUTC`、`timeZoneID`、`lastUpdateDateTime` 等欄位，但本輪未取得可獨立核實的實際開波或逐場採集者／上游審計證據。不能將預定時間或最後更新時間改名成 actual kickoff。既有 ODbL 資料重用調查及其範圍另見 [OpenLiga 受控擷取文件](OPENLIGA_CONTROLLED_CAPTURE_2026_10_20.md)；資料授權不等於 feed 上游獨立性。

## 本輪工程：固定預算內的 UTC 日輪換

既有 collector 每次只取列表首三項，令穩定列表其餘固定賽事長期沒有詳細頁原件。本輪的唯一工程目標是改成可從簽封原始列表重播的確定性輪換：

- 先驗證完整 cohort，按數值固定賽事 ID 排序；不用比分、模型選向、勝負或文章排名決定次序。
- 只用 collector 實際記錄的 UTC 擷取日與已記錄請求上限。對 `n > 0`，起點為 `(UTC 日序數 × request_limit) % n`，循環選取 `min(request_limit, n)` 個唯一固定 ID；每次最多三個 detail GET。空 cohort 不作請求。
- 新版 completion report／manifest 保存選取政策及可重算 metadata；原件 replay 必須重算選取次序、cohort 與所選 ID，拒絕被改動的選取聲稱。舊版原件仍按其原有首三項政策重播，不補寫輪換或新身份。
- 同一 UTC 日、相同 cohort 及上限的重試選同一批。只有 **cohort 與上限維持相同，且每個連續 UTC 日都有完成的採集執行** 時，才可保證在 `ceil(n / request_limit)` 日內排程嘗試所有 ID。例如穩定七項、每天三項，需要三個連續 UTC 日；這不是已觀察七場或已認證七個賽果。

這個規則不保證缺席日、cohort 改變、請求失敗或同日重跑下的完整觀察覆蓋，亦不是跨執行持久公平佇列。UTC 擷取日不能當作原站發布時間或實際開波。驗收須包括少於三項、limit 1／2／3、跨日／跨年、數值排序、同日重試、選取 metadata／原始列表被改動、失敗後仍守三次請求上限及舊原件相容的正反例。

## 首場完整認證鏈仍欠的原件

需要能涵蓋特定 feed、賽季、期間及用途的上游／獨立採集證據；可追溯的跨來源固定 fixture／team mapping；實際開波與 regulation FT 原始證據；以及原封存賽前預測的完整連結。網頁名字、URL、雜湊、一般 credit、技術 ID、明文完場或 provider 自報期間，都不能代替這些條件。

輪換增加的是有界原件取樣機會。`independently_verified`、scoring／promotion 資格維持 false，`production_recommendations=DISABLED`／HOLD 不變。原有最低 300 場、12 個合資格星期、四聯賽各 40 場與校準／市場優勢／不確定性門檻不變；沒有新樣本外優勢證據，也沒有可承諾的正式推薦日期。

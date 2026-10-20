# OpenLigaDB 受控原件擷取與獨立簽封（#285／#274）

本輪只補原始 API bytes、逐次擷取時間及永久簽封重驗鏈。這不是賽果認證，亦不是正式推薦資格。舊 v1 manifest 不會補寫時間、來源身份或新簽章。

## 原站授權調查

2026-10-20T11:30:42.151397Z 讀取 [OpenLigaDB 官方首頁](https://www.openligadb.de/)，HTTP 200，原件 SHA256 `e92823978fa203f34d0be24ffda65767b7a281c03f15f4abed23f1dee847180a`。原文明確寫：

> Die über diese API bereitgestellten Daten stehen unter der Open Database License (ODbL).

首頁直接連到 [ODbL 1.0](https://opendatacommons.org/licenses/odbl/1-0/)。該授權頁於 2026-10-20T11:31:12.196238Z 成功讀取，原件 SHA256 `85bc21fb2c00b2effb9202b2aa785934ce5a05df954e17cbd2a1f7c10c04c633`。第 3.1(d/e) 項涵蓋永久複製及公開分發；第 4.2 項要求保留授權 URI／原有通知，第 4.4／4.6 項的相同方式分享及機讀衍生資料條件仍適用。第 2.4 項不涵蓋個別內容的其他權利。兩個 `/lizenz`、`/nutzungsbedingungen` URL 當次只回傳 Blazor shell，沒有實際條款正文，內容維持 UNKNOWN。

本功能保存未改動的事實性 API JSON，附原始 endpoint、OpenLigaDB／community contributors 署名及 ODbL 1.0 URI。資料授權與程式授權分開；不下載或重新發布連結內的圖片／標誌二進位。每份 tar 的 NOTICE 與原件一起簽封，不加額外重用限制。

## 具體輸入與輸出

1. 原有兩個固定免費 GET 次數不變。v2 manifest 記錄每次請求開始／完成 UTC、固定原站 URL、HTTP 200、最終 URL、拒絕 redirect、媒體類型、原件大小及 SHA256；失敗保留有限安全錯誤碼。不得以執行時間更新舊來源時間。
2. `python -m ops.openliga_capture_pack --raw <本輪原件目錄> --output <新目錄>/openliga-capture.tar`：重播 v2 transport receipts，將原始 `manifest.json`、原始 `openligadb.json`、可重建 `capture.json`、ODbL `NOTICE.txt` 四項封成唯一 canonical tar。manifest 內第二來源只屬我方 transport metadata；OpenFootball 原始 JSON 不在簽封範圍，scope 嚴格為 `OPENLIGADB_ONLY`。
3. GitHub main 原生工作另簽 `openliga-capture.tar`，使用獨立 `capture.sigstore.json`；NDR 簽章不能延伸至 OpenLiga。驗證器每次呼叫真實 `gh attestation verify`，核對 repository、workflow、main、source SHA、workflow SHA、run／attempt、subject SHA 及透明日誌時間，完成後重新讀取原件，按已驗日誌時間重播全部 receipts。
4. 簽章重驗成功後，獨立 archive job 才可寫入 `openliga_capture_provenance/YYYY/MM/DD/<run>-<attempt>/`。只准兩份原件 gzip；既有相同內容為 no-op，任何不完整／不同內容都拒絕，不覆寫歷史。Git push 只用一般快轉及有限重試。
5. 同輪 fixed-ID replay 的原始 SHA 必須與 tar 裏 OpenLiga 原件一致。固定同 provider ID 仍只表示 `SAME_PROVIDER_FIXED_ID_UNAUTHENTICATED_LINK`。

## 未完成的認證與正式資格

簽封可核對受控擷取工作聲稱捕獲的 bytes、metadata 及其早於已驗透明日誌的時序；不證明出版社本身、資料原始發布時間、逐場採集上游獨立性、跨源 fixture／team mapping、實際開波或 90 分鐘賽果。社群輸入機制不代表 OpenLigaDB 與 NDR／其他網站獨立。來源政策未獲新原件支持的項目全部 UNKNOWN，不修改凍結的 `result_sources_v1.json`。

`production_recommendations=DISABLED`、HOLD 及所有 scoring／promotion／獨立賽果資格維持 false。下一個真正資格里程碑是首場完整固定身份、實際開波、獨立 90 分鐘賽果及原始前瞻封存的證據鏈；之後才有已認證同場 A／B／C／市場 cohort 可做校準與市場比較。

現行最低 300 場、12 個合資格星期、4 聯賽各 40 場及市場優勢／不確定性門檻不變。未認證記錄跨過的曆週不能冒充已合資格星期；數量足夠亦不自動放行。首次合資格星期、實際累積速度及模型是否勝過市場未確定，因此不能承諾正式推薦日期。

測試、CI、真實簽封與永久讀回結果以本輪 PR／Actions 驗收記錄為準；這份設計文件本身不是成功執行證明。

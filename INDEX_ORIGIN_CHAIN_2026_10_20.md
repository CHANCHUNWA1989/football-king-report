# 原站列表擷取鏈 v2｜2026-10-20

關聯 #274。本次只修補列表請求的原站擷取及可重驗 metadata，不改模型、來源獨立性政策、歷史預測／賽果／ledger 或正式門檻。

## 實際問題與修補

舊 external collector 使用會自動跟隨轉址的 `urlopen`，沒有最終網址、逐次請求／完成時間，亦可能覆寫既有原件。因此 URL／hash／簽章只能證明受控工作留下那些 bytes，不能補出缺失的請求鏈。

新版只對固定 DFB、NDR 網址各嘗試一次 GET，拒絕所有轉址（包括同站轉址）。只有精確最終網址、整數 HTTP 200、HTML/XHTML 及最多3MB的回應才保存；`timeout=15` 是 socket timeout，不保證整次請求15秒完成。注入測試 getter 的回傳亦重新驗證，不能跳過大小、媒體及網址限制。

來源錯誤逐項降級；保存固定安全錯誤碼、有限錯誤類別及可核對 HTTP 狀態，不保存任意 exception 訊息／header／私密網址。輸出必須為全新空目錄，獨佔寫入，拒絕符號連結與覆寫；時鐘倒退會拒絕產生不實時序。

## 新收據與原件重播

`football-king-external-raw-evidence-v2` 保留 batch 起點及固定次序 DFB、NDR 的收據。每項包含 requested/completed UTC、DENY_ALL、來源與 final URL；成功時另有 raw檔名／hash／大小／HTTP／媒體，失敗時 final URL 為 null、沒有成功 payload 欄。

`index_origin_metadata.py` 對 schema、完整欄位、固定來源次序、網址、嚴格類型及時間作白名單驗證。來源請求及完成必須依序串連，最後完成不遲於 detail report 起點，再受本次已驗證 Rekor 時間約束。不能靠多加欄位或自報認證旗號補出可信狀態。

observer、capture pack、fresh CLI provenance audit 及逐場來源審計一起支援 v2。只有當次真正驗章成功、tar/bundle digest綁定及原始 NDR bytes 重播通過，逐場審計才列 `CONTROLLED_ENDPOINT_CAPTURE_REPLAYED`。

範圍固定為 **NDR_INDEX_ONLY**。DFB只有 metadata 留在原件 tar，DFB raw不在該subject，不能連帶認證其 bytes、出版社或賽果。來源政策、出版社真偽、實際開波、跨源身份、上游獨立及90分鐘賽果認證仍分開檢查。

| 輸入 | 受控收據狀態 | 賽果評分／正式推薦 |
| --- | --- | --- |
| 新v2精確原件及完整NDR成功收據 | 原件驗章／重播後可完整 | false／HOLD |
| 新v2 NDR抓取失敗 | 失敗收據可重播、鏈不完整、零觀察 | false／HOLD |
| 舊v1原件 | 可重播，origin incomplete、時間欄null | false／HOLD |
| 錯網址／轉址政策／時序／型別／簽章／bytes | 拒絕或安全失敗 | false／HOLD |

舊v1原始 tar、report、metadata 一律不補寫。舊原件重新驗證仍輸出 incomplete／null；將v2欄位塞入v1亦會拒絕，不能事後升格已封存資料。

## 執行及驗收

既有每日工作自動使用新 collector，HTTP來源數量維持2、detail最多3，沒有增加免費API配額或購買服務。舊直接執行 observer 與 `python -m` 兩種CLI皆可；新增 subprocess `-E` 測試先重現無 repository PYTHONPATH 時的匯入失敗，再修正。

完整 ops 1,493項及編譯通過；新增17項collector及27項原站收據／原件重播測試。新測試先重現舊缺陷，涵蓋實際 urllib 轉址拒絕、偽最終網址／媒體／大小／時間／來源次序、錯誤回應、舊v1不升格，以及完整 collector→observer→pack→audit 流程。既有簽章正反例及永久封存防護繼續生效。本地 crypto boundary 替身不作真正密碼學證據，仍須合併後原生 main 驗章／篡改拒絕／原件讀回驗收。

## 尚未完成

原站受控收據完整不等於獨立賽果認證。publisher identity仍未獨立認證；上游關係及實際開波仍UNKNOWN，90分鐘賽果仍UNVERIFIED，跨來源固定身份及賽前封存連結未完成。#274維持OPEN，之後仍須足夠同場前瞻樣本、校準、相對市場優勢及實價風控。

首3場仍未輪換；本次不改取樣規則。正式推薦 `HOLD／DISABLED`，沒有增加合資格樣本，未證實提高命中率或盈利。

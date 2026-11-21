# 第五關｜首場前瞻原件 SHA-256 綁定與驗收交接

日期：2026-11-21（香港時間）｜研究專用｜**HOLD / DISABLED**

## 現有來源實際狀態

- Draft [PR #463](https://github.com/CHANCHUNWA1989/football-king-report/pull/463) 可以對**指定收據 bytes** 透過 RFC3161/可信 CA 進行獨立 OpenSSL 加密學核對。其成功結果仍標示 `independently_timestamped=false`，需要額外 TSA 信任政策、來源及獨立審查，**不是正式資格**。最重要：驗證一張時間戳收據，並不自動證明收據裏面寫嘅模型同盤口原件存在。
- Draft [PR #464](https://github.com/CHANCHUNWA1989/football-king-report/pull/464) 只已有 TheSportsDB 加密原始 FT 候選，公開收據／兩場公開比分對照仍然係**候選資料一致性**。原始明文需要密匙持有人喺私人環境審查；第二個真正獨立來源、官方實際 KO、賽前模型 bytes 鏈仍未完成。正式認證 **0**。
- Draft [PR #501](https://github.com/CHANCHUNWA1989/football-king-report/pull/501) 修正亞洲盤/大小球數學 EV，Draft [PR #502](https://github.com/CHANCHUNWA1989/football-king-report/pull/502) 隔離前瞻重複樣本；均不得因 CI 成功升格為投注訊號。

## 今次新增：只讀 SHA 綁定預檢

`ops/first_case_payload_binding.py` 在離線/私人執行環境，讀取 **同一場** 三份原始檔：

1. `forecast.json`：受限 schema `football-king-first-case-forecast-v1`；包含內部 `fixture_id`、聯賽、主客隊鍵、開球時間、預測捕獲時間、模型版號、完整 1X2 三項機率。此為**研究檔案聲稱**，唔係可信簽封認證。
2. `quote.json`：受限 schema `football-king-first-case-quote-v1`；包括相同內部賽事標識、時間、供應商原生 event ID 字串、賠率來源、市場、方向、盤口、所觀察時間、捕獲時間、價格；不核實可成交。
3. `manifest.json`：受限 schema `football-king-first-case-manifest-v1`；包括同一 `fixture_id` 和開球時間、**對 forecast/quote 兩份原始 bytes 各自計算嘅 SHA-256**、清單建立時間、`status=HOLD`、`production_recommendations=DISABLED`。

工具會拒絕：更改一個字節、JSON 重複欄位／非有限數字、換另一場或主客鍵、盤口方向衝突、只得賽後預測、開賽不足10分鐘先補入、觀察盤口超過120秒後才捕獲，以及破壞 SHA-256 綁定。報告不輸出原始價格或模型機率。

使用指令（實際執行時需有合法、授權、**真正開賽前保存**的三個檔案）：

```bash
python ops/first_case_payload_binding.py \
  --forecast /private/forecast.json \
  --quote /private/quote.json \
  --manifest /private/manifest.json
```

成功只係 `byte_digest_binding_checked=true`，狀態**仍為 HOLD**，`certified_forward_case_count=0`；因為三個檔案可以被事後一齊重寫，單憑 SHA 同自稱時間，**不能證明真正在賽前存在**。

## 實際上線前安全交接（仍屬未完成的獨立工作）

1. 在獲授權的私人環境直接從可信賽前供應商捕獲源原始 bytes（不得回填舊比賽或使用模擬資料）；原始來源 ID、開賽、數據取得日期及完整來源鏈須保留。
2. 由受信任獨立 TSA 對**清單原始 bytes** 取得 RFC3161 token；用 PR #463 OpenSSL `ts -verify` + CA 鏈核對 token 嘅資料摘要必須正正對應同一個 `manifest.json`，並且 token 時間必須早過官方確認嘅開賽時間。實際 CA/TSA 信任政策仍需要獨立覆核。
3. 賽後另由兩個真正上游獨立來源取得**正規90分鐘 FT 精確比分**及原生事件 ID，先以 PR #464 私人原件 replay 檢查來源記錄／加密、再核對跨來源真實身分、比分與官方實際 KO。不得使用只靠名稱／日期嘅近似 match。
4. 建立「清單 hash → TSA token → 賽前原件 hash → 兩來源 FT 原件」審查材料。若其中任何一節缺失，結果保持 `HOLD`，不得增加 certified 樣本、宣稱新模型準確率、正EV、實際ROI。
5. 經獨立 reviewer 再對時間洩漏、重複 fixture、原始 A/B/C + 市場對比、期間與聯賽覆蓋及可成交報價核對。所有 Draft PR 維持未合併；正式投注功能繼續 `DISABLED`。

**限制：** 此次 PR 只建立第一段可重播原件一致性檢查，沒有真實來源憑證、沒有已執行過 TSA 驗證、沒有認證第一場、沒有樣本外回測結果。


## 第六關：RFC3161 同一份原件綁定（新增研究版）

新增 `ops/first_case_rfc3161_link.py` 會先重新檢查原始 `forecast.json`、`quote.json`、`manifest.json` bytes 與時間先後；**只有三者在內容層一致**，才會離線調用 OpenSSL：

```bash
openssl ts -verify -in stamp.tsr \
  -digest "$(sha256sum manifest.json | cut -d ' ' -f1)" \
  -CAfile reviewed-tsa-ca.pem
```

上面係公式展示；實際 Python 會在**記憶體直接計算先前檢查過嘅 manifest 原始 bytes** SHA-256，將 digest 用 `-digest` 參數傳入 OpenSSL，故 OpenSSL **不會再次從可能被調包嘅 manifest 檔案路徑讀取另一份內容**。之後以同一 token 嘅 `openssl ts -reply -text` 解析簽署時間，要求時間 >= 清單聲稱建立時間且不晚於開賽前10分鐘（現階段採取保守閘門）。

實際使用（有**真正合法授權、獨立簽發** TSA token 與獨立審查嘅 CA 鏈後）：

```bash
python ops/first_case_rfc3161_link.py \
  --forecast /private/forecast.json \
  --quote /private/quote.json \
  --manifest /private/manifest.json \
  --token /private/stamp.tsr \
  --ca /private/reviewed-tsa-ca.pem
```

`local_openssl_signature_and_imprint_checked=true` 僅表示本機 OpenSSL 對**指定、由操作者供應嘅 CA**成功核對該 token 同清單 digest。它**不驗證 CA/TSA 信任政策、來源捕獲環境、來源身份、原始預測是否真正在 token 之前發生、兩來源賽果獨立性**，因此結果即使成功亦一律 `status=HOLD`、`certified_forward_case_count=0`、`production_recommendations=DISABLED`。測試全部係無網絡 mock，**並無真實 TSA token**。

同一份原件必須同時經 #506 SHA 綁定及 RFC3161 check；獨立 PR #463 的 TSA 政策審查、#464 原始 FT 私人 replay 及第二獨立賽果來源仍係未完成入門條件。切勿合併或用測試結果代表第一次真正認證。


**來源檔案防調包強化：** TSA token 同操作者提供嘅 CA PEM 會先讀成受限大小嘅 bytes，放入私有臨時目錄（只供兩次 OpenSSL 調用）；所有呼叫都使用同一份 token，呼叫後再核對臨時 bytes 未改動，並立即清除。呢一步只提升本機驗證一致性，唔取代 TSA 機構資格/信任政策覆核，亦唔保證來源主機未被其他有權限程序入侵。無真實 TSA token 時，所有測試成功都只是合成測試。

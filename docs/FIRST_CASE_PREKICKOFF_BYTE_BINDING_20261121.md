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


## 第八關：真正賽前封存入口及報價最終有效期

新增 `ops/first_case_live_manifest.py`。**只適用於使用者獲授權、已經在私人環境取得原始模型及原始報價檔案的情況**，唔會呼叫公開 sportsbook API 或創造機率和賠率。程式直接從執行環境目前 UTC 產生 `manifest.created_utc`，不可透過 CLI 輸入舊時間。這份時間仍然只係本地 runner 時鐘聲稱，須獨立 TSA 認證。

使用方法（於有真實來源檔案、受控私人工作目錄的終端執行；**不要將原始賠率上傳公開 GitHub repo**）：

```bash
python ops/first_case_live_manifest.py \
  --forecast /private/forecast.json \
  --quote /private/quote.json \
  --manifest-output /private/manifest.json

# 當同一份 manifest 已建立，程式絕不覆寫；必須再向獨立 TSA
# 取得覆蓋 exact manifest bytes 的 RFC3161 token，然後執行：
python ops/first_case_rfc3161_link.py \
  --forecast /private/forecast.json \
  --quote /private/quote.json \
  --manifest /private/manifest.json \
  --token /private/stamp.tsr \
  --ca /private/reviewed-tsa-ca.pem
```

### 新增兩道時間閘門

- `first_case_payload_binding.audit` 會拒絕報價在**最終清單 `created_utc`** 當刻已超過120秒的情況。之前只檢查來源報價到初次複製的 age，可能將超過一小時前的報價錯誤視為新鮮。完整校驗還要求盤口時間、模型時間、清單時間順序合理，且至少早於記錄開賽10分鐘。
- 即時產生器 `first_case_live_manifest.build` 會用目前 UTC 重新檢查報價觀測、報價擷取、模型擷取均不可晚於當前時間、目前距原始報價觀測不超過120秒、模型不超過120秒、當前時間早於記錄開賽至少10分鐘。**資料本身的來源時間只是聲稱，非來源認證。**

程式只建立 mode `0600` 的私人 `manifest.json`（create-only、不可覆寫或使用符號連結），不更改兩份原始輸入；只在控制台輸出雜湊、狀態及 blocker，不輸出盤口水位或預測機率。測試包括「初次擷取時有效，但直到封存時已過期」的反例。冇賽前原始模型及當時盤口、冇第三方 TSA 收據，就不能真正執行認證，**正式認證仍為 0，下注／推薦 DISABLED**。

### 現有倉庫的真實來源概況（不可混淆）

在 **main** 讀取到的 `market/private_summary_latest.json` 標明 `captured_utc=2026-11-20T17:58:01Z`（香港時間 2026-11-21 01:58），稱研究盤口觀測數為 **750**（EPL、h2h、僅匿名統計），`VERIFIED_VALUE=0`、`quotes_are_executable=false`。這份檔案並不含單場原始可成交報價，不能作為本工具的 `quote.json`。另外，`evidence/settled.json` 的 `checked_utc=2026-11-21T02:56:04Z`（香港時間10:56），列出 **105** 條仍未獨立核證的研究結算個案，`results_independently_verified=false`。兩個數字都唔係獲認證下注或獨立認證的前瞻樣本。**certified=0**。

**運行前仍需解決：** 將既有 `private-all-market-research.yml` 私人來源原始資料封存與真正賽前模型原始檔以**同一場的原生供應商事件ID**逐個對應；取得獨立 TSA token 並覆核 CA 信任政策；開賽後再由兩個真正上游獨立的原生來源覆核 90分鐘 FT。此 Draft PR 未整合所有動態資料源、未將公開研究候選升格。


## 第九關：私人 h2h 原始回應綁定同一場原始賽前模型（新增）

現有私人 `private-all-market-research.yml` / `private_response_capture` 可以保存 The Odds API 真正由收集程式讀取到的 response body 原始 bytes、endpoint 及完成時間收據、private pack SHA-256。**但來源原始回應本身未獲上游獨立認證**，而且目前私人免費來源只讀 `h2h`，不能假稱實際採集到 `spreads` 或 `totals`。主分支匿名研究摘要亦不包含單場可成交盤口。

新增 `ops/first_case_private_quote_link.py`：於**已存在、授權、mode 0700 的私人目錄**，把已存的 `forecast.json` 原件連同 `private_response_capture.replay_records` 重播出嚟嘅**同一份 SHA 固定私人 pack**做無網絡配對，然後只新建 `quote.json` 和 `manifest.json`；不修改原件、禁止覆寫、檔案 mode 0600、控制台不記錄原始賠率／單場莊家或賽事識別。

嚴格只認原始 event ID == `forecast.fixture_id`、原始 home/away 字串 == 模型對應 home/away、原始 KO == 模型記錄 KO、聯賽 The Odds API `sport_key` == 模型聯賽。所有額外輸入必須明確；不得以同名球隊、聯賽、時間接近作模糊配對。同一 pack 內如果同一原生 ID 出現兩次（包括兩個不同 response），**全部拒絕，不能 first-wins**。只接受唯一莊家、唯一 full-time h2h 市場、完備 HOME/DRAW/AWAY 三向回報；拒絕重複方向、懸掛盤口、錯誤時序、非浮點有限賠率等。選中嘅 quote `provider` 字段固定為 `the_odds_api_v4/<bookmaker_key>/<private_pack_sha256>`，所以 forecast 與 quote 一經後續獨立 TSA 保護，就連結到**所聲稱**私人 source pack digest。呢個 digest **不等於信任來源身份或可成交保證**。

完整私人 CLI 例子（所有 path 只作格式示意；實際需真正資料及具授權嘅 private pack）：

```bash
PYTHONPATH=ops python -m ops.first_case_private_quote_link \
  --private-dir /private/capture-pack \
  --forecast /private/first-case/forecast.json \
  --source-sha <actual-40-character-run-source-SHA> \
  --run-id <actual-GitHub-run-id> \
  --attempt <actual-run-attempt> \
  --expected-manifest-sha256 <actual-64-character-private-pack-SHA> \
  --bookmaker-id <exact-raw-bookmaker-key> \
  --selection HOME \
  --quote-output /private/first-case/quote.json \
  --manifest-output /private/first-case/manifest.json
```

如未知原始來源 pack SHA／repo SHA／attempt、指定 bookmaker 或賽前模型內部 `fixture_id` 不是同一來源原生事件 ID，程式會嚴格拒絕，**不得虛構或靠姓名作替代**。所有檔案驗證通過只代表結構上可以配對，`certified_forward_case_count=0`、`production_recommendations=DISABLED`。

取得上述原始檔後，仍要經獨立 TSA 對這份 `manifest.json` 原始 bytes 發 RFC3161 token，受信任 CA/TSA 政策審查，並完成賽後兩個真正上游獨立來源的 90分鐘 FT 精確結果核實、模型來源簽封及成績配對樣本外統計。**不允許直接從 source pin 或 GitHub CI success 升格為正EV／已認證下注。**


## 第十關：由私人原始 pack 至 RFC3161 token 一條鏈重新驗證

新增 `ops/first_case_private_e2e_audit.py`，**只讀，不重新從供應商請求資料、不改寫任何原件、亦不輸出原始賠率**。指定同一份 `forecast.json`、`quote.json`、`manifest.json`，再提供私有原始 response pack 嘅 context（source SHA／run ID／attempt／原始 SHA pin）及 token、CA 路徑：

```bash
PYTHONPATH=ops python -m ops.first_case_private_e2e_audit \
  --private-dir /private/original-capture-pack \
  --forecast /private/first-case/forecast.json \
  --quote /private/first-case/quote.json \
  --manifest /private/first-case/manifest.json \
  --source-sha <actual-source-commit-SHA40> \
  --run-id <actual-run-ID> \
  --attempt <actual-run-attempt> \
  --expected-manifest-sha256 <actual-private-pack-SHA256> \
  --token /private/first-case/manifest.tsr \
  --ca /private/independently-reviewed-tsa-ca.pem
```

驗證順序：
1. 透過 `private_response_capture._open_chain/_read` 確認三份受保護檔案（0700 目錄、0600 正規檔、無符號連結、無公開 Git worktree 路徑）；完整讀取原始 bytes。
2. 嚴格核對 `quote.provider` 指定的私人 pack SHA **必須完全等於**操作者提供嘅 pinned source manifest SHA。使用 `replay_records` 核對 capture pack 全部原件、receipt/context、請求時間及 SHA；不接受匿名市場統計或者使用者手寫「已驗證」欄位。
3. 由**同一份 raw provider bytes**、同一原生 fixture ID、原始主客隊、原始 KO、莊家及三方 h2h quote，**按已封存 `manifest.created_utc` 當時嘅有效期**重新生成 `quote.json` 及 `manifest.json`。採用歷史封存時間作 replay cutoff，係為咗日後賽事完場後依然可以覆核；絕不可用覆核當刻時間將正確歷史證據判為過期。核對結果必須 byte-for-byte 同已封存嘅兩個檔案相等。
4. 呼叫 `first_case_rfc3161_link.check`，使用 OpenSSL 對**原始 manifest bytes SHA-256**核對 token 簽章、操作者提供的 CA 及時間窗。重新讀取本地檔案並再次 replay 整份來源 pack，攔截核驗期間調包。
5. 即使所有本機檢查通過，一律只回覆 `HOLD`、`certified_forward_case_count=0`、`production_recommendations=DISABLED`。本地 OpenSSL 驗證只證明 **在使用者提供的 CA 信任根下**簽章/內容相符，**不代表獨立 TSA 政策已核實或真實來源可信**。

新增 `ops/tests/test_first_case_private_e2e_audit.py`：使用真實 `CaptureSession` 私有檔案 pack + 無網絡合成賽事及實際 OpenSSL/合成自簽 TSA 完整測試；亦測試修改原件、重新計 hash 的錯價、清單修改、用錯 pack pin、私人檔案權限違規、重播中途換檔、無效時間戳等拒絕案例。測試使用嘅自簽 TSA 根**完全不可信於正式業務**，沒有任何真實來源原件或機構私鑰、亦沒有一場可認證比賽。

**正式未完成：** 來源原生事件同受認證官方 fixture identity 的獨立交叉覆核、實際市場價格可成交性、獨立第三方 TSA policy 與真實 token、兩個上游真正獨立 FT 源、正式 paired OOS 回測。維持 Draft，拒絕將 0 場認證誤算為 1 場。

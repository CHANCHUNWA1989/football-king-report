# KPL 第22階段｜RFC 3161賽前時間戳證據包：完整原始位元組、nonce與賽事身份

日期：2026-11-03。研究型Draft PR，以上游 #407 為基礎；#407本身依賴前置研究Draft分支。**不合併main、不部署、不發送任何外部TSA請求、不申請真實憑證、不啟用投注。**

## 風險背景
KPL V20採本地時鐘及排他創建 JSON 檔案儲存 `manifest`、逐局 `FORECAST` / `HOLD`。V21解決了部分BO7系列賽被選出來報命中率，但本地操作者仍可以事後修改時鐘或檔案，無法證明預測喺開局前已獨立存在。此前V15已提供RFC 3161時間戳Token的本地離線核對，但封存對象係V14簽署預測收據，唔係V20實際的前瞻性trial檔案。

RFC 3161標準：https://www.rfc-editor.org/rfc/rfc3161 。協議要求驗證TSA簽章、簽署者身份、MessageImprint、原始請求nonce、政策與撤銷狀態；**單憑自填時間、SHA256或自稱官方TSA嘅證書唔足夠。**

## 新增研究模組

`research/kpl_v22_shadow_witness.py`：

### prepare_shadow_timestamp_request(...)
- 對V20 `manifest.json` 或某系列賽／局數嘅實際 `decisions/{series_id}-g{n}.json` 檔案讀取完整原始位元組，校驗系列賽、決策、文件名稱、登記版號及截止時間。
- 利用系統OpenSSL `ts -query -data -sha256 -cert` 產生**隨機nonce**、MessageImprint完全對應上述bytes嘅DER格式 `.tsq` 請求；傳回base64請求同資料SHA256。
- **不發送任何請求**。操作方需經獨立渠道傳送 `.tsq` 畀其有合同、信任根及使用權嘅TSA，保存原始請求同TSA返回 `.tst` Token；本repo唔含任何正式TSA密鑰或私鑰。

### audit_shadow_timestamp_bundle(...)
- 同一試驗需覆蓋**1份manifest + 所有已記錄逐局FORECAST/HOLD檔案**，不准欠任何一份或重複／跨系列重用。
- 強制嚴格格式：接收original `request_b64`、`token_b64`，不接受自稱 `verified=True` 或收據內自帶可信CA。
- 每份 `manifest` 或逐局檔案**單次有界讀入**並檢查安全名稱/身份，拒絕symlink、冒名紀錄，以及刪除G2後仍保留G3/G4的非連續局數（防止連檔案同收據一齊刪走後錯誤判定剩餘資料為完整）。
- 證書信任設定經既有V15 `_pin_trust` 以Root和TSA證書DER SHA256指紋固定；確保外部配置公鑰而非從收據中採納。
- 用V15 `_verify_token` 驗證TSA signer必須符合釘住嘅葉證書，以及RFC3161訊息印記與**當前原始檔案bytes**一樣、證書鏈與 `genTime` 簽章有效。
- 用第二次OpenSSL `ts -verify -queryfile original.tsq -token_in`，確保**原始隨機nonce**及原始請求摘要同簽署Token完全吻合，防止同一份資料另外生成的請求被重播來冒充當初那次TSA請求。
- 嚴格要求TSA已簽署嘅genTime：對manifest為登記時間至最早系列賽首局開賽前；對每份決策為當地保存時間至當局開賽前（G1還要受當初登記嘅首局時間約束）。
- 欠CRL/撤銷歷史就清楚標示 `REVOCATION_EVIDENCE_MISSING_OR_UNVERIFIED`；即使提供CRL，既有V15只驗葉憑證本地CRL，唔代表完整鏈撤銷歷史、OCSP、可信外部權威認證及實際原始TSA收據送達時間已獲獨立審核。
- 一切結果固定 `status=HOLD`、`live_execution_allowed=False`、`production_recommendations=DISABLED`、`independent_tsa_identity_verified=False`、`real_kpl_accuracy_verified=False`。函數可報「針對所提供公鑰／token嘅密碼學一致性」，但**不得報真正TSA可信來源已被證明**。

### 為何保留HOLD？
任何人都可以本地生成測試用CA、TSA證書與Token並自己填入「可信keyring」，令密碼學核對通過；所以數學上驗到一份簽章**不等於**TSA獨立性、真正官方賽果、授權用途、賽前提交／回收、或者模型方向命中率已獲證實。只有受保護配置提供經權威渠道核對嘅真正TSA信任根、有效時間／撤銷憑據、對應原始未來比賽紀錄，先值得進一步獨立審核。

## 21項完全合成安全測試

`ops/tests/test_kpl_v22_shadow_witness.py`：實際在暫存目錄產生合成RSA Root/TSA私鑰、X509測試證書、4局合成BO7 trial (3次FORECAST +1次HOLD)、5份RFC3161原始請求及5枚由OpenSSL簽署嘅真實RFC3161格式合成Token；私鑰與證書**僅在GitHub Actions運行時臨時存在，絕不提交GitHub或發送外部服務**。

測試包括刪除中間局數及對應收據、有效OpenSSL印記及nonce仍HOLD、欠manifest／決策收據、跨局Token重播、同一份資料換另一個nonce仍被拒絕、改寫已封存預測概率、改寫manifest、無公鑰／錯指紋、壞base64、冒認verified旗標、超過開局期限嘅Token、無CRL、遺漏決策、檔案符號連結及未知賽事身份拒絕。

```sh
python -m compileall -q research ops
python -m unittest discover -s ops/tests -p 'test_kpl_v22_shadow_witness.py' -v
python -m unittest discover -s ops/tests -q
```

## 未完成嘅真實KPL驗證
本輪**未**實際向任何獨立TSA購買或提交時間戳、冇已授權真實BP/賽果供應者、冇真實賽前影子預測登記、冇真正實戰勝率或市場賠率改善證明；PR繼續Draft。後續須從合規且可確認身份嘅TSA獲得真正見證、保護固定信任根及撤銷鏈，並為整個BO7完整母體提供合法且可獨立核實嘅賽果，先可做真正前瞻性模型驗收。

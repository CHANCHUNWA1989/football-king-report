# KPL 第十四階段｜Ed25519 離線驗簽、公鑰固定及跨賽事重播審計（2026-11-03）

## 功能界線
本輪以 PR #395 為 base、獨立 Draft PR；PR #390–#395 仍屬研究分支。本輪**不取得任何真實KPL比賽BP、官方授權資料或賠率**，不部署簽章服務、不傳輸私鑰、不啟動投注、不修改正式預測模型。

新增 `research/kpl_v14_signed_anchor.py` 與 `ops/tests/test_kpl_v14_signed_anchor.py`。

## 選用加密方案
採用 **Ed25519（RFC8032），公鑰符合RFC8410 Ed25519 SubjectPublicKeyInfo（SPKI）DER**。用宿主作業系統已安裝的 OpenSSL 3 `pkey` / `pkeyutl -verify -rawin` 完成驗證，**不自行實作橢圓曲線**；驗簽程式只使用標準庫包裝 OpenSSL，無網絡呼叫、無 pip 安裝及執行時生成或存儲私鑰。若OpenSSL缺失／出錯，回傳 HOLD / CRYPTO_BACKEND_UNAVAILABLE。

需要具獨立審核權限的部署方提供 `trusted_keys`，例如 `{"witness-key-v1": {"public_key_pem": "...", "spki_sha256": "..."}}`，其中 `spki_sha256` 應由**受信任部署設定或獨立程式碼審查**預先固定。驗證會確認 Ed25519 SPKI DER長度、算法OID與該SHA256，然後用固定公鑰驗證簽章。

**特別注意：** 同一個攻擊者如同時控制收據與公鑰設定，仍可製作一份形式上正確嘅有效簽章。因此收據本身不能提供或覆蓋可信 keyring，也不可將 `signature valid` 等同 `true official KPL witness`。本倉庫無配置任何正式可信見證機構公鑰；單元測試由OpenSSL **即場生成一次性合成測試私鑰於OS temp directory**，從不將私鑰、真實金鑰或secret提交GitHub。

## 簽章訊息契約
以 UTF-8、JSON `sort_keys=True`、無空白分隔符、非ASCII不強制轉義，對以下所有欄位作Ed25519簽章：

`schema=kpl-ed25519-anchor-v1`、`record_index`、`head_hash`、`prediction_id`、`series_id`、`game_number`、`team_ids`、`model_version`、`forecast_at`、`game_start_at`、`anchor_target`、`witnessed_at`、`nonce`。

簽章封包只能含 `payload`, `key_id`, `signature_b64`；不接受內嵌的 `verified=True` 或公鑰。核對頭部 `record_index/head_hash` 與 V13單次讀取驗證後的封存快照，以及系列賽ID、局數、兩隊ID、模型及預測時間。觀測時間必須滿足 `forecast_at <= witnessed_at < game_start_at`。不同系列／對局即使隊名相同亦不能重播同一收據；批量模式會檢查每局覆蓋、重複局數及 nonce重用。

`build_unsigned_anchor_payload` 只構造待簽JSON，**唔簽名或提交任何資料**。
`verify_signed_anchor_receipt` 僅回報 `pinned_signature_verified`、`archive_binding_verified` 等技術指標，`audit_signed_anchor_batch` 會確保每個封存紀錄各有受固定公鑰驗證的簽章及互不相同nonce。

## 不可誇大為可信時間證明
真正可證明的，只係「此數學簽章可由參數提供的固定公鑰驗證，內容對應現存本地封存快照」。以下並**未**被獨立驗證：

- 公鑰是否來自真正、獨立的見證機構（仍須外部授權、信任根、註冊及密鑰輪替政策）；
- `witnessed_at` 是否準確／不可回填（Ed25519只簽署聲稱的時間；不等於RFC3161 TSA時間證明）；
- 收據是否真正喺賽前由外部方見證／保存；
- KPL資料取得、商業用途或再發佈權利；
- 真實比賽賽果、正EV、校準或勝率提升。

**所有 API 永遠回傳 `status=HOLD`, `production_recommendations=DISABLED`, `external_timestamp_authenticated=False`, `live_execution_allowed=False`；測試用 keyring 不能令正式系統放行。**

## 安全測試
19項完全合成測試，包括：有效Ed25519/SPKI固定驗簽仍HOLD、修改signature、改動系列ID、換局數、換整個封存檔、偽造公鑰pin及key_id、沒有keyring、惡意verified=True、賽後見證時間、壞Base64、OpenSSL不可用、無效公鑰格式、RSA錯誤算法、全檔批量覆蓋、重播nonce、缺收據及跨記錄誤綁。

```sh
python -m compileall -q research ops
python -m unittest discover -s ops/tests -p 'test_kpl_v14_signed_anchor.py' -v
python -m unittest discover -s ops/tests -q
```

### 下一階段前置條件
1. 真正獨立見證機構及明確合同／公開金鑰：用權威渠道釘住其 SPKI SHA256，而唔係信任隨收據到達的公鑰。
2. 有簽章時間憑據與不可回填保存政策，並能由獨立證據核實；要考慮密鑰撤銷、輪替、時鐘偏移及簽章格式版本。
3. 從合法授權來源取得KPL真實BP/逐局賽果，經系列賽身份及時間閘門驗證，再按事前時間切分回測，不能靠本輪synthetic測試宣稱預測提升。
4. 維持全部Draft及正式投注HOLD，待独立審核和相依PR整合。

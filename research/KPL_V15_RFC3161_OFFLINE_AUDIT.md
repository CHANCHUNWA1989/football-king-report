# KPL 第十五階段：RFC 3161 離線時間戳、憑證鏈及撤銷狀態審計（2026-11-03）

## 根據標準與操作文件
- RFC 3161：時間戳 Token 必須核對 messageImprint、簽章者證書、唯一序號／nonce、時間、政策OID、時間戳用途的 critical EKU 與證書撤銷狀態。
  https://www.rfc-editor.org/rfc/rfc3161
- OpenSSL `ts -verify -token_in -data -CAfile -untrusted -attime`：驗證 Token 所蓋印的原始位元組、TSA CMS 簽章、ESS/證書鏈與指定驗證時間。 https://docs.openssl.org/master/man1/openssl-ts/
- OpenSSL `verify -purpose timestampsign -attime -crl_check -CRLfile`：只用本地 CRL 檢查指定時間的TSA葉證書。無有效CRL = 不可宣稱未撤銷。 https://docs.openssl.org/3.6/man1/openssl-verify/

## 本階段實際實作
新研究模組：`research/kpl_v15_rfc3161_offline.py`；合成測試：`ops/tests/test_kpl_v15_rfc3161_offline.py`。

1. 先由V13單次驗證封存快照，再用V14固定公鑰驗證Ed25519收據與系列賽、局數、英雄隊伍ID、預測ID、雜湊及預測時間。
2. 將**整份**已簽署Ed25519收據（包含 payload/key_id/signature_b64）按固定JSON契約編碼，作RFC3161 Token覆蓋嘅資料；只覆蓋payload可能無法證明Ed25519簽章喺TSA時已存在。
3. TSA Root CA 與TSA葉證書必須分別由**獨立信任設定**傳入完整PEM及其DER SHA256指紋；不接受Token或用戶收據自行提供公鑰。具體識別由部署及審核提供，本倉庫完全沒有任何正式KPL或TSA公鑰。
4. 用 `openssl cms -verify -nointern -noverify -certfile <pinned TSA>` 先要求Signer精確匹配固定TSA證書；用 `openssl ts -verify -data <canonical signed envelope> -attime <signed genTime> -CAfile <pinned CA> -untrusted <pinned TSA> -purpose timestampsign` 同時核對印記、Token簽章、TSA特別用途及當時X509憑證有效期；檢查政策OID allowlist 與 SHA256。無OpenSSL或格式錯誤均HOLD。
5. Token內簽署嘅genTime必須早於 `game_start_at`，唔可早於Ed25519收據所聲稱嘅 `witnessed_at`。時間欄位只有完成Token簽章驗證後才有密碼學意義；即使如此，是否獲獨立可信TSA實時發出仍未獲證實。
6. 無 `revocation_crl_pem` 就返回 `REVOCATION_STATUS_UNAVAILABLE`、`revocation_status_locally_checked=False`、`status=HOLD`。若提供CRL，僅在OpenSSL離線 `verify -crl_check` 過關時標記葉證書本地檢查；這唔係全面鏈撤銷／OCSP／可信時間證明。CRL過期、錯誤或顯示撤銷都HOLD。**無任何網絡下載CRL或OCSP。**
7. 回傳 `rfc3161_token_signature_and_imprint_verified` 等技術結果，但 `external_timestamp_fully_trusted=False`、`trust_anchor_independently_authenticated=False`、`production_recommendations=DISABLED`、`live_execution_allowed=False` 始終固定。

## 重要殘餘風險
- 簽章與憑證鏈只能證明使用配置公鑰可驗證，不能證明配置公鑰來自權威見證機構、時間服務真正獨立或具有合法商業資料授權。
- 本版無RFC3161原始請求nonce對照與獨立送達回執；若無可信外部收據、時間源及保存證據，不能聲稱不容事後偽造或重播。
- 只有本地CRL葉證書檢查，未有所有中介憑證的完整撤銷證據、OCSP及密鑰輪替政策；任何缺失繼續HOLD。
- `genTime` 由簽章Token內容得出，憑證有效期以該時間進行離線檢驗；真實採用時還須確認相關TSA信任政策及撤銷時間歷史。
- OpenSSL命令介面及本地測試通過不等於RFC3161第三方一致性或安全審計完成，不能宣稱真實KPL預測效能、已核實勝率或正EV。

## 測試與交付
合成測試由OpenSSL在暫存資料夾生成臨時Ed25519測試金鑰、RSA根／TSA測試證書和真正RFC3161測試Token；**不提交或共享私鑰、憑證、真實BP或受限賽事資料**。包含正向密碼學驗證仍HOLD、錯印記、跨賽事、錯TSA簽署者及固定證書、錯政策、壞Token、缺CRL、錯CRL、時間晚於賽事及過期TSA證書負向測試。

```bash
python -m compileall -q research ops
python -m unittest discover -s ops/tests -p 'test_kpl_v15_rfc3161_offline.py' -v
python -m unittest discover -s ops/tests -q
```

以 PR #396 為基礎獨立 Draft PR 提交；前置 Draft PR #390–#396 須經獨立審查和依賴合併計畫；正式投注永久維持HOLD，無部署或正式功能更改。

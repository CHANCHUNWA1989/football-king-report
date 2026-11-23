# 足球王者 VNext｜第十三關：來源用途／地域／有效期／撤銷範圍檢查（2026-11-23）

## 目的（保留 HOLD）
PR #545 已把未驗證供應商來源／權益聲稱整理成候選資料，但未有逐條比對「用作賽前研究」與「即場分析、AI 訓練、再分發、投注推介」等使用範圍；亦未核對地域、權利持有人、時限和撤銷狀態。*同一個 API 能夠讀取，不代表可以作任何下游用途。*

新增 `ops/inplay_source_use_scope_gate.py`，使用 `audit_scope_claims(dossier, grants, *, requested_use, territory, license_holder, now=None)`。它只做 **offline、資料結構及自稱範圍的一致性驗證**：不是獨立簽署審核、外部授權、legal opinion、可信時間，亦不發起任何網絡連線。

## 演算法與輸入契約
- `dossier`：原 PR #545 `assess_source_readiness` 的原始、未認證 dossier，必須先在同一評估時刻取得 `ready_for_independent_review=true`。**不能用外部傳入的 success/approved 字段替代。**
- `grants`：正好兩個自稱授權範圍紀錄，來源 ID 必須一一對應 dossier 中兩個 provider；權益文件 SHA-256 必須與 dossier 的自稱 digest 相同。
- 每個 grant 僅允許：`provider_claim`、`license_holder_claim`、`rights_record_sha256_unattested`、`covered_uses_claim`、`denied_uses_claim`、`territories_claim`、`valid_from_utc_claim`、`valid_until_utc_claim`、`revocation_status_claim`。
- `requested_use` 必須同時在兩份 grant 的 covered uses 及兩個 dossier 的 requested uses 內，且不能列在任何 denied uses；全部值使用固定枚舉。
- `territory` 要 ISO-like 兩位大寫地域聲稱，例如 `HK`；兩份 grant 都必須包含該聲稱地域。**唔會用裝置 IP 推斷地域，也唔代表所在地法律合規**。
- `license_holder` 必須與兩個 grant 及預檢時的呼叫相同，格式嚴格限制。**未核實真正持有者身份**。
- `valid_from_utc_claim <= now < valid_until_utc_claim <= dossier.rights_expiry_utc_claim`；只接受 UTC 具時區時刻。
- `revocation_status_claim` 只接受 `NO_REVOKE_REPORTED`。**此值由呼叫者填寫，完全不能證明獨立撤銷查詢已完成。** 出現 `REVOKED`、`UNKNOWN` 或其他字串均失敗安全。
- 驗證成功只輸出 `ready_for_external_rights_review=true`，固定 `status=HOLD`、`source_authorized=false`、`source_data_access_enabled=false`、`signed_grant_verified=false`、`revocation_registry_independently_verified=false`、`eligible_for_model_input=false`、`production_recommendations=DISABLED`。其他情況輸出安全 `HOLD`，不洩漏 private metadata。
- 批次結果使用排序及 SHA-256 自記承諾（unattested），**不等於 TSA／Sigstore 也沒有第三方 hash 見證**。

## 真實供應商條款研究（只係供審核清單用，無一間獲批准）
- Football-Data.co.uk 2026-11-20 更新的官方 contact / fair usage 頁：免費 CSV/Excel 用途指向個人投注或學術研究，限制自動下載頻率，特別指出不適合部分 AI training／commercial scraping；另有收費授權途徑。官方： https://football-data.co.uk/contact.php
- StatsBomb Open Data / Hudl 官方 README：公開特定歷史賽事供足球研究，資料使用、發布與署名有其聲明；**唔可以將這視作即場賠率、商業或投注授權**。官方： https://github.com/hudl/open-data/blob/master/README.md
- Sportmonks 官方條款：按服務／訂閱範圍可能供 App 使用，但轉售、地域、資料與網站素材、圖像、期限等需另外審核；**唔可以推定自動取得 betting / model training 權益**。官方： https://www.sportmonks.com/terms-of-service/

## 真正解除外部阻塞之前必需
1. 獨立核實每個供應商及資料權利人、授權範圍、文件原本、權益人及簽名；有權審核員確認用途、地域、時限及備份/轉發政策。
2. 採用獨立可信的授權記錄與撤銷來源，不信任 caller `NO_REVOKE_REPORTED`，建立定期重審／即時停止機制。
3. 由外部真實 provider 回應建立合法 HTTP 收據、provider event ID、可信時間戳及確實可重播的私有封存，建立防 lookahead。
4. 對足球正式採集器／模型輸入完成新版本獨立 code review 和證據驗收；**本 PR 冇任何正式採集開關**。
5. 只有真實賽前樣本外回測、真實盤口 timestamp、穩健估計及 EV 檢查完成，先可以討論模型是否具正 EV；純 CI 通過不等於盈利。

## 研究鏈、CI 和驗收
Stacked Draft：#529→#530→#531→#532→#533→#535→#537→#540→#545→本 PR。未經獨立 review 不 merge；唔改 `main`、既有封存、模型權重、HKJC、正式投注開關。

```bash
python -m unittest discover -s ops/tests -p 'test_inplay_source_use_scope_gate.py' -q
python -m compileall -q ops
python -m unittest discover -s ops/tests -q
```
`ops/tests/test_inplay_source_use_scope_gate.py` 共 **15 項合成正反測試**，不包含真實 provider 合約、機密 token、實際賽果、xG、bookmaker quote 或 EV。
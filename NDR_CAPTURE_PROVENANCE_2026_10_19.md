# NDR 受控擷取證據驗證（2026-10-19）

原本擷取後只有未簽署的 HTML、雜湊及觀察 JSON，不能獨立重驗是甚麼版本的工作流程留下這批位元組。今輪加入受控擷取的原始證據鏈：確定性封裝、GitHub／Sigstore簽署、每次重新驗證及永久封存。

`ops/ndr_capture_pack.py` 只封裝原始 index manifest、可選NDR列表HTML、completion manifest／report及最多3個詳細頁；只准固定名稱普通檔案，拒絕額外成員、連結、重複、非有限JSON、矛盾metadata及超限內容。讀取tar不解壓到輸入路徑。驗證會從原始HTML重新計算列表、固定身份、比分、完場顯示、拒絕及抓取失敗，整份報告都要吻合；來源失敗亦可保留一致的零觀察證據。

每日研究在隔離的簽署job中，沿用已釘選的actions/attest簽署一份`ndr-capture.tar`。另一個唯讀job執行`ops/ndr_capture_provenance.py`：每次真正呼叫`gh attestation verify`，核對repo／owner數字ID、main workflow、來源及workflow SHA、run／attempt、GitHub hosted runner、唯一subject雜湊及可信Rekor見證，再重播全部原始來源。儲存的verification JSON、自報的布林值、來源文字及predicate時間均不能代替新驗證。

簽署job亦實際測試修改位元組及錯誤source SHA必須被拒。通過後，由獨立contents-write job以`ops/archive_ndr_capture_provenance.py`保存原始tar及bundle至`ndr_capture_provenance/YYYY/MM/DD/run-attempt/*.gz`，gzip mtime=0、原子新增、相同重跑不變、有衝突拒絕。原本forecast證據鏈不變；新封存也不改舊預測或賽果。

## 資格界線

這一層只驗證受控工作流程的身份、原始位元組及重播一致性；記錄的抓取時間必須與見證相容，但不等於NDR發布時刻或真實開波時刻已獨立認證。原始index collector亦未認證重新導向後的出版者身份。NDR兩個頁面仍屬同一出版社；出版社上游獨立性、賽果真實性、可成交盤口、校準及模型優勢全部仍要另行驗收。

即使`audit_completed`／`capture_content_replayed`為true，`source_identity_independently_authenticated`、`outcomes_independently_authenticated`、`independently_verified`、`eligible_for_model_scoring`及投注資格仍為false，正式推薦保持HOLD／DISABLED。此票沒有解決全套正式資格驗證器的`TRUSTED_EVIDENCE_VERIFIER_NOT_IMPLEMENTED`，沒有增加合資格賽果，亦未證實改善命中率。

## 重驗

```bash
python -m ops.ndr_capture_pack --index /path/to/external_raw --completion /path/to/ndr_completion --output /tmp/new-proof/ndr-capture.tar
python -m ops.ndr_capture_provenance --proof /path/to/original-proof --source-sha TRUSTED_SOURCE_SHA --workflow-sha TRUSTED_WORKFLOW_SHA --run-id TRUSTED_RUN_ID --attempt TRUSTED_ATTEMPT --output /tmp/ndr-audit.json
python -m compileall -q ops
python -m unittest discover -s ops/tests -q
```

CLI的來源SHA／workflow SHA／run／attempt必須從可信GitHub運行context取得，不可從待驗的payload自行信任。需要支援attestation的gh版本；缺工具、簽章失敗或內容不符即HOLD，不能繞過。首次真實密碼學驗收以主線實際運行為準，本地CLI測試替身只支持政策與程式測試。

本輪本地驗收：45項新增測試、99項相關測試及完整ops 1,405項全部通過；編譯、51個workflow shell步驟語法、原ZIP雜湊亦通過。實際原始3場資料可確定性重播，tar SHA256 `e2c9f0030a4489ffb3e3ef52351ebc350d1bfb9404a12fcd01e2610ee13a0dbd`。獨立覆核亦確認內容偽造、錯誤身份、早於抓取的見證、超限及危險路徑被拒。真正簽章及負例以主線運行記錄為準。

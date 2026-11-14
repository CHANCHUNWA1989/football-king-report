# 足球王者 P0｜持有人離線解密及來源原件重播指南（2026-11-08）

> 這份操作指南係為有權保管 **原本 age PQ 私人金鑰** 嘅獨立覆核者而設；**唔好**將私人金鑰、解密後檔案、API 密鑰、原始 JSON 放入 GitHub 公開儲存庫、Actions Artifacts、聊天或 Issue。測試時新產生嘅 PQ 金鑰 **無法** 解開已封存嘅舊密文。

## 已驗證的兩份歷史加密證據

- GitHub 實驗分支：`fix/sportsdb-single-result-raw-capture-20261108`
- 原件位置：`evidence/encrypted_result_sources/v1/42406458039-1/`
- TheSportsDB `2508371`：多蒙特對雲達不來梅，2026-10-09，API claim 2:2。
- TheSportsDB `2508372`：賀芬咸對漢堡，2026-10-10，API claim 2:3。
- 每場包含 `.age` 密文及 `.receipt.json` 安全指紋收據。**公開收據＋密文核對只證明位元完整，唔認證上游獨立、90分鐘 FT 官方事實、實際開賽或模型準確度**。

## 由授權覆核者喺受控 Linux 電腦執行

1. 先確認使用原本對應固定 `sources/policies/private_original_recipient_v1.txt` 嘅 PQ 私匙。請以離線 `age-keygen -y /private/path/identity.txt` 導出公鑰並與該公開 recipient **本機比較**；請勿輸出私人 identity、亦唔好喺聊天發送。**如果原本私匙不存在，原有密文無法用新 key 復原**。
2. 使用 PR #464 嘅受審查分支程式碼，在個人受控 Linux 環境，依以下命令安裝 hash-pinned 官方 `age v1.3.2` 工具。把 key 放在 repo 以外、只有本人可訪問嘅 `0700` 私人目錄；identity 檔必須 `0600`、無 symlink，唔好喺 CI 共享真實金鑰。

```bash
python -m ops.install_age --destination /secure/owner-only/football-age
python -m ops.sportsdb_public_cipher_audit \
  --directory evidence/encrypted_result_sources/v1/42406458039-1

python -m ops.sportsdb_private_keyholder_replay \
  --directory evidence/encrypted_result_sources/v1/42406458039-1 \
  --event-id 2508371 \
  --identity-file /secure/owner-only/identity.txt \
  --age-binary /secure/owner-only/football-age/age

python -m ops.sportsdb_private_keyholder_replay \
  --directory evidence/encrypted_result_sources/v1/42406458039-1 \
  --event-id 2508372 \
  --identity-file /secure/owner-only/identity.txt \
  --age-binary /secure/owner-only/football-age/age
```

3. 正常輸出只有安全嘅 `raw_sha256`、`decrypted_original_pack_sha256`、來源原生 ID、HOLD 同 `production_recommendations=DISABLED`；解密進程會使用受權限保護嘅臨時 quarantine 檔案，程序完成即刪除；唔會寫入任何永久公開明文檔案，亦唔會輸出私人 key。同一套工具依次核對 public ciphertext/receipt pins、age PQ authentic decryption、原始 pack SHA、原始 provider JSON SHA、固定賽事身份、HTTP 200/URL、時間排序、既有來源 claim。
4. 無對應 identity、不一致或資料被篡改，必須 `HOLD` 並拒絕；唔可以將失敗結果改寫為「已認證」。新增 GitHub CI 只使用 **即場生成隨後刪除嘅合成 PQ 身份** 做完整真加密/解密測試，並**冇**使用歷史真實私匙。

## 未完成的正式認證條件

- 再建立**可合法保存、真正獨立上游**嘅第二條結果原件鏈，非僅兩個網站相同比分。
- 明確驗證 `actualKO` 同正規 90 分鐘 FT，不把賽前排定時間當實際開始時間。
- 原預測前瞻封存、賽事身份與賠率時序審核，簽署信任根、版本化正向 admission 及 append-only certified ledger。
- 直至完成，正式認證數 **0/300**；正式投注 **DISABLED/HOLD**。加密測試、密文完好或解密成功，都唔代表模型有盈利優勢。

此模組只喺授權覆核者嘅環境執行，唔應加入自動排程或 GitHub 公開 CI 真金鑰。PR #464 尚須獨立程式碼覆核，未過關唔合併。

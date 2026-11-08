# 足球王者｜已封存雙來源原件：授權持匙者離線解密驗證

**用途**：針對 2026-11-08 GitHub Actions `42446535384-1` 已保存嘅 OpenLigaDB 及 OpenFootball PQ-age 密文，先做公開 SHA／Git blob 驗證，然後由**實際持有原對應私人身分檔案**嘅授權人士，離線解密並逐位元驗證當日收到嘅原始 HTTP JSON。只係證據保管能力驗收，**唔等於官方賽果、上游獨立性、真實開賽時間或模型命中率認證**。

## 使用條件

1. 從本 repo 對應版本讀取 `evidence/identity_ab_ft_sources/v1/42446535384-1/` 內全部5個檔案；必須保留原檔名／原位元，不能重新編輯 receipt。
2. 授權持匙者自行喺本地 **Linux x86_64** 安全環境保存原對應 `AGE-SECRET-KEY-PQ-1...` 身分檔案。必須放喺只容擁有人存取嘅私人目錄（權限 `0700`），檔案權限 `0600`。切勿將金鑰放進本 repo、PR、GitHub Actions、Issue、聊天室，亦唔好提交到 Library。
3. 使用 repo 既有 `ops.install_age` 安裝**官方 SHA256 釘選** `age v1.3.2`。於權限合適嘅本地資料夾執行以下示範，實際路徑需自行替換：

```bash
python -m ops.install_age --destination "/my-private-tools/football-age-1.3.2"
python -m ops.identity_ab_two_source_public_cipher_audit \
  --directory evidence/identity_ab_ft_sources/v1/42446535384-1
python -m ops.identity_ab_two_source_authorized_replay \
  --directory evidence/identity_ab_ft_sources/v1/42446535384-1 \
  --private-age-identity "/my-private-vault/age-identity.txt" \
  --age-binary "/my-private-tools/football-age-1.3.2/age"
```

工具先檢查首次原始 index Git blob SHA1、5份檔案 SHA256、每個密文分段同收據。驗證通過先讀私人金鑰；年齡解密使用私有 memfd、核對 pin 版本、私有暫存。解密原件只喺程序記憶體中校驗，**唔寫回 GitHub、唔輸出原始賽果或金鑰**。對每個來源執行：壓縮包 SHA、固定 manifest、HTTP 200 固定來源 URL、接收時間、zlib 最大解壓長度、原文長度及原文 SHA256，並校驗基本 JSON 格式。任一來源失敗則整個離線驗證返回 `HOLD` 並以非零代碼退出。

輸出成功只代表 `original_source_bytes_decrypted_and_replayed=true`，`upstream_independence_authenticated=false`、`actual_kickoff_authenticated=false`、`independently_verified_regulation_ft=0`、`certified_scored_cases=0`、`production_recommendations=DISABLED` 必須保持不變。

## GitHub CI 範圍

`ops/tests/test_identity_ab_two_source_authorized_replay.py` 只使用**合成假密文／假 PQ 身分**與替身解密器來驗證真實封裝格式、拒絕錯誤私人檔案權限、任一來源失敗、偽造認證旗標、壓縮炸彈、附加無關資料、JSON 改寫。CI **冇原本對應私人金鑰，亦唔會聲稱已解密真實5份歷史檔案**；佢只會再重驗真實公開密文完整性。需要有權使用私人身分檔案嘅持有人喺獨立本地環境執行上面指令。

> GitHub Contents API create-only + Git 原始 commit / blob pin 並非不可變第三方時間公證。公開密文重播同獨立來源認證係兩回事。未完成官方FT、actual kickoff 及市場校準之前，正式推薦維持 HOLD／DISABLED。

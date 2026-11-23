# 足球王者 VNext｜第廿一關：排除 SSH 第二金鑰來源漏檢（2026-11-23）

## 實際漏檢
Draft PR #563 的 `ops/inplay_openligadb_sshd_policy_audit.py` 只閱讀專用服務帳戶 `~/.ssh/authorized_keys`，但未要求 `sshd -T -C` 真正顯示的 **`AuthorizedKeysFile`** 剛好係該檔案。OpenSSH 可以列出多個授權金鑰檔案，官方文件說常見預設值包含 `.ssh/authorized_keys .ssh/authorized_keys2`；如另有 `/etc/ssh/keys/%u` 或其他後備來源，一個受限的 authorized_keys 只能證明它自身，**不能證明另一檔案不存在未審核公鑰**。以前程式甚至可在 `sshd -T` 未包含 `authorizedkeysfile` 行時返回 `RESEARCH_ONLY`。

官方依據：[OpenSSH sshd_config (Debian)](https://manpages.debian.org/trixie/openssh-server/sshd_config.5.en.html) 對 `AuthorizedKeysFile`、`AuthorizedKeysCommand`、`AuthorizedPrincipalsFile`、`AuthorizedPrincipalsCommand` 的說明。使用者提供的主機設定以及檔案未在此對話出現，因此本輪僅審核合成 sshd 有效設定，沒有在真實主機執行命令。

## 本輪修改
- 強制有效設定 `authorizedkeysfile .ssh/authorized_keys` **精確比對**：包含 `authorized_keys2`、系統後備檔、同一檔重複列出、`none`、`%h`/`%u` 代入路徑、缺值、不同大小寫、額外空格、重複安全指令一律 HOLD。唯一允許的檔案仍需符合 PR #563 的專用 `~/.ssh/authorized_keys` owner/0700 `.ssh`/0600 單連結普通檔案及唯一受限 ed25519 公鑰結構。
- 另要求 `authorizedprincipalsfile none`、`authorizedprincipalscommand none`。連同原本 `authorizedkeyscommand none`、`trustedusercakeys none`，避免未經審核的其它授權來源進入專用帳戶；這些是本項目自訂的**保守 fail-closed 安全條件**，不是指 OpenSSH 有此一律必須的普遍最小配置。
- 更新原本 `test_inplay_openligadb_sshd_policy_audit.py` 的 `effective()` 安全快照樣本，必須明確載有全部授權來源設定；避免測試依賴 OpenSSH 可能依發行版而異的預設值。
- 新增 `ops/tests/test_inplay_openligadb_sshd_single_key_scope.py` **12項全合成測試**：單一檔案正例仍只可 RESEARCH_ONLY；第二個 authorized_keys2、etc 系統後備、錯路徑、缺 directive、重複 directive、principal file/command、CA fallback、forcecommand 不能替代金鑰來源審核，以及不洩漏原始公鑰內容、不可提升部署或投注權限。CI 不讀真實 SSH 金鑰，亦唔運行 sshd 或 API。

## 驗收、限制、下一真實部署關口
```bash
python -m compileall -q ops
python -m unittest discover -s ops/tests -q
```
需要核對 PR 最新 exact HEAD 7項 GitHub CI（Python 3.11/3.12 safety、regression×2、stress、ledger-tests、validate）；必須由獨立 reviewer 完成上游研究鏈審核先可按次序處理合併，不能將本輪直接合併 main。

合成設定符合所有條件時最多只可返回 `RESEARCH_ONLY`。本輪**仍未**驗證 sshd 是否已載入配置、其它使用者或主機授權能否繞過、SSH host-key pin、實際 authorized_keys 檔案身份、跨主機網絡出口防火牆、OpenLigaDB 原始資料真偽、TSA／Rekor 外部見證及第二來源。即使所有限制測試通過：`sshd_running_process_policy_verified=false`、`ssh_authentication_independently_verified=false`、`cross_host_firewall_verified=false`、`ready_for_actual_provider_http=false`、`eligible_for_model_input=false`、`production_recommendations=DISABLED`、`positive_ev_verified=false`、`certified_forward_samples=0`。

下一步真正硬證據仍需由擁有該主機操作權的管理員，在指定 OS 帳戶、固定客戶端 IP 的實際部署機執行唯讀工具，再進行授權／拒絕 SSH 金鑰登入、防 shell/forwarding、deny-by-default egress 的網絡負向測試。當前無此主機證據，**任何聲稱跨主機完成部署都屬不實**。
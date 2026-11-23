# 足球王者 VNext｜第廿關：專用 SSH 帳戶有效設定唯讀驗收器（2026-11-23）

## 已證實的工程缺口
研究 PR #558 同 #561 實作咗有界時限、只接受一筆 JSON 嘅 SSH forced-command stdio 橋接，但該程序收到 `SSH_CONNECTION` 環境變數**不能驗證**用戶到底有冇採用受限金鑰、sshd 密碼 fallback 是否關閉、其他 forwarding 是否開啟，亦無法驗證真實主機防火牆。用戶上一輪要求真實跨主機驗收；目前 repo 無真實主機、sshd 或管理權限提供。因此本輪不虛構主機實測，先做一個**可以在真正主機上唯讀執行**、且 fail-closed 的 SSH 安全設定快照檢查器。

## 實作內容
- `ops/inplay_openligadb_sshd_policy_audit.py`：`inspect_local_host(user, client_ip, server_ip, server_port, authorized_keys_path, expected_command)`，先安全讀取專用 OS 用戶 `~/.ssh/authorized_keys` **公鑰記錄**（絕不讀私鑰）：只允許 root 外專用帳戶、固定 `0700` `.ssh`、單連結正規 `0600` `authorized_keys`、限制檔案大小、防 symlink、核對前後 inode/uid/mode、最多一筆限制公鑰；唔回傳公鑰內容、檔案路徑或錯誤原文。
- 只向固定 `/usr/sbin/sshd` 做**不會修改設定**的 `-T -C 'user=...,host=...,addr=...,laddr=...,lport=...'`，用 `subprocess.run` 直接傳參數（無 shell）、5秒 timeout、限長回應。必須真正喺擬部署的主機，以**對應用戶及實際客戶端IP**生成有效 SSH Match 設定；在別處模擬的 `sshd -T` 快照不算真正主機已完成驗證。
- 對 `sshd -T` 有效設定採保守強制要求：`forcecommand` 完全等於唯一指定 Python stdio bridge 命令；`authenticationmethods publickey`、`passwordauthentication no`、`kbdinteractiveauthentication no`、`pubkeyauthentication yes`、`permitrootlogin no`；`disableforwarding yes`、TCP/streamlocal/agent/X11/PTY/UserRC/UserEnvironment 全部 `no`；hostbased、GSSAPI、Kerberos、empty password 皆禁；`authorizedkeyscommand none`、`trustedusercakeys none`、`maxsessions 1`。缺失、多義或放寬一律 HOLD。實際 sshd 不同版本可能唔支援部分強制欄位，**係審核阻塞，唔係默認通過**。
- authorized_keys 必須只得一條**完整固定格式** `restrict,command="..." ssh-ed25519 <public-key-base64> [comment]`；`command` 必須與已驗證的 expected command 相同，含 `--forced-ssh-stdio` 和絕對 `--private-root`；拒絕相對路徑、Shell metacharacters、添加 `pty`/`agent-forwarding`/`port-forwarding` 等重新啟用選項、無限制公鑰、其他第二把鑰或證書授權。驗證的是 SSH Ed25519 公開 blob 結構，唔係簽署身份或具體鑰匙是否已撤銷。
- **輸出只係安全旗標**：即使有效設定＋公鑰快照完全符合規格，最多 `RESEARCH_ONLY`，`actual_local_host_snapshot_read=true`（只有本機實際檢查時），`sshd_running_process_policy_verified=false`、`ssh_authentication_independently_verified=false`、`client_host_key_pinning_verified=false`、`host_firewall_egress_verified=false`、`cross_host_firewall_verified=false`、`ready_for_actual_provider_http=false`；**絕不可因本檢查器而開啟 live 資料收集或投注**。

## 受控主機手動唯讀操作示意
注意以下路徑、IP、服務帳戶全部係**部署前示例，未證明存在**。操作員必須先用正常 OS 安全程序創建受限專用帳戶／金鑰，配置 sshd 並獨立審查 firewall。此工具不會修改任何設定。
```bash
python ops/inplay_openligadb_sshd_policy_audit.py \
  --user footballresearch \
  --client-ip 192.0.2.10 --server-ip 192.0.2.20 --server-port 22 \
  --authorized-keys /home/footballresearch/.ssh/authorized_keys \
  --expected-command '/usr/bin/python3 /opt/football-king/ops/inplay_openligadb_ssh_stdio_bridge.py --private-root /srv/football-king-private --forced-ssh-stdio' \
  --manual-read-only
```
工具預設 `sshd` 固定 `/usr/sbin/sshd`，並不從 `$PATH` 執行不可信程式，亦不讀取 `.ssh/id_ed25519` 等私鑰。建議在隔離主機操作並保留獨立、可信的驗收記錄，不要將 public key 內容、Private Key 或 host 配置上傳公眾 GitHub。

## 有效設定 ≠ 目前運作策略／跨主機防火牆
- `sshd -T -C` 是**讀取當下設定檔對指定條件的有效值**，並非實際 SSH 登入憑證、已運行 daemon 所採用的設定證明，亦不能涵蓋所有 host/user/IP、其它 `AuthorizedKeysFile` 或 PAM 配置、未審查 SSHCA/AuthorizedKeysCommand、其它 service accounts、或 ACL / 路由繞過。
- 需要獨立驗收：sshd reload 後的行為實測、獲授權／未授權金鑰各自測試、不能以密碼登入或執行任意 shell、無 PTY/forwarding、客戶端 known_hosts 釘住主機鑰匙、不同 host 直接連 OpenLigaDB 被 OS firewall 阻擋、只有中央 Broker 可以出口、資料封存成功及回收。以上都**未在本 PR 執行**。
- 參考 [OpenSSH sshd_config](https://man.openbsd.org/sshd_config)、[OpenSSH authorized_keys](https://manpages.debian.org/trixie/openssh-server/authorized_keys.5.en.html)。本工具收緊嚴格度並非以上手冊強制官方最低設置，而係足球王者研究服務自訂的安全先決條件。

## 驗收
- 新增 `ops/tests/test_inplay_openligadb_sshd_policy_audit.py` 共 **17項 synthetic tests**，覆蓋正例結構（仍非現場認證）、多種密碼／Forwarding fallback、未限制公鑰、重新放行 pty/agent、Shell 命令、重複有效設定、多公鑰/壞 base64、錯路徑、過長、缺實際公鑰檔、模式／symlink、不安全連線條件、模擬只讀 `sshd -T -C` 正例。測試從不真的讀主機 SSH 配置或執行 `/usr/sbin/sshd`，亦不會觸及 HTTP。
```bash
python -m compileall -q ops
python -m unittest discover -s ops/tests -q
```
需核對最新 exact HEAD GitHub 7/7 CI 安全、回歸、壓力及 ledger 綠燈，獨立 code review 後才可按依賴順序考慮合併。疊加研究 PR #529→#530→#531→#532→#533→#535→#537→#538→#542→#543→#546→#548→#552→#555→#558→#561→本 PR，維持 Draft。

## 永久 HOLD
沒有真實伺服器授權、外部 TSA、兩個真實獨立 source、官方紅牌、即場xG、可成交盤口或樣本外前瞻。`production_recommendations=DISABLED`、`eligible_for_model_input=false`、`certified_forward_samples=0`、`positive_ev_verified=false`；不得將工程設定檢查成功當作預測命中率提升。
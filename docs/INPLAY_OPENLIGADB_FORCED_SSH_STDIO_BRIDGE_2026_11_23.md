# 足球王者 VNext｜第十八關：OpenSSH 強制命令 → 中央私有 Broker（2026-11-23）

## 問題及實際新增
PR #555 增加單主機 Unix domain socket Broker，可將兩個本機客戶端的變更探測／條件式下載請求匯聚至同一個 PR #542 聯賽限速器，但外部主機唔可以直接連到 UNIX socket；**之前未有任何設計上能以受限、經驗證的遠端工作階段把單一請求安全轉給中央 Broker**。
本 PR 新增 `ops/inplay_openligadb_ssh_stdio_bridge.py`，提供一個 **stdin/stdout、one-shot、no TCP listener** 的小型橋接程式。只有經**獨立設定**的 OpenSSH 強制命令可考慮調用，傳輸層及伺服器身份驗證由 OpenSSH/OS 完成，唔係由 Python 程式自行證明。

## 實際執行流程
1. 客戶端透過安全、由操作員預先核對 SSH host key 並授權客戶端 public key 的 OpenSSH 連到**唯一中央收集主機**。使用 `-T`，無互動 shell；OpenSSH sshd 的 `authorized_keys` 必須對該專用公鑰使用 `restrict,command="..."`，或同等獨立審查的 `sshd_config ForceCommand`。`restrict` 同時禁用 port/X11/agent forwarding、PTY 及使用者 rc。請參考 [OpenSSH authorized_keys](https://manpages.debian.org/trixie/openssh-server/authorized_keys.5.en.html)、[OpenSSH sshd](https://man.archlinux.org/man/sshd.8.en)。**不得**為方便起見去掉 `restrict`、開放 TCP proxy 或給予 shell。
2. sshd 被批准的強制命令，以**專用非 root 帳戶**執行 `python3 /REVIEWED/REPO/ops/inplay_openligadb_ssh_stdio_bridge.py --private-root /SECURE/PRIVATE --forced-ssh-stdio`。以上路徑只係操作示例，**唔係已存在的實際部署路徑**；OpenSSH 金鑰、帳戶、known_hosts、sshd 設定、host key、來源 IP allowlist 必須由獨立操作員在真實受控主機設置，絕不提交真實密鑰到 GitHub。
3. 客戶端向 SSH stdin 輸入**一行**符合 PR #555 `REQUEST_SCHEMA` 的 JSON 然後關閉 stdin，例如 `{"schema":"football-king-openligadb-broker-command-v1","action":"probe","season":2026,"group":8}`。只允許 `probe` 或 `capture`（capture 另外必須有 `match_id` 整數）。不接收任何原始 URL、第三方域名、token、秘密、shell 指令，亦不容許一個 SSH 工作階段執行多筆請求。
4. 橋接程式拒絕缺 `SSH_CONNECTION`、非數字 port、無效 IP、任何非空 `SSH_ORIGINAL_COMMAND`、TTY、agent/X11 forwarding 標誌、GitHub Actions/CI、Root、以及干擾 Python 執行的若干環境變數；請注意這些環境欄位**可以被本地程序偽造，僅作誤操作檢查，不構成 sshd 身份或政策證明**。
5. 它向 PR #555 受控的 **本機** Unix socket 呼叫 `request_private_broker(root, command)`；中央 Broker 仍以 `SO_PEERCRED`/檔案權限核對同一 OS UID。因而 sshd forced-command 帳戶的 OS UID 與 Broker socket 擁有者要有**獨立審核的最少權限安排**，不能為了讓遠端登入而放寬 socket 0600/根目錄 0700。
6. Broker 原有同聯賽 90 秒／故障後 600 秒限速、變更標記、原生 season/group/matchID 檢查及 create-only 私有封存保持不變。橋接程式對上游回覆只容許完整固定 schema，`HOLD` 直接輸出固定安全原因；通過者只會回傳自算 SHA256、安全旗標及變更狀態，絕不回傳 HTTP body、球隊或原始 token。

## 可核實程度與嚴格邊界
**本輪只開發並以合成資料測試 SSH forced-command stdio 適配器，未建立 sshd 用戶、authorized_keys、私有伺服器、網絡隧道、實際 remote hosts 或任何實時供應商 API 請求。** 因此不得宣稱已有跨主機受控部署、mTLS、host-key pinning 實測、跨 host firewall 隔離、全局 egress 限速已強制執行。Python 從 `SSH_CONNECTION` 讀到嘅值唔等於已驗證 sshd 來源，程式永遠 `sshd_forced_command_policy_verified=false`、`ssh_authentication_independently_verified=false`、`ssh_host_key_pinned_and_verified=false`、`cross_host_firewall_verified=false`、`centralized_across_hosts_verified=false`。
若日後配置 SSH forced command，亦必須逐項測試 sshd 密鑰及 restricted principal、password/keyboard-interactive 不容許繞過、不同 host 的客戶端對 OpenLigaDB 直接 egress 被 OS/網絡阻止、時間偏移、agent forwarding 關閉、服務隔離、網絡故障時沒有新來源 GET，以及同一來源 IP 配額限速。僅靠 Python 程式及兩個 fake clients 唔能證明以上條件。
原始封包留在操作員配置的私有資料夾，不可提交到公開 GitHub Actions artifacts；任何公開結果不可包含真實盤口或可識別秘密。

## 測試及工程驗收
- 新增 `ops/tests/test_inplay_openligadb_ssh_stdio_bridge.py` 16項**純合成**測試（先提交）：缺 SSH context、錯 IP/port、PTY/agent/X11/CI、遠端命令注入、root、unknown URL/secret/extra JSON keys、duplicate JSON keys/NaN、超長/多行 input、單次 probe 轉發、惡意上游 output 欄位、壞 digest/schema/status、異常無 secret leak、CLI 在 CI 不碰 socket。
- `python -m compileall -q ops`
- `python -m unittest discover -s ops/tests -q`
需檢查 exact HEAD GitHub workflow 7項 checks，包括兩套完整 regression；獨立審核前保持 Draft，不合併研究鏈。

## 不可提升的研究門檻
`production_recommendations=DISABLED`, `eligible_for_model_input=false`, `eligible_for_model_scoring=false`, `positive_ev_verified=false`, `certified_forward_samples=0`, `recommendation=null`、`roi=null`。真正來源雙驗證、官方紅牌、可信 TSA/原始回應身份、真實xG、即時可成交莊家盤口與樣本外校準，今輪完全冇加入；通過工程測試唔等於模型預測改善。
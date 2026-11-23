# 足球王者 VNext｜第十九關：SSH 強制命令標準輸入有界時限（2026-11-23）

## 確認的實際程式缺口
上一輪 Draft PR #558 `ops/inplay_openligadb_ssh_stdio_bridge.py` 使用 `reader.read(MAX_STDIN_BYTES+1)` 讀取 OpenSSH forced-command 的 stdin。對於真實 SSH pipe/socket，Python 緩衝式 `read(N)` **可能一直等待 N bytes 或 EOF**。如果 SSH 客戶端只送出一行 JSON，卻刻意保持輸入串流開啟，橋接程序便可能無時限佔用一個進程／連線。上游中央 Broker 有 timeout，但呢個問題發生於客戶端命令到達 Broker **之前**，所以 Broker timeout 救唔到。

## 研究分支修正
- 新增 `_read_one_command(reader, timeout_seconds)`：真實檔案描述符經 `select.select`、`os.read` 等待資料與 EOF，計時用 `time.monotonic()` 計算**整體絕對截止時間**，唔會因每次收到一個位元組而重新計時。預設最多3秒讀取完整指令；即使送到一行合法 JSON，唔關閉 stdin 都會 HOLD。
- 固定最多 `MAX_STDIN_BYTES=MAX_REQUEST+1` bytes（包括唯一換行符），多行、超過上限、未換行、過期、不正常檔案描述符、下游解析錯誤全部拒絕。必須**完整一行＋EOF**先調用 #555 的本機 `request_private_broker`，唔會因半條指令先發 provider HTTP。
- 純合成測試需要 `io.BytesIO`，由程式明確識別並執行同樣長度、單行和結尾檢查；真實 SSH stdin 使用 fd 路徑，唔使用可能無限阻塞的 buffered `.read(N)`。未支援 fileno 的其它未知 stream **不退回**無界讀取。
- 新增 `ops/tests/test_inplay_openligadb_ssh_stdin_deadline.py` 11 項 no-network 對抗測試：有效 pipe+EOF、完整一行但 writer 保持開啟、部分一行無 EOF、空 pipe、慢速逐 byte 輸入（絕對時限）、同連線雙指令、超長且不 EOF、缺少換行、非法 SSH 環境先於讀取被拒絕、既有 synthetic BytesIO 相容、錯誤 deadline 設定拒絕。每項都驗證未符合條件就**不調用中央 Broker**。

## 設計邊界
這項修正只限制 Python bridge 的單次 stdin command parsing；**唔可以視為真正 DoS 防護已全面部署**。實際服務仍需 OpenSSH `MaxStartups`／`MaxSessions`／`LoginGraceTime`、每帳戶連線數、PAM／系統資源配額、作業系統防火牆同代理、Host Key、SSH restricted authorized_keys 全部由獨立操作員核對。3秒截止時間亦唔係外部身份／來源 timestamp 見證。
要透過 forced command 遠端用此 bridge，SSH client 應一次送完單行 JSON 後關閉寫入端（stdin EOF），而唔係保持長駐互動 shell。仍不容許任意 command、URL、PTY、SSH agent／X11 forwarding 或上傳原始來源證據。

## 已知安全及合規未完成項目
- **未有真實跨主機 SSH 部署、SSH 身份驗證、中央主機網絡出口防火牆、強制客戶端不可直接訪問供應商或獨立來源證據／TSA。** 本輪不發任何 OpenLigaDB HTTP 亦不設金鑰或上傳敏感資料。
- 仍保留前瞻樣本0場、`production_recommendations=DISABLED`, `eligible_for_model_input=false`, `certified_forward_samples=0`, `positive_ev_verified=false`。工程 CI 成功只說明預期安全行為在合成情境成功，不能推論已提高足球預測準確率、具可成交盤口或正EV。
- 疊加研究 PR #529→#530→#531→#532→#533→#535→#537→#538→#542→#543→#546→#548→#552→#555→#558→本 PR。保持 Draft，獨立審核及依賴處理之前不合併 main。

## 驗收
```bash
python -m compileall -q ops
python -m unittest discover -s ops/tests -q
```
必須驗證 latest exact-head 7個 GitHub CI：safety 3.11/3.12、regression×2、stress、ledger-tests、validate，遇失敗先讀原始日誌再修正。
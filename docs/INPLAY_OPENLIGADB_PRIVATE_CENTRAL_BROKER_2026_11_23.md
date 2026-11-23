# 足球王者 VNext｜第十七關：中央受控 Unix Socket 來源入口研究原型（2026-11-23）

## 已經實際增加的功能
承接 Draft PR #552 的預設拒絕真實 HTTP 環境驗證。本輪新增一個**不公開 TCP、必須手動啟動**的 Unix domain socket 收集入口。所有經此入口請求均由**同一部專用 POSIX 主機**代為執行既有 PR #543 的來源變更探測、PR #546 的指定賽事條件式下載，並共用 PR #542 的同聯賽排他鎖／90秒正常間隔／600秒故障冷卻。呼叫端只收到打碼安全摘要及 self-hash，**原始 HTTP body 永遠留在中央私有 0700 目錄內**。

新增檔案：
- `ops/inplay_openligadb_central_broker.py`：private Unix socket ` .openligadb-bl1-research-broker.sock`（實際名稱開頭無空格），只容許單一 request JSON line 的 `probe` 或 `capture` 動作。完全禁止任意 URL、host、provider、API key、token 或其他未知欄位；原生 season/group/matchID 需以 strict type 驗證。請求上限512位元組、回覆上限2048位元組、每個連線只執行一個命令。
- Socket 位於事先存在、由操作員持有的 Git repo 以外 0700 私有目錄，以 0600 權限建立。每次請求都驗證 socket 原 inode / mode / owner、目錄權限及 Linux SO_PEERCRED（或支援 getpeereid 的 POSIX 系統）；唔能核對本機 peer 身份就拒絕。伺服器單線程序列處理命令，避免不同應用程序各自讀取聯賽限速檔。
- `request_private_broker(root, command)`：本機 Python 客戶端，以 AF_UNIX 向指定私有 socket 發送單一 schema JSON；不直接對外 HTTP。回傳只有固定安全欄位、變更狀態及未認證 SHA256，不包含球隊名字、原始資料、URL、原始更新時間字串、秘密或命令原文。
- `main(--private-root ... --serve-manual-broker)`：明確手動啟動的阻塞 CLI；先強制 PR #552 的 `require_manual_egress()`（CI/runner、代理、TLS覆寫、root或缺少操作宣告都拒絕）再建立 socket。GitHub CI 測試只注入兩個 synthetic fake getter，絕不連真正 OpenLigaDB。CLI 不會由任何排程自動啟動。
- `ops/tests/test_inplay_openligadb_central_broker.py`：14項合成測試，包括首次 baseline→變更→原生輪次條件式一次下載、同時兩個客戶端只一次來源 probe、未有 changed token 不准下載、拒絕任意 URL/secret/惡意 JSON/異常欄位、私有 socket 0600、root 在 Git repo 或弱權限拒絕、socket 變成 public mode 拒絕、已有 symlink 不覆寫、CI 無法啟動真實 broker，以及服務關閉時安全移除原 socket。

## 必須明確區分單主機集中 vs 真正跨主機
**本 PR 只實作一部機器的中央收集程序，並非已經完成跨伺服器協調。** Unix socket 本身無法從第二部機器直接連入；要跨主機使用，需要另行批准及部署具身份驗證的安全 SSH Unix socket forwarding 或 mTLS 反向代理，確保各客戶端**只能**通過中央 broker 讀取，並在網絡／容器／主機 OS 層拒絕所有直接對外向 OpenLigaDB 的 egress。此 PR 沒有建立 SSH tunnel、mTLS、反向代理、遠端部署或實際防火牆測試；也未證明已把其他既有數據收集程式強制路由經 broker。

由於外部 SSH forwarding 可能會擴大 Unix socket 的使用者存取，部署前必須獨立設計專用帳戶、OS filesystem ACL、SSH key/peer 身份、socket forwarding 限制、connection timeout、資源限制以及命令審計。任何未經驗證的轉發或公開 TCP 入口都唔可以當作安全中央限速。

## 零證據升級及防資料外洩
- 即使該 broker 實際運行，它收集的 OpenLigaDB 社群資料亦不構成官方紅牌、實際xG、可成交莊家賠率、第二獨立來源或可信 TSA；變更 token 是未認證的來源聲稱，並不證明具體 matchID 的資料改變。
- 所有研究回覆固定 `production_recommendations=DISABLED`、`eligible_for_model_input=false`、`eligible_for_model_scoring=false`、`positive_ev_verified=false`、`certified_forward_samples=0`、`cross_host_firewall_verified=false`、`centralized_across_hosts_verified=false`；沒有模型準確率或正EV改善宣稱。
- 公開 GitHub workflow 對此項目僅做 fake source tests，未有真實 API 請求、私有原始封包上傳、iPhone 連線、任意帳戶付款或背景服務啟動。

## 驗收
```bash
python -m compileall -q ops
python -m unittest discover -s ops/tests -q
```
需確認 PR 最新 head GitHub 安全(3.11/3.12)、regression兩組、ledger、stress、validate 合共7個 checks 全 PASS，獨立程式審核前維持 Draft。下階段真正跨主機部署必須於受控環境完成網絡層 deny-by-default、遠端身份驗證、provider fair-use 配額及私有存檔取回測試；否則仍然 HOLD。
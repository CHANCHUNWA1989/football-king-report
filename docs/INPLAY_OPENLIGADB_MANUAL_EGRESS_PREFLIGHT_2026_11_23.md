# 足球王者 VNext｜第十六關：OpenLigaDB 手動來源 HTTP 出口部署前檢查（2026-11-23）

## 工程缺口
研究 Draft PR #548 已退役舊版直接 GET CLI，但新 PR #546 的 changed-token 手動下載，以及 PR #543 的 lastchangedate 手動探測，仍可在 GitHub Actions/CI、具代理/TLS覆寫或高權限環境下意外啟動真正 HTTP。
本輪在真實網絡 transport 前加程序級 fail-closed gate，且不修改封存 A/B/C/D、main、模型權重或投注功能。研究鏈 PR #529→#530→#531→#532→#533→#535→#537→#538→#542→#543→#546→#548→本 PR 全部仍待獨立審核。

## 已實作
- ops/inplay_openligadb_manual_egress.py：預設拒絕。只有操作員顯式配置非秘密宣告 FOOTBALL_KING_OPENLIGA_MANUAL_EGRESS=ONE_SHOT_RESEARCH_V1 才可進入 RESEARCH_ONLY。此宣告只是操作確認，唔係 API key 或正式資料授權。
- 對 CI、GITHUB_ACTIONS、GITHUB_RUN_ID、RUNNER_OS、GITHUB_TOKEN、ACTIONS_RUNTIME_TOKEN 存在的環境一律拒絕；同時拒絕 HTTP(S)_PROXY、ALL_PROXY、NO_PROXY 等大小寫變體及 SSL_CERT_FILE、SSLKEYLOGFILE、PYTHONHTTPSVERIFY、REQUESTS_CA_BUNDLE、CURL_CA_BUNDLE 等 TLS 覆寫，亦不允許非 POSIX 或 root UID。任何錯誤只回傳固定代碼，不洩漏環境值。
- ops/inplay_openligadb_lastchange_probe.py 與 ops/inplay_openligadb_conditional_capture.py：當 getter=None 代表真正 HTTP 時，先於開私有目錄／寫限速檔／消耗來源 token 檢查環境，未通過即 HOLD、HTTP 請求數0；注入 fake getter 的合成測試保留。
- ops/inplay_openligadb_one_shot.py 及 lastchange 兩個底層 _fetch_one：再次做 fail-closed 檢查，urllib 使用 ProxyHandler({}) 不繼承環境代理，並保留固定 HTTPS API、TLS、拒絕 redirect 及 timeout。
- ops/tests/test_inplay_openligadb_manual_egress.py：14項無網絡合成測試，覆蓋無宣告、正確／錯誤宣告、CI、大小寫代理、TLS覆寫、root、不合法環境映射、底層 real transport 再驗證、動作前無副作用及 fake getter 可用。

## 安全界線
此 gate 只能證明程式按眼前環境變數作了安全檢查，**唔係 OS firewall、容器 sandbox、跨主機或整個出口 IP 限速、DNS/HTTPS 外部證明、實際取得原始資料、供應商身份、TSA 時間見證或資料授權證書**。惡意本地程序仍可修改程式或自行發 HTTP；絕不宣稱已完成真實部署安全。
實際上線前必須在受控 POSIX 主機由獨立操作員核對：最小權限非 root 身份、私有 0700 repo 外目錄、OS 層 egress deny-by-default / API allowlist、跨主機 limiter、秘密管理及授權條款、是否允許保存／加密原始資料、資料保留期及不可公開上傳 GitHub Actions。
即使環境檢查通過仍永久 host_firewall_isolation_verified=false、cross_host_rate_control_verified=false、production_http_isolation_certified=false、source_authenticated=false、eligible_for_model_input=false、certified_forward_samples=0、positive_ev_verified=false、production_recommendations=DISABLED。

## 驗收
python -m compileall -q ops
python -m unittest discover -s ops/tests -q
審查新 PR 的最新 exact-head GitHub CI，安全與完整回歸全通過後只代表本輪工程可驗收；不能單獨合併未審查上游研究鏈。CI 只使用 synthetic 回應，沒有任何真實供應商請求、未執行正式部署、未新增可認證前瞻樣本。
# 足球王者 VNext：第十四關條件式單場來源擷取（2026-11-23）

## 範圍與前置
研究 Draft PR #543 已在同一個 POSIX 主機／0700 私有資料夾限制 OpenLigaDB bl1 共用90秒成功／600秒失敗間隔，單次手動取得 getlastchangedate(bl1,season,group) 的未認證 JSON 字串。但舊 checkpoint 只保留最新 token，跨程序無從核對上次與今次是否曾經不同。

本輪新增以下兩個有測試的變更：
1. 擴充 ops/inplay_openligadb_lastchange_probe.py 的私有 checkpoint：previous_token_sha256、transition（BASELINE_ONLY／UNCHANGED／CHANGED_UNATTESTED），驗證其與當前 token digest 的內部一致性。新格式不能直接沿用任何舊私有研究 checkpoint；遷移需要獨立審核。
2. 新增 ops/inplay_openligadb_conditional_capture.py：人工顯式指定原生 matchID、season、group、已配置私有 root，只有最近5分鐘內曾觀察到 CHANGED_UNATTESTED、同聯賽共享90秒閘已開，才允許嘗試一次原始賽事 GET。先喺鎖內為 (season, group, matchID, token SHA256) 以0600、O_EXCL、NOFOLLOW 建立 create-only reservation 並 fsync/readback；任何 HTTP 失敗或 crash 仍視該 token+matchID 已被使用，之後不會相同 token 重試。然後寫入600秒冷卻，再進行唯一一次 GET；成功且原始 HTTP body 由 #538 以私人檔案成功重播後，限速改成90秒。

另外，完整 response 裏面的 leagueSeason 與 group.groupOrderID、matchID、球隊 ID、聯賽簡稱、開球時間及比賽狀態都要一致，否則 HOLD，不封存錯輪次資料。保留私有原始回應 bytes，同時唔會將任何真實球隊、秘密、原始 token 或 HTTP body 印出 GitHub 日誌。

## Manual-only 操作順序
* 在同一台受控 POSIX 機、同一個位於 Git checkout 以外的0700 私有根目錄，先執行一次 PR #543 的 manual-probe 建立 baseline。
* 最少90秒後，對同一季同一輪再次 manual-probe。只有看到 CHANGED_UNATTESTED 才考慮下一步。
* 再等同聯賽90秒，且必須係本機自報 probe 完成後5分鐘內，用 ops/inplay_openligadb_conditional_capture.py 的 --match-id、--season、--group-order、--private-root、--manual-changed-only 手動執行一次。
* 例子中的 season=2026、group=8 只係合成測試常數，**唔代表目前德甲真係有該場賽事**。本 PR 沒有執行真正 API GET，亦未建立運營私有儲存。
* 此功能絕不開啟 schedule、重試、任何自動下單或 Live betting recommendation。

## 不可誤解之處
* matchday 變更只證明「未認證來源聲稱有資料變動」，不證明目標 matchID 的比分、入球或紅牌改變。兩次來源 HTTP 請求至少相隔90秒，來源可能再次修改；token-to-body causal proof **一直 false**。
* 即使當時成功收到 HTTP，仍不是 provider-signed origin、可信 TSA、外部時間存在證明、第二獨立來源、官方紅牌、真實xG或可成交盤口。所有模型輸入及投注永遠 HOLD/DISABLED，認證樣本=0。
* **舊 PR #538/#542 手動全量 GET CLI 尚存在**，所以本次只能稱為新增一條手動變更條件式路徑，不能宣稱整個系統已統一強制 changed-token 後才可下載。若要部署，必須先由另一項獨立安全改動退役／封住舊 bypass，以及建立跨主機／同外部 IP 的全局配額管理。
* 私有 JSON 及檔案非 WORM；同一 OS 用戶有能力修改／刪除，不能作外部認證來源。
* 所有 code / CI 資料為 synthetic，絕不會打真實 OpenLigaDB API。

## 驗收
python -m compileall -q ops
python -m unittest discover -s ops/tests -q

必須以新 PR 的 exact head 檢查全部 GitHub Safety Python 3.11／3.12、regression×2、stress、ledger、validate，獨立 review 前不得合併 Draft 研究鏈。

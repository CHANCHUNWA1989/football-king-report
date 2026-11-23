# 足球王者 VNext｜第十一關：OpenLigaDB 單場原始 HTTP 回應私有保存（研究模式，2026-11-23）

> **2026-11-23 後續安全更新（PR #548 研究鏈）：此文描述的 `--manual-one-shot` 直接下載 CLI 已退役，現只會 HOLD，絕不發出 HTTP。需以 `ops/inplay_openligadb_conditional_capture.py --manual-changed-only` 並提供 season、group、matchID 及事先變更快照作手動研究。舊文檔下文指令只作歷史設計記錄，不應操作。**

## 現階段真正做咗乜
在 Draft PR #537（本機安全封包保存）上加一個 **可實際執行但不會自動啟用** 的單場 HTTPS OpenLigaDB 接駁。新增 `ops/inplay_openligadb_one_shot.py` 與 `ops/tests/test_inplay_openligadb_one_shot.py`。

**唔係只用 user-supplied normalized source-claim JSON**：手動呼叫時，程式會向官方 `https://api.openligadb.de/getmatchdata/{matchId}` 做**一次 GET**，保留收到嘅原始 HTTP response body 位元組，建立本機請求起／完成 UTC、狀態碼、媒體種類、原始 bytes SHA256 同固定請求網址的 receipt。兩件資料放在同一個 deterministic USTAR。檔案以 digest 命名，操作員必須先建立 0700 私有目錄（不在 Git repo 內），程式以 O_EXCL/O_NOFOLLOW 建立 0600 檔案，fsync 後 readback + SHA256 + parser 重播。相同位元組重試為 no-op，衝突／修改／非法路徑一律 HOLD。

## 最新官方資料授權（需持續覆核）
- [OpenLigaDB Data License](https://www.openligadb.de/en/license)，2026-11-07更新：資料係 ODbL 1.0，可用、複製、修改、再發佈（包括商業用途），需署名及遵守 share-alike 等條件。公佈資料必須有 `Data from OpenLigaDB (www.openligadb.de), licensed under ODbL 1.0`；球隊 logo / 圖像及第三方商標不在數據授權範圍。
- [OpenLigaDB API Terms](https://www.openligadb.de/en/terms-of-use)，2026-11-07更新：資料由社群登錄，**沒有編輯審核**，即場可有延誤、錯誤。即場每聯賽建議最多約30–60秒一請求；要用 `getlastchangedate` 先輕量 polling，有變化先抓完整資料。429及5xx要退避，不要即時重試；不要讓每個手機客戶端各自直連。API 現時免註冊／免 API key，不保證永遠可用或免費。
- [OpenLigaDB Swagger](https://api.openligadb.de/index.html)：`GET /getmatchdata/{matchId}`，回應包括 `matchID`, `team1`, `team2`, `matchDateTimeUTC`, `matchIsFinished` 等。

本 PR 故意 **沒有高頻輪詢／定時排程／重試機制**，只允許人工顯式執行一次。**尚未加入同聯賽全局60秒鎖／LastChanged 變更檢查；所以不得將此 CLI 接入自動排程或讓多裝置並行呼叫。** 若將來要上線持續輪詢，先要獨立開發集中快取、率限制及變更探測工具，亦要按供應商更新條款審核。

## 安全閘門
- 只允許固定數字 `matchID`（1..999999999），固定官方 URL，no redirects，200 狀態及 JSON / text-json / text-plain，原始回應大小 ≤250kB，讀取逾時15秒，無 secret、無輸入 URL、無帶參數可控的域名。
- 檢查嚴格 JSON（重覆 key、NaN 拒絕），要求 `leagueShortcut=bl1`、season integer、native `teamId` 兩隊存在且不同、同一 `matchID`、`matchIsFinished=false`、觀察時間符合 kickoff 至3小時內。
- 即使成功儲存，**不會**用 `goals` / `matchResults` 直接推導可認證比分：OpenLigaDB 即場資料未必即時一致，亦唔提供合適紅牌證據。(non-zero/zero紅牌不可由缺值推斷) 無合法實時 odds 或真實 xG。
- 研究回報 `local_original_response_bytes_readback_verified=true` 僅代表**本機取到嘅 HTTP response body bytes 可讀回**。無 TSA、TLS handshake 外部簽名、獨立供應商證據、第三方原件見證、賽事官方來源認證，模型仍唔能接入。測試用 fake getter 可模擬相同 API 形狀，故測試成功唔證明真實 HTTP 當場成功。
- `production_recommendations=DISABLED`、`eligible_for_model_input=false`、`certified_forward_samples=0`、`positive_ev_verified=false` 永不因為本模組變成 TRUE。

## 人工受控操作（Linux / POSIX + 擁有人確認來源用途）
先用 POSIX `install -d -m 700 /secure/private-research` 在 Git repo 之外建立私有儲存位置。**請按自己環境調整路徑，勿喺公開 Actions runner 做真資料永久封存。**

```bash
python ops/inplay_openligadb_one_shot.py \
  --match-id <受控、已確定的OpenLigaDB matchID整數> \
  --private-root /secure/private-research \
  --manual-one-shot
```

因程式只准當時進行中的 `bl1` 比賽，無賽事或離開時間窗就應該回傳 HOLD，不要用歷史 completed case 測試當真即場前瞻。依需要用 `replay_saved(private_root, archive_sha256)` 驗證有冇遭修改。**本 PR 未執行任何真實供應商 GET，也沒有喺用戶裝置建立私有資料夾**；測試全為注入式 fake HTTP response。

## 驗收
```bash
python -m compileall -q ops
python -m unittest discover -s ops/tests -q
```
含12項新 synthetic tests：原始位元組保存＋私有重播、拒絕 wrong ID / season/league/teams/KO、finished、轉址與錯誤媒體類型、429、過大、NaN、重覆 JSON 欄位、symlink／git／公開可讀目錄、私有檔案被改、無重試及敏感文字不回傳。保留 Draft + HOLD，逐項 CI 核實及獨立人手 review 前唔合併。

## 下一真正阻塞
第一個來源做完真正受控捕捉之後，仲要第二個**確實獨立及獲授權**的官方事件/紅牌資料來源、可信外部時間與來源原件見證、同一原生賽事ID的跨來源匹配，以及真實逐場 sealed forecast 模型執行收據。未滿足不能計算可靠正EV、回測宣稱、商用正式投注。

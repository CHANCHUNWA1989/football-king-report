# 足球王者 VNext｜第十三關：OpenLigaDB 最後變更時間探測（2026-11-23）

## 目標及官方依據

上一關 Draft PR #542 已建立單一 POSIX 主機內，德甲 `bl1` 全聯賽共用的 `fcntl.flock` 限速閘門（成功90秒，錯誤/崩潰600秒），但仍然欠缺官方建議嘅低成本 `getlastchangedate`。本輪只補一個可獨立驗收嘅小階段：**同一把鎖、同一個時鐘限制先探測一個指定賽季及輪次的來源變更標記，保留可重播的原始回應 byte，再比較是否變更**。

2026-11-23 官方面向：
- [OpenLigaDB API OpenAPI Swagger JSON](https://api.openligadb.de/swagger/v1/swagger.json)：`GET /getlastchangedate/{leagueShortcut}/{leagueSeason}/{groupOrderId}`，200 是 JSON **string date-time**，非完整比分／事件。只准目前研究支援的 `bl1` 德甲、2020–2100賽季、輪次1–34。
- [OpenLigaDB API 使用條款](https://www.openligadb.de/en/terms-of-use)，上次更新2026-11-07：即場每聯賽（非每場／每用戶）約30–60秒一請求；用 `getlastchangedate` 優先查變更；遇429/5xx應 backoff；大規模使用需中央快取；社群編輯的即場資料可能不準確。
- [OpenLigaDB ODbL 1.0](https://www.openligadb.de/en/license)，需適當來源署名。本模組不公開來源全文。

## 新增實際功能

- `ops/inplay_openligadb_lastchange_probe.py`：
  - `probe_once(season,group,private_root,getter=None,now=None)`：操作員**明確手動**執行一次 GET，固定 HTTPS官方來源、15秒timeout、200、原始 URL，不允許 redirect、無自填 URL/API密鑰、最大256 bytes、嚴格 JSON 字串 datetime parser。
  - 和 PR #542 的 **完全相同 `.openligadb-bl1-pacing.json`** 共用 flock / 90秒與600秒窗口。先預留600秒失敗冷卻，探測成功+私有讀回驗證後才縮成90秒；同一個主機的 PR #542 完整 match GET 及本探測亦互相阻擋短間隔呼叫。唔 sleep、唔 retry、唔自動 poll、唔發出第二個完整 match GET。
  - 事先建立擁有人-only `0700`、位於 Git repo 外的安全私有根目錄；在其中固定 `0600` `.openligadb-bl1-lastchange.json` 用 `O_NOFOLLOW` 存原始 response bytes 的 base64、其 SHA256、字串 token SHA256、season / group key、自報本地 observation UTC。讀入時嚴格檢查檔案owner/mode/hardlink/symlink/inode、JSON schema、位元組原件 hash 及 monotonic 時間；任何不符 HOLD。
  - 第一次讀取只建立 `BASELINE_ONLY`；後續用**字串等值**比較同一 season+group 的兩個 token，分成 `UNCHANGED` 或 `CHANGED_UNATTESTED`。同一私有根目錄一時間只容許同一輪次；如需切換，須使用分開獲審核的 private context，並服從同 IP 的全域總配額。
  - Source token 即使格式為 ISO date-time，可能**沒有時區**，所以絕不將其當作 UTC發佈時刻、不從 token 推算實際入球或資料何時可用。原始 bytes 係該程序收到的原文，亦沒有第三方時間簽章／官方發布者身份簽章。
  - 回報只有安全研究欄位、`source_token_sha256_unattested` 同 `raw_response_sha256_unattested`，不輸出原始 token/網址或原文，無外部網絡測試資料被提交到 GitHub。
  - 手動 CLI：`python ops/inplay_openligadb_lastchange_probe.py --season 2026 --group-order 8 --private-root /SECURE/PATH --manual-probe`。所示賽季輪次只作參數示例，不代表今日有該輪次比賽；必須實地核對賽程/來源授權才使用。

- `ops/tests/test_inplay_openligadb_lastchange_probe.py`：14項 synthetic fake HTTP tests，首次 baseline、未變、更改、錯 JSON/date-time、HTTP302/429/5xx、URL 偽冒、超大回應、clock rollback、錯 group、private symlink/hardlink/weak permission、雙 threads 競態、與舊完整 match GET 互相限速。**CI 不會對真正 OpenLigaDB 作網絡請求。**

## 尚未完成及絕不可偷步的功能

**本 PR 未將完整賽事 GET 改為「token changed 才可執行」的閉環**。即使回傳 `change_detected=true`，`eligible_for_full_match_auto_fetch=false`、`full_match_get_performed=false`，未修改 PR #542 的舊手動 full GET 入口；不可上自動排程或宣稱 `getlastchangedate` 已阻止所有不必要 download。下一輪需要綁定 `season + group + matchID`、保存 `last_captured_change_token`，於同一分布式或單主機閘門實行先 probe 後等待90秒、再唯一一次完整資料擷取，且處理 stale token、provider changed during two calls、429 退避。

此 PR 同樣沒有跨雲/跨不同主機全局配額，沒有真實環境部署、沒有取得兩個具原始證據獨立的事件來源、紅牌、即場xG、莊家即時盤價、TSA、前瞻核實或OOS效能。所有回報 `production_recommendations=DISABLED`、`eligible_for_model_input=false`、`positive_ev_verified=false`、`certified_forward_samples=0`。不可把模擬測試通過當成真實賽事證據。

## 研究分支與驗收

Draft 疊加鏈：PR #529→#530→#531→#532→#533→#535→#537→#538→#542→**本PR**。每輪只做一件獨立改進；無獨立code review就唔合併，亦唔改main或封存A/B/C/D。

```bash
python -m compileall -q ops
python -m unittest discover -s ops/tests -q
```

必須核對 **exact-head** GitHub safety Python3.11/3.12、regression×2、stress、ledger、validate 全成功後，只可宣稱工程 CI 已驗收。

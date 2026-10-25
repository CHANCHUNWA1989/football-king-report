# 同回應盤口處理鏈：採集 → 綁定 → 消費者重驗 → 公開安全摘要

## 已重現的工程斷點

既有 The Odds API 私人 h2h collector 逐項 append outcome，沒有完整主／和／客組要求，
容許空 event ID／陌生選項，且市場時間缺失時會回退 bookmaker 時間。
舊 screener 沒有消費完整報價證據。這是可修復的程式問題，不是外部來源授權不足。

本次透過已有的 `all_market_private_feed.collect → all_market_screen.screen →
private_artifact_guard.sanitize → private_summary_archive.prepare` 路徑接通；
不另建孤立工具、排程或私人儲存，不增加 HTTP／markets／regions／免費額度使用。

## 完整組及證據契約

- 每次原有 response 完整接收後立即驗證；native sport_key／event ID、home／away、
  bookmaker key、唯一 h2h market 及恰好三個不同選項均須明確有效。
  重複 event ID 的全部副本、重複 bookmaker、重複 h2h market 或缺側／壞價整組隔離，
  不以 first-wins 或截斷掩蓋資料缺失。
- 保留原有20分鐘研究更新窗口、嚴格超過10分鐘開波緩衝及少於7日賽程範圍。
  只用 market.last_update，更新 ≤ 回應完成；不容許未來市場時間，不回退 book 時間。
- 原件、完整20欄 row 及 v2 digest 只進既有 runner-local 私人工作檔。
  row `line=0` 是舊 generic screen 的 h2h 相容佔位值，v2 canonical 的 line 明確為 null；
  任意改成其他盤線會拒絕。
- `football-king-bound-h2h-feed-v1` producer 綁定 league／sport／native event ID／主客隊、
  bookmaker／HOME-DRAW-AWAY／price／更新及回應完成與紀錄開波時間。
  原來源沒有 native quote ID；本地觀測 ID 帶 `derived:` 前綴，明示
  `DERIVED_COMPOSITE_NOT_PROVIDER_NATIVE`，不冒充供應商報價識別。
- screener 從 row 重建 canonical 及完整 expected v2 record，拒絕改寫、未知欄位、
  非字串 JSON 時間、過期或不完整組；100,000列上限整批拒絕、不截斷。
  generic legacy研究輸入仍可分析，但明示 LEGACY_UNBOUND_RESEARCH，不作新鏈的通過證據。
- source_verified、independently_calibrated、lineup_checked、independently_verified 一律 false。
  雜湊是內容一致性檢查；能重寫資料及摘要的攻擊者仍能重算，不能稱為來源認證或簽章封存。

CONNECTED 仍只代表取得供應商回應，可能有0個完整合格市場；新 screener 的
quote_evidence_validation 分開報告接受數／完整組數及固定拒絕原因。
公開摘要仍只輸出既有白名單彙總數量，不公開 fixture／球隊／bookmaker／原價／單條 digest，
也不增加正式樣本或 VERIFIED_VALUE。

## 驗收及運行方式

先以現有 fixture 重現缺側、空 ID、未知選項及 book 時間 fallback。
舊正 fixture 補回第三側及 native sport_key，另保留缺側負例；沒有移除故障或配額測試。
新增整合測試使用實際 collect／screen／sanitize／prepare，mock 同一次既有 HTTP 回應，
逐項改寫 producer 後的價格、身份、選項及時間，驗證 consumer 拒絕及公開摘要不洩漏。
另測 script CLI／package 匯入相容。

沒有修改工作流程 YAML，避免因 private workflow 自身的 push trigger 額外採集。
主分支部署後，原有排程下一次在配額允許下執行時會自動使用此路徑；
本次離線及 CI 驗收不等於已取得新真實原件，沒有額外手動 provider 探測。
原始私有報價仍隨 runner 結束消失，公開安全摘要可沿既有流程留存。

## 尚未完成

這是完整的同次 h2h 報價處理鏈，未完成跨賽前／賽後的私人原件保存。
亞洲盤／大小球採集、舊 iphone workflow 的 authorized_asian_quote_audit.json producer、
可信賽果 admission、認證樣本統計及校準亦未因本次修改而完成。
不能把 PropLine 改標成 The Odds API，亦不能把當次新賽前報價送入較早完場賽果當成前瞻結算。
完整正式推薦資格仍須真正獨立來源、實際開波及90分鐘賽果證據和最後人工審核。
本次沒有改寫歷史預測、模型權重、封存 ZIP 或安全政策；HOLD／DISABLED 不變，
未證實能提高預測命中率或盈利能力。

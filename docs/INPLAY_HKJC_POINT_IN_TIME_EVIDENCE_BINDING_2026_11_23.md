# 足球王者｜日本女足截圖、比分雙源及HKJC盤口「同刻綁定」研究閘門

## 起因（2026-11-23）

用戶提供的「長野帕塞羅女足 0:0 浦和紅鑽女足」手機畫面，含 13:30 頁面更新時間及「浦和讓一球勝 2.31」。之後賽果 0:2 **不可倒填**當時未知的真正模型勝率、紅牌或上游盤口更新時刻。畫面中的 13:30 不是外部獨立可驗的 API 上游報價時間；截圖展示的數值亦不可由 SHA256 自動讀出。此 PR 不提交使用者圖片、帳號/下注資料或任何受授權限制的商業原始盤口到公開倉庫。

## 單一改動範圍

新增純 Python、零網絡的 `ops/inplay_hkjc_evidence_binding.py`，重用以下**現有**流程，不調整其安全旗標：

- `ops/live_score_identity_guard.py`: 檢查已在賽前封存的各來源 fixture ID 與兩份獨立 provider 聲稱，以及現況比分、時刻、URL 形式；特別拒絕 `NOT_STARTED` 0:0 假即場。
- `ops/screenshot_evidence_intake.py`: 接收人工標註的 image manifest，核實輸入 bytes 的 SHA256、在場次記錄中連結畫面 event ID、比分及人工檢視聲稱，不宣稱有 OCR。
- 新模組要求以上對應至同一個 **預先封存**的 sportsbook event ID、bookmaker host、聯賽及雙方顯示名稱；引用雙源同一 last material event 時刻及紅牌 count；比分、賽事階段、規定時間分鐘必須相容。
- 三向讓球盤只允許 `HKJC_THREE_WAY_HANDICAP`、整數主隊讓球 -3 至 +3；不以亞洲 `-0.75` 或 `+0.75` 盤混用；必須有 bookie event ID/host、來源聲稱更新及擷取時間，以及與 screenshot image 的 digest 綁定。所有來源更新不超過 90 秒；最後實質入球／紅牌／VAR 的聲稱時刻不可晚於 quote 更新。
- 對有瑕疵的時間、來源、比分、紅牌、盤種、引用鏈及未來賽果／假 EV 欄位一律 `HOLD`；格式一致最多 `RESEARCH_ONLY`，`decision=HOLD`、`model_scoring_eligible=false`，出一份可重算的 **自行聲稱** manifest SHA256。

## 唔可以誤稱嘅地方

此模組**無**去外部網站抓取新數據，**無**驗證 bookmaker 真實更新時間，**無**簽名、Rekor、TSA、第三方 timestamp、密鑰或正式兩源認證；純由輸入者聲稱之「來源」亦未證實真實獨立。即使 `structure_consistent=true`，仍然 **不能證明**（a）截圖內容真正等於 manifest 所填價格，（b）價錢曾可被接受成交，（c）比賽資料已被模型使用，（d）預測改善或正EV。回傳的 image SHA 只核實所見 image bytes 的完整性，不能證明照片在聲稱時間已存在。

特別是 `2026-11-23 13:30 HKT` 的上述舊截圖，只能做事後人工核對，**不可能在完場之後補成有效的即場前瞻研究樣本**。目前缺上游 quote updated 時間、當時雙 provider 原始見證、source event IDs 的賽前封存及獨立外部時間證據，保持 `HOLD`。

## 參數／測試

`audit(fixture, observations, quote, screenshot_bytes, screenshot_manifest, decision_utc)` 完全內存運算，caller 負責合法收集及私密儲存原始證據；無寫文件副作用。示例及 21 項合成測試見 `ops/tests/test_inplay_hkjc_evidence_binding.py`。

```bash
python -m compileall -q ops
python -m unittest discover -s ops/tests -q
```

新增測試覆蓋：正向合成格式／manifest 重算、來源重複／比分矛盾／假開賽 0:0、錯場、截圖篡改、顯示隊伍不同、報價更新缺失／過時／早於入球、即場分鐘錯配、亞洲盤誤用、紅牌缺失／存在、惡意 URL 與事後結果或假 EV 注入、原始輸入不可變、重複摘要穩定性。

## 後續驗收（尚未完成）

1. PR exact-head Actions / 全倉回歸及獨立 reviewer 全通過；不得略過 failure。
2. 一個真實新賽事在開賽前存固定 native provider ID 和 bookie event ID 的封存映射，合法取得更新時間和可重算的原始 source/quote 原件，並**在當時**作獨立外部時間戳見證。
3. 用外部認證的 source/quote 時間及已凍結的同刻模型輸出，才計前瞻 Brier / Log Loss、校準、合法盤口的 EV；保持獨立賽後核實。

**永遠保持 `production_recommendations=DISABLED`；本 PR 沒有自動落注、下注金額、正式推介、模型權重更改或 API 費用。**

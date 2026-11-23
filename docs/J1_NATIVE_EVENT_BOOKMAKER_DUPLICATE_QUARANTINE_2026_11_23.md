# 足球王者｜J1 Native Event / Bookmaker 重複身份隔離（研究 Draft，2026-11-23 HKT）

## 實際發現：first-wins 令覆蓋數量可能不可靠

現有 J1 免費市場副鏈 `ops/japan_free_market.py` 基於 PropLine 來源產生研究用 J1 賽前 h2h / spreads / totals 覆蓋摘要。上游研究 PR #560 已經修正 **同一 bookmaker 內 1X2 outcome/market 重複** 嘅處理；但仍有一個**不同層級**嘅缺口：

- 同一 `event.id` 兩個來源記錄（包括第一筆有效，第二筆矛盾或已完成）原程式只計第一筆；後面異常會被無聲略過。
- 同一場球隊、kickoff 組合但 **兩個不同 `event.id`**，原程式可能將同一場算兩次 `upcoming_events` / `fresh_3way_event_count`。
- 同一 `book.key` 出現兩個 quote blocks，原程式只使用第一筆。即使第二筆價格相反或者 schema 不完整，仍可能用第一筆加另一間 bookmaker 的價格宣稱有兩個有效市場。
- Python `bool` 為 `int` 子類，原生 `event.id=True` 原本會被接受，對來源身份判斷不安全。

## 先測試，再修正（可核對 GitHub）

1. **RED SHA `59156ddb`**：只加入 `ops/tests/test_j1_duplicate_native_identity_quarantine.py` 的 12 個純合成案例。GitHub regression 報告 **10 test failures**，精確指出重複 event ID、兩個 event ID 同一場、重複 bookmaker ID 及 bool ID 等缺陷；其餘正向保持通過。
2. **GREEN 修正 `ops/japan_free_market.py`**：對整批來源 row 先預計算 `event.id` 數量與同場（獲識別 J1 球隊身份、kickoff UTC）數量；凡 count > 1，**全部副本都不計研究覆蓋**，亦不計為可配對市場。原生 ID 拒絕 bool、空白、不可見字元及過長欄位。對每場比賽先預計算 `book.key` 頻次，重複的 bookmaker 即使其中一份報價 invalid，仍隔離所有同 key 版本；保留獨立有效的其它 bookmaker。
3. **清楚獨立的無傷例子**：同一 batch 的另一場（不同 kickoff）仍可計研究覆蓋；如有三個有效 book，其中一個 key 重複，仍可採用其餘兩個獨立 key 的有效研究向量。不能藉此聲稱兩個不同 API 就係真正兩間獨立博彩公司。

### 嚴格界線與來源限制

- 重複身份係從**同一批已提供的原始結構**中檢測，不會嘗試連線供應商查驗 ID 是否真的屬於該場球；所有來源仍需要外部驗證、合法資料使用權、實際更新時刻及最終賽果雙來源核實。
- 資料無異常只代表初步*結構性*一致，**不是**即場可成交盤口、模型校準、正 EV 或前瞻憑證。
- **不修補歷史快照**：`market/japan_free_status.json` 截至目前最後存檔 2026-11-22 08:43:24Z（HKT 16:43），PropLine 7 場係舊 parser 計數，不可宣稱已用新規則重新檢查或重算過往 A/B/C 預測。
- The Odds API 2026-11-22 快照顯示 J1 剩餘 141 點數，只係歷史，低過現有 J1 保護額度 220，唔會嘗試額外查價或猜測當時可用額度。
- 不修改 `.github/workflows`、Secrets、免費配額、網站發布、獨立研究封存、模型權重、實際下注或任何正式推薦。
- `status=RESEARCH_ONLY/HOLD`、`production_recommendations=DISABLED` 永久維持；此 PR 屬 stacked Draft **#562 → #560 → main**，唔自動合併或聲稱認證樣本數增加。

## 驗收

```bash
python -m compileall -q ops
python -m unittest discover -s ops/tests -q
```

要求最新 HEAD 七項 CI（安全 Python 3.11/3.12、回歸 x2、壓力、ledger、validate）全部通過，並有獨立 reviewer。測試全部合成，不係真實賽事回測或實盤 EV 驗證。

## 下一關

待獲授權新來源資料後，先做原生 `event.id`、書商 `book.key` 及各市場 `last_update` 同一時刻封存；再用真正獨立來源核對 fixture/賽果，分開報告覆蓋數與可前瞻評分數。任何缺口維持 HOLD。

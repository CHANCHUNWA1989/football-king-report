# 足球王者｜J1 PropLine 讓球／大小球兩邊價格及盤線一致性修正

研究日期：**2026-11-23 香港時間**。研究 Draft PR #572（疊加 #566 → #564 → #562 → #560 → main）。

## 审查發現

此前 `ops/japan_free_market.py:prop_line` 會在一間 bookmaker 的 `spreads` 市場任何一個來源 `home` 或 `away` outcome 提供有效價格和 quarter-goal `point` 時，將該 bookmaker 加進 `spreads`；`totals` 同樣只要有一個 `Over` 或 `Under`。結尾只看 set 是否非空，因此**只有半邊的盤口也會令 `fresh_spread_event_count` / `fresh_totals_event_count` 加 1**。更差的是同場雙邊 handicap 的方向值可能不相反，Over／Under 可能指不同球數，原版本不會檢查這兩個意義重大的市場關係。

這會虛高*歷史覆蓋摘要*，並不代表有真正可執行的雙邊市場。修正只針對 PropLine 日本 J1 研究性 metadata，不改動 The Odds API 六大聯賽的共用解析器，也不宣稱系統能從 1X2 去水概率推算相應亞洲讓球盤或大小球。

## 最小而完整的 fail-closed 修正

`_complete_two_way_line(kind, outcomes, home, away)` 只接受**同一 bookmaker、同一個 market block** 的一組恰好兩條有效結果：

- `spreads`：一條 `home`，一條 `away`；兩條都有合法 `price_decimal` 或 American odds（沿用已存在 `_price`），及可被 `quarter_units` 無損解讀的 quarter-ball line；**主客 handicap 必須相反**，例如 `-0.25 / +0.25`，`-0.75 / +0.75`。不是要求主勝/客勝概率互補，只係同一結算線。
- `totals`：一條 `Over`，一條 `Under`；兩條都有有效價及**完全相同的非負** quarter-goal line，例如大2.5／小2.5。
- 欄位缺失、單一 outcome、同方向重複、價位或結算線不合法、主客符號不匹配、大細球線不一、同 bookmaker 重複 `spreads` 或 `totals` market blocks、非空 `suspended_at`、過時 `last_update`：均不構成有效兩邊市場覆蓋；不再「先到先用」。
- 既有 `h2h` 兩間有效書商與原生賽事身份去重、跨 API 配對、The Odds API 額度及其他六大聯賽行為不變。
- **一間**已提供完整兩邊嘅 bookmaker 仍可以算研究性「市場覆蓋」1場，**但絕不構成兩間獨立 book、更不是可成交價格或核實 EV**。需要研究獨立 book 的對照另有資格條件，唔可以由此 metadata 推斷。

## 回歸、未核實資料與阻塞

新增 `ops/tests/test_j1_propline_paired_spreads_totals.py` 14項完全合成測試，涵蓋一側報價、重複 sides、重複 market blocks、方向／大小球線相反或相同條件、非法 quarter line、錯價、suspended、正常雙邊正向及其他不受污染市場。最終以 **GitHub exact-head 綠燈 CI** 及源生數據證據為準；若新分支的最早 test-only SHA 沒有 CI 工單，**不得宣稱已實際核對 RED 測試失敗**。相關程式碼原始缺陷可由修正前的 `else` 單邊遍歷邏輯直接審核。

已保存 `market/japan_free_status.json` 快照（2026-11-23 09:41:41 UTC = 香港17:41:41）記錄 PropLine 7 場賽前三向市場覆蓋、The Odds API J1 HOLD、歷史 quota 141、跨 API 配對 0，仍係**舊解析器結果**。本輪無外部授權原件可以合法且可回溯地重新計數，亦未取得 2026/27 J1 真正可成交報價、外部 TSA、官方獨立比分或可信前瞻樣本。

**保持 `HOLD`／`production_recommendations=DISABLED`、無自動投注、無新增 API call／額度消耗、無改動已封存 A/B/C 賽前預測，無正EV／ROI／準確率改善證據。** 獨立正式 Reviewer 未完成，研究 PR 不合併 main。

## 測試

```bash
python -m compileall -q ops
python -m unittest discover -s ops/tests -q
```

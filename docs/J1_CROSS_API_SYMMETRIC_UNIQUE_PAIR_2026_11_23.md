# 足球王者｜日本 J1 跨 API 候選必須「雙向唯一」配對（2026-11-23 HKT）

## 實際缺陷

`ops/japan_free_market.py` 的 `crosscheck(a,b)` 只用 A→B 候選個數同 `used` 集合做**單方向 first-wins**。例如：

- A 來源對同一場有 kickoff 10:00、10:05 兩個候選（可能係重複資料或不一致 fixture），B 只有 10:02 一個候選。舊程式會將第一個 A 當成「唯一」配對並加 1，之後忽略另一個 A。
- A1 10:00 對 B1 10:00、B2 10:20 兩個候選；A2 10:45 只對 B2 10:20 一個候選。舊程式會忽略 A1，再將 A2–B2 計 1，但 B2 實際有兩個 A 候選。
- A 字典元素順序對被選中邊有影響，令跨 API coverage 統計可能不穩定。

上述示例全部係**合成**，不代表真實 J1 比賽；係結構性 bug。

## 本次修正

- 先對所有 A 觀察建立 B 邊候選（保留既有：同樣固定 J1 主、客 team IDs，開賽時間 ±30 分鐘；絕不靠中文名模糊匹配）。
- 再反向統計每個 B 被多少個 A 候選指向；只有 **A 剛好一個 B 且 B 剛好一個 A**，才計作「研究用跨 API 配對觀察」。
- 不使用第一筆優先，亦不貪心搶佔 B。受衝突影響的群組全數拒絕，無衝突嘅其他場次仍可計入原有 coverage 統計。
- 保留現有 JSON schema 和 `same_fixture_two_api_observations`、`median_abs_home_probability_delta` 字段，避免舊報告閱讀器衝突。**注意 ±30 分鐘係粗略 candidate discovery tolerance，絕非同一秒、同一市場版本、可成交 book 價格或來源真正獨立的證明**。
- 已使用 Python 自帶 `collections.defaultdict`，唔增加 dependency、網絡查詢或 API 額度消耗。

## RED → GREEN 可重現驗收

- **RED head `c6700483`**：先提交 `ops/tests/test_j1_cross_api_symmetric_unique_pair.py` 共12項合成測試；兩組 GitHub regression **各有4個 fail**，涉及 2A/1B、順序變動、跨邊矛盾以及含糊場次污染無衝突場次等。
- **GREEN head**：改動 `ops/japan_free_market.py` 的 `crosscheck`，保留正常一對一、兩個互不重疊賽事、邊界 ±30 分鐘及不同主客隊識別；最終以 GitHub 最新 exact-head 7項 CI 結果為準。

## 研究及安全界線

- 上游依賴：**本 PR #564 → #562 → #560 → main**。屬 stacked Draft，冇授權自動合併研究側鏈或啟用正式投注。
- `market/japan_free_status.json` 最近存檔為 2026-11-22 08:43:24 UTC（香港 16:43:24），其 `same_fixture_two_api_observations=0` 及 The Odds API J1 剩餘 141 係**歷史、未經此修補重算**嘅 metadata。冇新授權原始 J1 資料可以用嚟驗證正EV。
- 未改動任何 `.github/workflows`、日程、模型權重、免費/收費 API、Sealed A/B/C 預測、結算、私密 raw book 賠率；不輸出可投注概率或下注金額。
- 無兩個可信來源同場同時刻原始報價、合法重用權限、賽前封存模型及獨立證明賽果前，`production_recommendations=DISABLED`，**模型與投注依然 HOLD**。

## 測試指令

```bash
python -m compileall -q ops
python -m unittest discover -s ops/tests -q
```

CI 通過只係合成解析品質證據，唔等於市場真實性、外部 TSA、樣本外預測效能或盈利性獲認證。

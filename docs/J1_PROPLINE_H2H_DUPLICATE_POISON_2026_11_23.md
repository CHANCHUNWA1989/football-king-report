# 足球王者｜J1 PropLine 1X2 重複盤口污染修正（2026-11-23 HKT）

## 真正缺陷

`ops/japan_free_market.py` 先前只在第二個相同 outcome side 出現時略過該行，卻仍然使用第一個 1X2 報價。例如已出現主勝、和局、客勝後再出現另一筆**互相矛盾的主勝價**，單一 book 仍然得到一個去水向量；若第二個 book 正常，`fresh_3way_event_count` 會被當作 1。重複 `h2h` market block 同樣可能令後面的 market 蓋過之前的值；缺少 `book.key` 亦曾可能把 `None` 視為一個出版社鍵。這只會製造**虛高的研究覆蓋**，不會證明能成交，卻足以令日後 Shadow 試點錯誤理解資料質素。

## 狹窄修正

`ops/japan_free_market.py` 現在：

- 只計非空、有限長度、無頭尾空白的 source-native `book.key`；沒有 ID 的書商唔可以算一間獨立來源。
- 同一 bookmaker 如有多個 `h2h` market blocks，該 book 的 1X2 貢獻完全無效；其他 market 的純覆蓋檢查維持現狀，不由這一改動認證讓球及大小球。
- 在查看賠率能否轉十進制之前，先檢查 `home/draw/away` outcome side 有冇重複；重複即令整個該 book 1X2 向量作廢，唔可以用 first-wins 僥倖接受。
- 如同一 outcome 的顯式 `side` 跟已知球隊 `name` 衝突，不可當作正常主客方向；唔靠模糊隊名做原始身份補齊。
- 仍需至少兩個不同、有唯一 ID 並分別有效嘅書商才能計 J1 `fresh_3way_event_count`；非受影響有效合成案例仍保留研究覆蓋。

`ops/tests/test_j1_propline_h2h_identity_poison.py` 新增 7 項合成測試（2 正向、5 負向），分別測試重複有效主勝、重複無效主勝、重複 h2h market、缺 book key、顯示球隊與 side 相反及正常二書商案例。測試只採用不存在嘅 fixture event ID，同歷史固定時間；無外部 API 呼叫、密鑰或真實可成交價。

## 重要界線

本輪**唔會重算或覆蓋**已封存 `market/japan_free_status.json`；2026-11-22 16:43 HKT 存檔的 PropLine 7 場僅係當時舊演算法產生的研究性覆蓋數，**不能因為補丁通過就追認該 7 場都沒有污染**。必須等下一次獲授權的新資料在修正後演算法下重新獨立檢查。此 PR 不修改採集配額及日程，The Odds API 存檔所示 141 credit 是歷史餘額，不可視為目前可用額度。

全程 `status=RESEARCH_ONLY/HOLD`、`market_quotes_are_not_executable=true`、`production_recommendations=DISABLED`。不產生正 EV、ROI、下注金額或模型資格；而且 J1 1X2 覆蓋不能代替 WE League/HKJC 三向盤。

## 驗收

```bash
python -m compileall -q ops
python -m unittest discover -s ops/tests -q
```

需 exact-head CI 所有安全、壓力、ledger、validate、回歸全綠及獨立 reviewer。此為研究 Draft，未解除投注 HOLD；CI 通過只證明合成解析規則正確，不等於來源正式授權、報價真實或模型準確率改善。

# 足球王者｜The Odds API 日本 J1 原生身份及重複盤口隔離

**研究審查日期：2026-11-23（香港時間）；研究 Draft，正式預測建議 DISABLED / HOLD。**

## 獨立碼路審查發現

前面研究 PR #560（PropLine 同書商 1X2 side/market 重複）、#562（PropLine native 賽事 ID／bookmaker 身份重複）及 #564（跨 API 同場**雙向唯一**候選配對）已建立對應測試，仍然保持 Draft 未合併。但另一條已存在的 J1 來源路徑 `strict_fresh_odds_j1` 和 `odds_japan` 尚未具備同等品質閘門：

- `odds_japan` 原來未要求 The Odds API 來源 **`event.id` 是原生非空字串**，有兩筆相同 ID 仍將 `fresh_3way_event_count` 加兩次；同場兩個不同 ID 可以同時加兩次，而且後一筆會覆寫 dict 中嘅去水向量。
- `strict_fresh_odds_j1` 原來見到重複 `book.key` 只忽略後續已接受的 book，若第一筆無效、第二筆有效，更可能用第二筆。缺口唔只係「兩個 book 唔可以重覆計」，而係**同一原生 ID 有互相衝突版本時，全部同 ID 版本應拒絕**。
- shared `ops/odds_market.py:book_probabilities` 設計容許找到第一個可用 h2h market block 後返回；今次只在 J1 特殊入口明確拒絕一個 book 多個 h2h blocks，**不改其他六大聯賽舊解析與定時採集**。
- 舊 J1 入口未獨立核對每筆 odds event `sport_key`；如來源包含其他聯賽記錄，不可憑 outer sports catalogue 顯示 J1 active 就將其當 J1。

## 真正 RED → GREEN

先以 **SHA `26aad7f1`** 提交 `ops/tests/test_j1_odds_api_native_identity_quarantine.py`：15項無網絡合成測試，所有供應商請求都經函式 mock；兩組 GitHub regression 同樣顯示 **16個失敗子案例**，包括重複/空白/缺失/bool 事件 ID、重複 book、重複 H2H 區塊、跨聯賽範圍、相同場次兩個不同原生 IDs。16係報告的失敗子案例數，**不是16項獨立測試方法**。

其後只修改 `ops/japan_free_market.py` 內 The Odds API J1 入口：

1. 賽事批次預計數所有 `event.id` 及同場 normalized team IDs + kickoff；同一來源 ID / 同一場有多筆，無論其中一筆是否無效、完場或帶相反價，都**全部不計覆蓋**，不用先到先得。
2. 只接受明確屬於 J1 或沒有明確 sport_key 且其餘資料符合 J1 的事件；拒絕明確標示其他聯賽的事件；事件 ID 必須為有界、可見、非空字串，完成/獨贏 outright 的 event 不納入賽前覆蓋。
3. 每一場先計所有 source-native `book.key`；只採用**唯一**非空、有限長度、無首尾空白書商 ID，拒絕全部重複 ID 版本；要求一個 bookmaker **恰好一個 h2h market block**，然後才調用已存在的 `book_probabilities` 基礎價/時間守門。
4. 正常兩個不同 book 且來源 event 唯一，仍會產生 J1 **研究用**去水摘要；第三個有效 book 可在其中一個重複時提供第二個獨立 book。保留同一批其他不同賽事正常覆蓋。任何結構審核都唔等於市場可執行價。

## 不能越過的安全及資料界線

- 本 PR **#566 → #564 → #562 → #560 → main** 為研究 stacked Draft。未有獨立 reviewer；只修正 J1 The Odds API 解析器，無權限讀取/公開 GitHub Secrets、無真實 API call、無調整免費額度保護 `MIN_THE_ODDS_LEFT=220`，亦無改 scheduler、原始封存、模型權重或下注。
- `market/japan_free_status.json` 目前最近已保存的資料時刻為 **2026-11-23 09:41:41 UTC = 香港時間 17:41:41**。當時 PropLine 7場 J1 賽前覆蓋、The Odds API J1 HOLD、其存檔配額顯示141、跨 API 比較0。這是**舊 parser 下的覆蓋快照**，不能當成本 PR 修補後已重新檢查的真實賽事，更不是當前可成交賠率。無相關授權新資料、獨立時間戳或前瞻實測成績。
- `RESEARCH_ONLY/HOLD`、`production_recommendations=DISABLED`，無 certified forward case、無真實 EV/ROI 或準確率改善證據。

## 驗收指令

```bash
python -m compileall -q ops
python -m unittest discover -s ops/tests -q
```

最終結果以最新 HEAD GitHub regression ×2、safety 3.11/3.12、validate、stress、ledger 全部驗收與獨立審查為準，不以合成測試通過宣稱外部資料可信。

## 2026-11-23 追加審查：已暫停 1X2 市場不可算「新鮮覆蓋」

上游 J1 PropLine 分支會對 `suspended_at` 不為空的市場拒絕，但 The Odds API J1 `strict_fresh_odds_j1` 原本直接使用共用六大聯賽 `odds_market.book_probabilities`，而該共用函式不會檢查來源 row 顯式的 `suspended_at`。即使 `last_update` 少於20分鐘，有暫停標記的 H2H 仍可被計入研究覆蓋並影響去水共識。**這是本地程式對明確暫停標記的防禦性處理，並不聲稱 The Odds API 目前必定回傳此欄位。**

- **RED test-only SHA `796bef28`**：在既有測試文件新增4項離線合成測試，GitHub regression 回傳3項實際失敗：兩種非空 `suspended_at`、以及第三間已暫停 book 污染兩間健康 book 的共識；`suspended_at=null` 正常案例仍通過。原始測試日誌可於 [GitHub Actions](https://github.com/CHANCHUNWA1989/football-king-report/actions/runs/45154110837/job/137622591070) 核對。
- **GREEN 修正**：限定在 J1 `strict_fresh_odds_j1`，只接受一個 `h2h` 區塊且其 `suspended_at is None`，否則整間書商嘅 1X2 研究貢獻無效；兩間或以上仍有效的其他書商可保留原有研究覆蓋。未有對六大聯賽共用 parser 直接修改。
- 資料來源出現新 `suspended_at` schema 仍須依實際供應商合約和 feed 規範獨立核實；不能將純合成測試誤當為有真實可交易市場、前瞻封存或正EV。
- 本輪不觸發任何真實 HTTP/API 呼叫、不讀取密鑰、不更改配額，繼續 Draft／`HOLD`／`production_recommendations=DISABLED`。

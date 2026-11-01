# 即場比分／xG／賠率時序檢查（研究模式）

本工具係 `ops/live_quote_snapshot_guard.py`。目標係阻止「新比分 + 舊xG + 舊莊家報價」混合而產生假EV或錯誤即場判斷。**唔係即場數據採集器、唔係已校準模型、唔會輸出下注推薦。**

## 點運行

```bash
python ops/live_quote_snapshot_guard.py /path/to/authorized_live_snapshot.json
python -m unittest discover -s ops/tests -q
```

- `RESEARCH_ONLY`：同一場賽事嘅資料格式及時序檢查通過，**唔表示來源真實性、賠率可成交性、正EV或者命中率已獲認證**。
- `HOLD`：缺上游更新時間、來源或盤線；90秒以外嘅舊資料；跨場；VAR改判／入球／紅牌後尚未刷新xG或盤口；時間錯置，全部拒絕。
- 程式退出狀態：研究模式0，HOLD 2。執行時會自動改用目前UTC作決策時刻，禁止由JSON宣稱舊時間扮新資料。
- 完整輸出保持 `production_recommendations=DISABLED`、`certified_positive_ev=false`。公開輸出唔包含輸入嘅原始報價或其他個別來源資料。

## 輸入格式（合成例子，並非真實賽事）

```json
{
  "event_id": "synthetic-match-001",
  "kickoff_utc": "2026-10-31T08:00:00Z",
  "decision_utc": "2026-10-31T08:30:00Z",
  "score": {
    "event_id": "synthetic-match-001",
    "source": "sample-score-feed",
    "upstream_updated_utc": "2026-10-31T08:29:50Z",
    "captured_utc": "2026-10-31T08:29:52Z",
    "home_goals": 0,
    "away_goals": 0,
    "last_material_event_utc": "2026-10-31T08:00:00Z"
  },
  "stats": {
    "event_id": "synthetic-match-001",
    "source": "sample-stats-feed",
    "upstream_updated_utc": "2026-10-31T08:29:53Z",
    "captured_utc": "2026-10-31T08:29:55Z",
    "home_xg": 0.10,
    "away_xg": 0.30
  },
  "quote": {
    "event_id": "synthetic-match-001",
    "source": "sample-authorized-market",
    "upstream_updated_utc": "2026-10-31T08:29:56Z",
    "captured_utc": "2026-10-31T08:29:58Z",
    "bookmaker": "sample-book",
    "market": "totals",
    "selection": "over",
    "line": 2.25,
    "decimal_price": 1.91,
    "in_play": true
  }
}
```

上述例子係固定歷史合成時間，**今日執行CLI必然因為過期而HOLD**；單元測試會使用相對於當前UTC嘅合成時間。

## 各欄位含意與風控

1. `event_id` 需係來源一致、已核對嘅固定賽事ID；唔能以球隊中文名稱模糊拼對。
2. `upstream_updated_utc` 係**供應商自身發布／更新**時間；`captured_utc` 係擷取時間。爬蟲成功時間唔等於上游更新時間。任何時間未知都HOLD。
3. `score.last_material_event_utc` 由可追溯事件流提供，代表最近一次改變價格解讀嘅**入球、紅牌或VAR改判**；如開賽後尚無此類事件，用已核對 `kickoff_utc`。**唔可由比分頁嘅普通計時器刷新時間推算。** xG與盤口供應商更新時刻都須晚於或等於此欄位。
4. `market=totals` 配 `selection=over|under`；`market=asian_handicap` 配 `selection=home|away`。後者 `line` 係**已選球隊自身嘅帶正負號讓球線**；不准把三項讓球主客和混同亞洲兩項盤。
5. `decimal_price` 必須為十進制賠率；港式水位應先依法定義正確轉換。四分之一盤全贏／贏半／走盤／輸半／全輸仍需個別計算，**本工具不計EV**。
6. `source` 和 `bookmaker` 只檢查存在，不認證供應商身份、授權條款或可成交價格；呢啲需要獨立資料來源驗證及有界配額。
7. 因不同供應商有延遲，缺少可靠上游時刻嘅賽事會較多HOLD。唔可以任意提高容忍值或者捏造時間，換取較多表面可用結果。

## 真正仍欠缺

此工具只係獨立CLI及安全檢查，**未接入正式市場API、未接入模型或手機首頁**。想打通正式即場預測，仍需來源授權、可靠上游時間、同場盤口配對、真正可執行賠率、前瞻封存、樣本外校準及人手覆核。主系統維持 `HOLD/DISABLED`；任何「研究方向」都唔等於可以正式下注。

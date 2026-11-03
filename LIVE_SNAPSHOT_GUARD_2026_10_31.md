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


## 2026-11-03 增量：即場角球大小盤（Issue #401）

新增 `quote.market="corners_totals"`，`quote.selection="over"|"under"`，`quote.line` 為全場角球總數門檻（例如 8.5），不等於入球 `totals`。此研究模式不需要假造 xG；改由 `stats` 必須提供 `home_corners`、`away_corners` 兩個非負整數及 `last_corner_event_utc`。其他原有 `event_id`、上游更新／擷取時刻、比分、最新重大事件、莊家及盤線欄位全部照舊必填。

例如（僅列差異，沿用上面合成例子嘅其餘欄位）：

```json
{
  "stats": {
    "home_corners": 4,
    "away_corners": 4,
    "last_corner_event_utc": "2026-10-31T08:29:51Z"
  },
  "quote": {
    "market": "corners_totals",
    "selection": "over",
    "line": 8.5,
    "decimal_price": 1.90
  }
}
```

上面片段唔係完整可執行 JSON：要連同原例子 `stats`／`quote` 其餘來源及事件時間欄位使用，並以真實授權且可追溯資料取代合成值。

- 如角球總數為 0，`last_corner_event_utc` 必須等於已核對開波時刻；有角球時，必須有真實晚於開波嘅最新角球事件時間，**不可用普通計時器 heartbeat 代替**。
- `stats.upstream_updated_utc` 和 `quote.upstream_updated_utc` 必須都不早於最新角球事件；否則 `HOLD`。
- 如目前總角球已嚴格大於盤線，例如9角對全場8.5大小角，結果已決定，兩邊選項均 `HOLD`；不會當成研究正EV。
- 角球輸入嘅 `score.match_status` 必須由比分來源明確提供 `FIRST_HALF`、`HALF_TIME` 或 `SECOND_HALF` 其中一種；`FINISHED/FT`、`ABANDONED`、`SUSPENDED`、`NOT_STARTED`、`EXTRA_TIME`、`PENALTIES`、未知／缺值一律 `HOLD`。唔可以因 `quote.in_play=true` 就推斷賽事未完。
- 比分來源所聲稱嘅比賽階段亦要通過相對 `kickoff_utc` 嘅寬鬆時鐘合理性檢查：上半場不超過75分鐘、半場介乎35至100分鐘、下半場介乎40至150分鐘。呢啲係保守異常檢查，**唔係官方實際開球／完場時間認證**；延期開波或來源有疑問時會拒絕，不得調寬閘門硬湊可用資料。
- 任何角球總數缺失、布林／負數／非整數、事件時間不可信或來源超過 90 秒，均 `HOLD`。
- 這只是**資料格式及對時檢查**；即使回傳 `RESEARCH_ONLY`，都不會計算角球概率、證明實際莊家可成交價格或證明正EV，更不會解鎖 `DISABLED`。
- 這一個PR只處理角球輸入驗證，不擴充原有免費賠率配額、不接 live API、不動封存歷史預測、不觸發自動下注。真實同場同刻角球／盤口採樣與樣本外回測仍屬 Issue #401 未完成部分。


## 2026-11-03：角球市場來源身份綁定（第八階段／Issue #401）

角球市場新增一個獨立於即場資料本身嘅 `--fixture-manifest` 參數，用嚟對照**預先登記**嘅同場供應商 native fixture ID 和原件網址。上層 `event_id` 單靠一個字串相同並不足夠：比分、角球、賠率各有可能屬唔同供應商嘅同名賽事。

CLI 使用方法（以下為合成示例，唔係真實來源）：

```bash
python ops/live_quote_snapshot_guard.py synthetic_live_snapshot.json --fixture-manifest synthetic_fixture_manifest.json
```

先於開賽登記嘅 manifest 格式：

```json
{
  "event_id": "synthetic-fixture-123",
  "kickoff_utc": "2026-10-31T08:00:00Z",
  "registered_at_utc": "2026-10-31T07:40:00Z",
  "source_events": {
    "score": {
      "source": "sample-official",
      "source_event_id": "score-event-123",
      "source_url": "https://score.example.org/matches/123"
    },
    "stats": {
      "source": "sample-stats",
      "source_event_id": "stats-event-123",
      "source_url": "https://stats.example.org/fixtures/123"
    },
    "quote": {
      "source": "sample-licensed-odds",
      "source_event_id": "quote-event-123",
      "source_url": "https://odds.example.org/events/123"
    }
  }
}
```

即場 `score/stats/quote` 各來源紀錄亦要分別附上對應嘅 `source_event_id` 和 `source_url`（其餘即場時間戳、角球數與狀態欄位維持不變）。三個 channel 必須完全吻合 manifest 中嘅 `source`、原生 `source_event_id`、HTTPS `source_url`；比賽身份與開波時間亦必須吻合。聲稱預先登記嘅 `registered_at_utc` 必須較開波早至少10分鐘。缺 manifest 或欄位、跨場／換網址、非 HTTPS、賽後登記一律 `HOLD`。

**重要信任邊界**：上述 `registered_at_utc` 係提交者宣告，程式無法單靠 JSON 證明呢個 manifest 真係早於比賽存在，亦無法驗證供應商真偽、來源網站當時內容或賠率可成交性。單憑 HTTPS 及 native ID 格式一致，**並唔構成獨立認證**。正式投入真實資料前，需要將 manifest 同原始回應以可信、可審計嘅事前封存時間證據綁定；未做到則仍只有 `RESEARCH_ONLY`，`source_authenticity_verified=false`、`certified_positive_ev=false`、`production_recommendations=DISABLED`。

呢個增量只為 `corners_totals` 加強資料一致性；舊 `totals`／`asian_handicap` 驗證格式唔變。沒有增加免費 API 用量、沒有將賠率存入公開檔、沒有解鎖正式下注。

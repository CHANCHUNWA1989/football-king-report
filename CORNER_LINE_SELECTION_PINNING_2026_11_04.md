# 第十四階段｜同場同角球市場：鎖定指定盤線與方向選項（Issue #401）

## 根因：賽事ID及市場ID相同，不代表正在讀取同一投注選項

第十三階段 #419 已在預先簽章的 `source_events.quote` 綁定 `provider_market_id` 及 `market_period=REGULATION_FULL_TIME`，但同一場比賽全場角球可同時有8.5／9.5盤線；同一市場亦有Over／Under。以 `quote.market="corners_totals"`、`quote.selection="over"` 同埋自填 `line=8.5`，**不足以核實莊家實際報價對應嘅選項**。

本PR在可信封存 source-map 中增加**固定盤線**及原生方向選項ID；配對的 snapshot 少一個欄位、來源與方向／盤線不一致一律 HOLD。

### Manifest `source_events.quote`（增量欄位）

```json
{
  "source": "sample-licensed-odds",
  "source_event_id": "quote-event-123",
  "source_url": "https://odds.example.org/events/123",
  "provider_market_id": "corners-total-fulltime-123",
  "market_period": "REGULATION_FULL_TIME",
  "market_line": 8.5,
  "selection_ids": {
    "over": "corners-fulltime-over-8p5-123",
    "under": "corners-fulltime-under-8p5-123"
  }
}
```

**所有值純屬合成例子**，不能當成真實莊家市場ID、當時可成交盤口。場次開波前要有獨立可信 source-map 同真實授權供應商的 ID，無法取得則 HOLD。

相應 snapshot `quote` 必須提供：
- `market="corners_totals"`、`market_period="REGULATION_FULL_TIME"`、`provider_market_id`；
- `selection="over"` 或 `selection="under"`，以及與該方向所綁定的 `provider_selection_id`；
- `line` 必須恰等於 manifest 已封存的 `market_line`，且為合法四分之一盤線；
- 原本 `decimal_price`、`bookmaker`、`upstream_updated_utc`、`captured_utc`、角球時間及賽事身份等欄位維持必填及原有安全閘門。

例如本次研究只封存全場8.5角盤線：如果即場變9.5，必須保持 `HOLD`，唔會自動把8.5 的賽前原生選項ID套到9.5。要覆蓋其他盤線，需要獨立合法來源證據及新嘅研究對照程序；**唔得事後重寫已簽署 manifest 來「修正」選項ID**。

## 信任限制

- 原生 `provider_selection_id` 係綁定使用者提交嘅賽前對照資料；**尚未獨立驗證**供應商是否真有該 ID、該時刻報價是否仍有效、該價格能否成交。
- 盤線及方向綁定只能降低內部錯配，唔代表可以認證特定 `@1.90` 價格；仍需原始報價時間戳、授權供應商回應及不可抵賴快照驗證。
- 只為 `corners_totals` 研究新增欄位；原本 `totals`／`asian_handicap` 的資料格式不變。合成測試唔等於真實回測。
- `production_recommendations=DISABLED`、`certified_positive_ev=False`、正式投注 HOLD 維持。
- 研究分支依賴 #403 → #406 → #408 → #411 → #414 → #417 → #419；未獨立審核完成之前唔合併主分支。

## 驗證

```bash
python -m compileall -q ops
python -m unittest discover -s ops/tests -q
```

新增負向測試涵蓋「同場不同角球盤線」、「Over/Under 原生ID對調」、「缺少／相同選項 ID」、「非法固定盤線」、「bridge 冒充全場8.5但實際提供9.5」，另有匹配 Under 方向及原有 live settlement 正向回歸。

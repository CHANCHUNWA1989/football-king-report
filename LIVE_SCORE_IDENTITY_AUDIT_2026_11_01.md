# 即場比分賽事身份防混淆｜2026-11-01

## 已重現的真實風險

2026-10-31 晚間查「曼城對白禮頓」時，公開比分網站的同名頁面曾顯示 **Women's Super League** 的 **Manchester City Women 3–2 Brighton Women，2026-10-18**，而本次研究查詢目標其實係 **2026-10-31 英超男子曼城對白禮頓**。只用中文／英文球會名稱配對，就會將錯誤賽果污染今晚原始 43 場研究覆盤。

此PR只做一件獨立工作：新增 **零網絡、研究專用** `ops/live_score_identity_guard.py`，拒絕賽事來源身份錯誤。**未接入現有定時排程或正式模型，沒有本PR創建任何新預測。**

## 校驗規則

- 必須提前記錄原始賽事身份：性別、聯賽、主客固定隊伍ID、UTC開賽時間、至少兩個來源各自嘅固定賽事ID同完整HTTPS賽事URL；封存時刻必須早於開球至少10分鐘。
- 即場兩個獨立供應商名稱不能重複；同場來源必須吻合已封存固定賽事ID、URL、性別、聯賽、主客隊同開賽時間（容差三分鐘）。
- 擷取時間同來源更新時間都必須清楚標註UTC，不能超過10分鐘、不能來自將來、不能早於身份封存。
- 「FINISHED」至少要喺開波90分鐘後，而且各來源必須同時回報 **同一狀態同一比分**。一個仍在進行、一個寫完場，一律HOLD。
- 女子賽事撞名、舊比分、賽事日期錯、同源重複、網址轉到另一場、真假布林分數等都拒絕。

## 仍然存在的限制

1. 兩個來源嘅聲稱吻合不代表網站被真正認證，亦不證明兩個上游資料鏈彼此獨立；`independently_authenticated=false`、`settlement_certified=false`、`model_scoring_eligible=false`，只能輸出 `RESEARCH_ONLY`。
2. 此工具只核對**上游已提供**來源數據；未自行取得即場直播、官方賽果、官方正選，亦未建立歷史資料樣本及校準模型。
3. 源網址與封存時間戳必須在實際採集系統另行提供真實可驗證證據；填入聲稱值不等於已通過來源身份核實。
4. 不能因呢個工具嘅合成測試通過，就聲稱模型命中率、Brier、EV、ROI已改善。正式推薦繼續 `DISABLED/HOLD`。

## 驗收與證據

- 實際錯誤查詢頁（女子賽事，2026-10-18）：https://www.sofascore.com/football/match/brighton-manchester-city/idhbsBCgc
- 正確男子賽事來源：https://www.fotmob.com/en-GB/matches/manchester-city-vs-brighton-hove-albion/2vnwg2 及 https://www.skysports.com/football/manchester-city-vs-brighton-and-hove-albion/live/559531
- 新增24項合成測試，包括成功研究性匹配與性別、ID、時間、來源衝突等負向用例。

```bash
python -m unittest discover -s ops/tests -p 'test_live_score_identity_guard.py' -q
python -m compileall -q ops
python -m unittest discover -s ops/tests -q
```

測試／CI通過只證明指定程式安全行為；實際接入、來源認證同樣本外準確率係另外獨立工單。

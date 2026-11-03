# 歐冠角球／上半場入球：同莊家完整盤口檢驗（研究用途）

本階段只處理 2026-11-03 UEFA 歐冠四場研究名單中兩個**特殊市場**：
- 飛燕諾 vs 國際米蘭：全場角球 Over/Under 9.0
- 巴塞隆拿 vs 阿士東維拉：上半場入球 Over/Under 1.75

依賴前階段 [PR #385](https://github.com/CHANCHUNWA1989/football-king-report/pull/385) 之賽事 request ID 和盤口身份。一般 1X2、亞洲讓球和全場大小球之完整來源盤口另有 [PR #379](https://github.com/CHANCHUNWA1989/football-king-report/pull/379)；本改動**不取代**或合併該 PR。

## 功能

`ops/ucl_special_market_pair_gate.py` 是離線、防錯、零 API 用量的輸入邊界。輸入由另行授權的來源私下提供。每個原始觀察 block 只容許一個 case、同一 provider fixture ID、同一 bookmaker、同一 market、相同觀察時間，及剛好一對 Over/Under 同盤線、合法十進制賠率；不能跨原始 block 拼接兩邊。此檢查**不會下載、登入或從未經授權網站擷取報價**。

每個 block 要求欄位：
- `case_id`, `provider`, `provider_event_id`, `bookmaker_id`
- `fixture`: `home`, `away`, `kickoff_utc`
- `market_id`, `market_updated_utc`, `captured_utc`
- `outcomes`: 兩條 `{selection: OVER/UNDER, line, decimal_odds}`

確認嚴格時序：market 更新不遲於取得時間、取得不遲於 `now`、`now` 早於開賽至少 10 分鐘、market 更新和擷取兩者距離目前均不超過120秒；時間必須帶時區。任何布林數字、未支援市場、不同盤線、缺邊、雙重同邊、重複同 case／莊家、跨 case 複用同 provider native ID、未知欄位與無法確認之時間均 fail closed。

**注意：**
- `provider_event_id`、bookmaker ID、market 時間都係傳入資料嘅**聲稱**；格式正確不等於第三方獨立確認或有權轉載。
- 正式 UEFA fixture 身份、來源授權、實際可成交價、跨來源真正獨立性、正選資料、角球/半場樣本外校準並未由本模組證實。
- 報告刻意不輸出原始賠率、bookmaker ID、provider event ID、來源識別值或用戶提供欄位。
- 即使合規 block 結構完整，狀態仍然係 `HOLD`；`bets_authorized=0`、`production_recommendations=DISABLED`；不會產生概率、推介、下注注碼或正EV聲稱。
- 此模組**不覆蓋正常六聯賽系統**，亦不改動任何封存 A/B/C 預測或 GitHub Pages。

## 驗證方法

```bash
python -m compileall -q ops
python -m unittest discover -s ops/tests -p 'test_ucl_special_market_pair_gate.py' -v
python -m unittest discover -s ops/tests -q
```

新測試覆蓋一對與兩對合成正向案例及大量負向案例（混 book、線錯、重複同邊、舊時刻、錯開賽、布林 odds、來源身份矛盾、惡意/無法 hash 嘅輸入等）。**合成測試過關只代表程式行為，唔代表真實數據到位、預測命中率或盈利能力提高。**

## 下一項外部依賴

合法、可追溯的角球及半場盤口同時提供完整雙邊；來源觀察是否真係同一次 provider response 及同一 event，仍需要獨立原件/授權審查。之後先可收集兩種市場的歷史現場觀察、前瞻獨立對照、校準，再討論正EV。PR #385 先通過獨立審查並合併後，呢個堆疊 PR 才可安全評估合併；不可因 CI 通過就自動升級為正式投注。


## 下一階段整合檢查（2026-11-03）

同一個堆疊 PR 將兩個研究元件真正接駁，避免單條 special-market quote 應被標記為「結構合格」：
- `ops/ucl_four_market_shadow.analyze(special_market_blocks=...)` 會使用此 atomic gate 的完整雙邊驗證結果，並於四場報告輸出每場 `quote_status` 與總 `special_market_atomic_pairs`。
- **單邊報價不算完整盤口**；只提供舊 `quotes` 單條資料時，角球/半場標記 `SPECIAL_REQUIRES_ATOMIC_PAIR`，冇任何符合條件 block 時標記 `MISSING_ATOMIC_PAIR`。
- 通過完整 pair 之後狀態只係 `SPECIAL_ATOMIC_PAIR_SOURCE_UNAUTHENTICATED`，全局依然 `HOLD`；所有報價、供應商原始ID及莊家ID都不會經由四場報告公開。
- 相同 native event ID 只會喺**同一 provider 名稱空間**之內做跨 case 衝突判定，唔再將不同 provider 嘅相同字串誤判成衝突。
- 額外回歸：強制一邊配對失敗、post-kickoff HOLD、跨 provider ID 共享、超大整數讓球線失效時安全拒絕。
- 仍然沿用 PR #385 唯一四場 `CASES` 資料；冇新增第二份手寫賽事ID清單，亦唔接通 API 或重算模型。

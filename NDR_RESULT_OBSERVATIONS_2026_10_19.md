# NDR 逐場比分觀察（2026-10-19）

現有外部網頁 probe 只搜尋附近隊名和形似比分的文字。同一行的開波時間 `20:30`、顯示比分 `1:0`、半場 `(0:0)` 可以一併出現；這些 token 原本已標示未核實，不能作正式賽果。

新增 `ops/ndr_result_observations.py` 從既有 NDR 原始 HTML 擷取同一個 Bundesliga 球季 results table、同一個賽事 row 的觀察。固定賽事及主客隊來源 ID、日期、顯示比分各自保留，半場及時間不混入比分；缺身份、結構矛盾、重複 ID、來源路徑或原始位元組不符均拒收。日期來自明確球季及日月，沒有替來源假造 UTC 開波時刻。

每天四模型研究流程及 PR 即時來源檢查，會重用既有外部來源擷取結果，執行解析並封存 `ndr_result_observations.json`，不增加 HTTP 請求。報告使用獨立觀察 schema，不送入原有賽果驗證、模型計分或結算輸入。

`finalresult` CSS 名稱本身不能證明 90 分鐘已完場。HTTPS 網址和雜湊亦不能認證來源、抓取時刻或出版社上游獨立性。所有輸出保留 `HOLD`、`independently_verified=false`、`eligible_for_model_scoring=false`、`production_recommendations=DISABLED`。此更改沒有增加合資格賽果，亦未證實提高預測表現。

下一步須核對固定賽事詳細頁的明確完場／比賽時段、固定身份及來源關係，再建立可信擷取和獨立賽果驗證鏈；不得把兩個網站名字或相同比分當成獨立認證。

```bash
python -m compileall -q ops
python -m unittest discover -s ops/tests -q
python ops/ndr_result_observations.py --raw-dir /path/to/external_raw --output /tmp/ndr_result_observations.json
```

## 本輪實測

2026-10-19T02:57:33.076502+00:00 的既有 collector 實際擷取，DFB 及 NDR 均回覆 HTTP 200。NDR 原始 285,586 bytes，SHA256 `6b2dc11dc72f5bcd9468102967ff93feb5444d137eedcfbfa9ed6b0563358e12`；從 9 行得到 7 行未核實觀察，2 行缺球隊固定來源 ID 而隔離。來源賽事 `5884` 讀得顯示比分 1:0、半場 0:0；20:30 沒有混作比分。這是當次實際輸出，往後場數隨來源改變，不能以此宣稱任何賽果已獲獨立認證。

驗收：先建立測試重現缺少嚴格解析器，再完成 22 項新正反例測試；完整 ops 1,328 項、compileall、兩條 workflow 共44個 shell步驟語法檢查通過。獨立助理覆核了最後程式、測試及流程。這些驗收只支持工程行為，不代表命中率提升。

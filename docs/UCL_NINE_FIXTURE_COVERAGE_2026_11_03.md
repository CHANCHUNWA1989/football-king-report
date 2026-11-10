# 2026-11-03 歐冠9場賽前完整性檢查（研究用途）

**研究批次：** 2026/27 UEFA Champions League 聯賽階段 Matchday 4，歐洲日期 2026-11-03。

官方賽程：[UEFA 2026/27 league-phase fixtures](https://www.uefa.com/uefachampionsleague/news/02a8-2174c9e9019d-f909a77bd77a-1000--2026-27-champions-league-all-the-league-phase-f/)；附加賽程交叉核對：[Bundesliga Champions League Matchday](https://www.bundesliga.com/en/champions-league/matchday)。UEFA 所列 18:45 CET／21:00 CET 對應 17:45 UTC／20:00 UTC（香港 +08:00：**11月4日01:45／04:00**）。

| 香港時間（11月4日） | 比賽 | 原生 provider fixture ID |
| --- | --- | --- |
| 01:45 | 薩克達 vs 士砵亭 | 未驗證 |
| 01:45 | 加拉塔沙雷 vs 史特加 | 未驗證 |
| 04:00 | 馬德里體育會 vs 拜仁慕尼黑 | 未驗證 |
| 04:00 | 巴塞隆拿 vs 阿士東維拉 | 未驗證 |
| 04:00 | 飛燕諾 vs 國際米蘭 | 未驗證 |
| 04:00 | 波杜基林特 vs 里爾 | 未驗證 |
| 04:00 | LASK vs 施洛雲 | 未驗證 |
| 04:00 | 曼聯 vs 羅馬 | 未驗證 |
| 04:00 | 維拉利爾 vs 巴黎聖日耳門 | 未驗證 |

只有賽程、日期、球隊配對經公開賽程核實。**任何本地 `local_request_id` 都不是 UEFA / The Odds API 原生賽事 ID。** 先前 [四場 UCL 研究 PR #385](https://github.com/CHANCHUNWA1989/football-king-report/pull/385) 的4個本地 case ID 在本manifest沿用，避免後續 join 產生兩套識別；該 PR 及其下一層 [#386](https://github.com/CHANCHUNWA1989/football-king-report/pull/386) 未合併時，此新 gate 仍獨立於 main。

## 重現的真實覆蓋缺口

`market/latest.json`（2026-11-03 01:59:39 UTC 的已核實 GitHub 快照）：
- 共91個公開 **h2h 去水共識研究賽事**，範圍為英超、英冠、德甲、西甲、意甲、法甲；
- 無 UEFA 歐冠聯賽源事件；不可以用其他聯賽同名球隊或中文別名推斷 UCL 比賽；
- `missing_markets` 列出 `spreads`、`totals`；公開快照唔包括可成交原始莊家報價，更冇角球及上半場入球資料；
- 故此本批次 **9/9 均為 HOLD，0場有可信可執行盤口或正EV資格**。0/9是對該份已檢視快照的結論，並非聲稱所有供應商都沒有歐冠資料。

另一份 `market/private_summary_latest.json` 係**匿名計數**，不足以逐場綁定盤口或證明可成交價；不能把其中數千條研究記錄搬來當9場有盤口。

## 新增零配額 Gate

`config/ucl_md4_2026_11_03_nine_fixtures.json`：只保存官方可核實賽程及9個本地研究 request ID。拒絕多場、漏場、重複、錯時區、非嚴格 2+7 時間表及冒稱官方原生ID。

`ops/ucl_md4_nine_fixture_coverage.py`：輸入只用既有公開去水快照，預設**不提供任何 provider binding**；絕不因姓名相似自行配對。日後如獲合法原生ID，可另行提供私有 `bindings` 檔案，同時檢查完全相同的事件ID、競賽 sport key、主客身份、開賽UTC、資料先後、更新時效，並拒絕同ID多場及重複聲稱。就算成功連到同一條去水 h2h 資料，亦只代表 **structural public consensus observation**，不認證報價來源／可成交價／EV。

### 最新風險修正：快照時效 ≠ 盤口時效（2026-11-03）

新測試重現：`as_of_utc` 距離審核時刻1小時，雖然仍在公開快照容許嘅2小時內；`market_last_update_utc` 只比該快照早15秒，但相對真正審核時刻已舊1小時。舊程式誤計算成「新鮮 h2h 結構觀察」（CI 已重現紅燈），修正後拒絕並加入 `STALE_PUBLIC_MARKET_UPDATE` 阻塞原因。

**兩個不同時效閘門必須同時通過：** 快照產生時間距離審核當刻不超過7200秒，並且莊家市場更新時間距離**審核當刻**不超過120秒；等於120秒可通過結構檢查，但一律維持 `HOLD`，不代表實際可成交報價或有效 EV。測試連同原本錯時區、錯聯賽及跨聯賽重複ID案例一起跑完整 CI。

輸出每場必含：
- 本地 request ID、隊名、UTC及香港開波時間；
- 唯一整體 `HOLD` 狀態；
- `public_h2h_structural_observation` / `provider_identity_independently_verified=false`；
- `blockers` 詳列是否欠原生ID、UCL source snapshot、完整盤口、獨立校準、被實際模型使用的正式正選、獨立簽核；
- 所有案例 `bets_authorized=0`，全局 `production_recommendations=DISABLED`。

**公眾報告不回傳**原生事件ID、原始賠率、博彩公司名稱、概率數值、API Key 或私有 binding。無外部 API 呼叫、無 Secrets 讀取、無付費升級、無正式預測模型改動、無 A/B/C 封存重算。

## 本地及 CI 運行

```bash
python -m compileall -q ops
python -m unittest discover -s ops/tests -p 'test_ucl_md4_nine_fixture_coverage.py' -v
python -m unittest discover -s ops/tests -q
python ops/ucl_md4_nine_fixture_coverage.py --output artifacts/ucl_md4_nine_coverage.json
```

GitHub Actions `ucl-nine-fixture-coverage.yml` 會跑全部測試，再用當時 GitHub repo 快照產生**無私人報價**之 JSON 診斷檔並上傳 14 日保留的 artifacts（不寫進 live 頁面）。新測試覆蓋：9場缺原生ID、國內聯賽冒充歐冠、假 full-market claims、缺或重複 binding、跨事件同ID、多源混線、錯主客、過期/未來快照、完場後不能新增賽前證據、數值溢出、公開輸出無機密資訊。

### 下一個外部依賴

只有先取得合法供應商對當季歐冠嘅賽事ID及授權，再取得具原始時刻的完整市場雙邊、獨立校準預測及已確認被模型採用的正式正選，先有條件進入真正賽前評估。**測試成功只代表 fail-closed 行為，唔代表有9場可信勝率或提高命中率。**

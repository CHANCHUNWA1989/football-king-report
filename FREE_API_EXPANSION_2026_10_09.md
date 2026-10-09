# 足球王者 V4.1｜額外四個免費 API 來源（2026-10-09）

## 新增的 4 個供應商、5 個 read-only 端點

| 來源 | API | 免費條件 | 實際工作 | 當前安全狀態 |
|---|---|---|---|---|
| [Open-Meteo](https://open-meteo.com/en/terms) | [Forecast API](https://open-meteo.com/en/docs) | 無 Key，免費只限非商業用途；每日至少須低於官方 10,000 次限制；CC BY 4.0 署名 | 每天只用 **1 個批次請求**，查六個已存在德甲主場城市**市中心**天氣，與 MET Norway 的天氣背景分開儲存 | RESEARCH_ONLY / HOLD，並非球場實況或獨立氣象模式 |
| Open-Meteo | [Historical Weather API](https://open-meteo.com/en/docs/historical-weather-api) | 同上 | 每週最多 1 次查詢，慕尼黑約 10–12 日之前歷史天氣；只供資料品質研究 | 過去重分析結果不是賽前可用資料，禁止回填預測 |
| [Meteostat](https://dev.meteostat.net/api) | [Historical Point Daily](https://dev.meteostat.net/api/point/daily.html) | RapidAPI Basic **每月 500 次**，須個人 API Key 和遵守協議；CC BY 署名 Meteostat 及原始機構 | 每週最多 1 次查慕尼黑歷史每日氣象，**model=false** 防止用預估值冒充觀測 | 未設 Key 時 NOT_CONFIGURED，觀測亦有賽後資料延遲 |
| [Wikidata](https://www.wikidata.org/wiki/Wikidata:Data_access) | [SPARQL Query Service](https://www.mediawiki.org/wiki/Wikidata_query_service/User_Manual) | 無 Key、共享 Wikimedia 公共資源；嚴禁大量查詢／忽略 429 | 每週最多 1 個針對 6 個已知球場英文全名的固定小查詢，只存座標目錄項目數 | 不自動將地點當作任意比賽的真實舉辦球場 |
| [ScoreBat](https://www.scorebat.com/video-api/docs/) | Free Feed V3 | 免費受限精華、需個人 Token；每次 API 請求計約 5 quota requests；需按其展示條款使用內容 | 每週最多 1 次只核實精華數量，不保存視頻/iframe/源比賽檔 | 只改善媒體資料，不能補即時傷停/正選/賠率 |

每週最大全套請求量 **5 次**（有齊兩個私人金鑰時），平日 **1 次**；沒有金鑰時星期一最大 **3 次**。GitHub Actions 有可能因調度延遲，並不是即時 feed。這些都不是 Google Play / 公司正式商用的免費永久授權承諾。若系統轉商業用途，先審查每個供應商的授權，尤其 Open-Meteo 公共免費層。

### GitHub 接駁

- 程式：`ops/additional_free_apis.py`
- 合成測試：`ops/tests/test_additional_free_apis.py`
- 工作流程：`.github/workflows/football-king-additional-free-apis.yml`
- 每日香港時間約 10:31 自動執行，逢星期一額外查閱 4 類背景研究；可以手動 Run workflow 勾選 `background`。
- 只上傳去 GitHub Actions 的 `football-king-five-free-api-research` 派生狀態工件；不自動發布來源原始內容、不影響現有網站文件、主 1X2 市場、歷史封存、EV、ROI 或投注資格。
- 密鑰只可由用戶本人放入 [GitHub Actions Repository Secrets](https://github.com/CHANCHUNWA1989/football-king-report/settings/secrets/actions)，**不要在聊天中傳送**：
  - `METEOSTAT_RAPIDAPI_KEY`（RapidAPI 免費 Basic）
  - `SCOREBAT_FREE_TOKEN`（ScoreBat Free Feed）
- 沒有密鑰的供應商標 `NOT_CONFIGURED`、不發請求；429/401/403 只標 `HOLD`、不自動重試；最多 900 KB JSON 回應，固定官方 URL、禁用 redirect。
- 第三方公開資料的上游來源未驗證獨立性，**不會**聲稱增加獨立投注市場或提高勝率。

### 真正仍需解決的預測缺陷

1. 各來源的上游資料可能重複，即使來源網站不同，亦不代表新的**獨立**訊息。
2. 免費來源並不提供可靠而全面的當季傷停、預計正選、實際可買博彩公司 1X2 市場，切勿做虛假補值。
3. 氣象或球場地理對結果的**獨立樣本外增量價值**尚待先行 Shadow Mode A/B 驗證；真正加入模型須遵循 point-in-time、source provenance、Brier/Log Loss、樣本外時序與聯賽分組驗證。
4. 額外 API 只是備援與研究，不是放行正式投注；`production_recommendations` 永遠 `DISABLED`。

如有實際供應商測試流程成功，仍需閱讀每個 provider 的 `status` 和 `reason`：**GitHub Action 成功只代表沒有程式錯誤，不代表所有 API 都取得可用資料。**

# 剩餘API接駁｜Sportmonks 免費蘇超／丹麥超賽程

**2026-10-31 研究安全版本**。此更新解決先前只向 Sportmonks 查聯賽ID、無法得到真正賽事資料嘅缺口。未設定個人 `SPORTMONKS_API_TOKEN` 時，供應商不會被呼叫。

## 已接入流程

現有 `.github/workflows/football-king-secondary-sources.yml` 每日跑 `ops/secondary_sources.py`。有合法免費 Token 時，會另外嘗試兩個請求：

- `GET https://api.sportmonks.com/v3/football/fixtures/date/YYYY-MM-DD?include=participants&filters=fixtureLeagues:271,501`，今天（UTC）
- 同一端點，明天（UTC）

官方文檔：[Fixtures by Date](https://docs.sportmonks.com/v3/endpoints-and-entities/endpoints/fixtures/get-fixtures-by-date)、[Participants](https://docs.sportmonks.com/v3/tutorials-and-guides/tutorials/includes/participants)。

只查免費丹麥 Superliga（271）及蘇格蘭 Premiership（501）；限兩個請求、最多12筆縮減樣本、拒絕其他聯賽。Token 只經 HTTP `Authorization` 請求標頭傳送，不放入URL、不打印、不保存。

## 安全欄位

經 `ops/sportmonks_free_fixture_adapter.py` 處理後，只保留 `league`、`provider_event_id`、`home`、`away`、`kickoff_utc`、`status` 六個研究欄位。主客根據 `participants[].meta.location` 分辨；開波必須有真實 `starting_at_timestamp`；缺時區或錯日期不猜測。

這些樣本放在 `sources/latest.json` 的 `sportmonks` provider 下 `free_fixture_samples`，**分開於原有六大聯賽 `sampled_fixtures`**，防止失真提高六大聯賽來源核實比例。缺最後比分就不認證結果，無亞洲讓球／大小盤報價，不能成為正式推薦。

免費方案/授權是否真正可獲得當季賽事，**要等你本人完成帳戶免費 Token 設定後由GitHub Actions實測，唔會用合成數據冒充真實連線。** 參考官方 [Sportmonks Free Plan](https://www.sportmonks.com/football-api/free-plan/)。

## 如要完成API供應商認證

1. 到 [Sportmonks 官方免費方案](https://www.sportmonks.com/football-api/free-plan/) 註冊／登入免費戶口。
2. 到你嘅 GitHub [Repository Actions Secrets](https://github.com/CHANCHUNWA1989/football-king-report/settings/secrets/actions)，新增 `SPORTMONKS_API_TOKEN`；**絕對唔好喺公開倉庫或聊天貼 Token**。
3. 到 [現有免費來源採集Workflow](https://github.com/CHANCHUNWA1989/football-king-report/actions/workflows/football-king-secondary-sources.yml) 按 Run workflow；檢查 Safe Status、嘗試次數、`free_fixture_count`。
4. 若取得 `NO_FIXTURES_RETURNED`，表示當時無有效資料，**唔係已通過賽事驗證**。`HOLD` 則代表資料／權限錯誤，唔可以放行模型。

## 其他仍未完成連線嘅API

- `FOOTBALL_DATA_ORG_TOKEN`（football-data.org）：程式與Workflow已存在，待本人申請免費Key；免費比分可能延遲。
- `OPENFOOT_API_KEY`：研究來源Workflow已存在，待本人申請；免費賽程非商業可成交賠率。
- `THERUNDOWN_API_KEY`：日職研究接駁等待Key；不得繞過供應商方案。
- `BSD_FREE_API_TOKEN`：已記錄有Key，但上次採集0條可比較市場，唔等於未接線。
- `API_FOOTBALL_KEY`：已有Key，2026/27現季 Free 仍被限制；不會盲目增加付費請求。
- `PROPLINE_API_KEY`：日職來源曾見 HTTP 200 但超大回應而 HOLD，需要另外處理供應商回應，不代表有可用盤口。

呢份改動只補 **Sportmonks 賽程讀取能力**，不聲稱所有供應商已取得Token／真正取得當季資料，更不開啟正式投注建議；全局 `production_recommendations=DISABLED` 保持不變。

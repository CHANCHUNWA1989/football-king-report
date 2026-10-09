# 足球王者｜免費 API 覆蓋缺口與負載審核（2026-10-09）

## 實際壓力測試與界線

- `ops/stress_test.py` 是離線、固定時鐘、零金鑰及零外部網絡合成負載測試。
- 測試 1,500 場六聯賽合成賽前模型配對、排名、至少 1,500 個畸形 bookmaker payload、24 次並行相同模型配對，以及 350 個已結算合成樣本的前瞻評估。
- 由 GitHub CI 每個修改 PR 和主分支執行，結果在 `football-king-offline-stress` artifact；若效能或安全斷言不通過，job 失敗。
- 上述結果**不是**供應商壓測、即時接駁延遲、公開網站吞吐量、模型準確率或盈利證明；不會用多 IP／代理對免費上游做壓力測試。
- 所有合成資料禁止進入預測封存。

## 真正值得補充的來源（經官方條款初步篩選）

| 資料來源 | 2026 官方聲稱的 $0 使用方式 | 可能填補 | 本系統狀態 | 不能聲稱 |
|---|---|---|---|---|
| [5DollarFootballAPI](https://5dollarfootballapi.com/pricing) | Free 五大聯賽、60 次／小時，單場 Bet365 1X2；需要免費私人 Key；公開產品需連結署名 | The Odds API 免費額度不足時的**獨立單一博彩公司研究觀察** | 新 `ops/five_dollar_free.py` + 每日最多3次請求流程；沒有 Key 時 0 次 | 非跨多博彩公司共識；開/收市價沒有完整賽前時點，不能冒充可執行 EV 或直接備援推薦 |
| [SportScore](https://sportscore.com/developers/terms/) | 免 Key；約 10,000 次／日／IP；公開資料使用畫面必須帶真實可見 dofollow 「Powered by SportScore」連結 | 額外比賽源供觀察及日後對照 | 新 `ops/sportscore_probe.py` + 每日兩次最多各 1 次公開來源只讀查核；不在網站轉載任何來源資料 | 未經真實賽事聯賽、UTC 開賽及賽果核實，不作自動結算或代替市場 |
| [football-data.org](https://www.football-data.org/) | 需免費 Token，10 次／分鐘；部分賽事與即時資料限制 | 賽程、正式賽果交叉核對 | **原有接駁已存在**，缺 Token | 無可保證的免費 1X2 原始博彩公司報價 |
| [OpenFootAPI](https://openfootapi.com/pricing) | 需免費 Key，月配額依方案 | 補當季賽程、比分 | **原有接駁已存在**，缺 Key | 不可假稱免費開放收費 xG、衍生 odds |
| [BSD](https://sports.bzzoiro.com/docs/api-license/) | 需免費 Token，授權限制見官方 | 獨立共識報價及研究資料 | **原有接駁已存在**，缺 Token | 共識不是可執行個別報價 |
| [Open-Meteo](https://open-meteo.com/en/terms) | 免 Key，非商用，最多 10,000 次／日，CC BY 4.0 署名 | MET Norway 天氣來源的獨立研究交叉核對 | 候選：需球場精確座標、同一時點及非商業使用條款再驗證 | 天氣唔係投注優勢，並非賽事即時情報 |
| [Wyscout 開放事件](https://figshare.com/collections/Soccer_match_event_dataset/4415000) | 2017/18 多聯賽歷史事件，CC BY 4.0 署名 | 離線 xG／事件特徵研究 | 待 Shadow Mode 時段分割、樣本外增量驗證 | 不能用歷史 2018 資料當 2026 即時狀態 |
| [Metrica Sample](https://github.com/metrica-sports/sample-data) | 3 場匿名追蹤與事件示例 | 事件/空間特徵解析器單元研究 | 僅候選，不足訓練全面六聯賽模型 | 不是 2026 球隊資料，且需遵守公開署名條款 |

## 不應盲目追加

- [SportDB.dev](https://sportdb.dev/tos.html)：條款寫免費服務屬試用，正式生產需付費；官網免費請求宣傳與條款數字亦有差異，暫不作可靠常駐備援。
- [Sportradar](https://developer.sportradar.com/soccer/docs/soccer-ig-account-maintenance)：通常以免費**試用**申請，唔可以當永久免費。
- ESPN 非公開網站內部 API、受限制爬蟲、以及無清晰授權之重包裝博彩報價：不列入正式數據來源。
- 同一個上游資料的不同轉售鏡像不構成真正獨立驗證；須比較事件 ID、原始供應商、比分延遲、歷史修正與資料時點。

## 目前最關鍵未解決問題

1. **沒有足夠獨立合法可買 1X2 實盤，故不能真實計算正 EV/ROI**；單一書商報價只能研究，不能偷換多書商共識。
2. **傷停和預計正選通常唔保證免費現季足夠覆蓋**；沒有資料應顯示 `UNKNOWN` 而非補假數據。
3. **賠率來源可能同源/過期**；原始快照與模型時點要先核對。
4. **結果樣本欠缺獨立一致性與跨賽季前瞻驗證**；需至少 300 個已結算有效樣本、12 個週次分組和概率校準。
5. **GitHub Actions cron 非秒級直播**；必須明確顯示最後資料擷取、更新時間及備援狀態。

## 安全規則

- 所有新供應商都留喺獨立研究觀察，**絕不自動寫入舊預測、正式賠率或任何投注功能**。
- 上游不足、未知格式、連接失敗、429 或無 Key => `HOLD`／`PARTIAL`／`NOT_CONFIGURED`；真實配額絕不因壓測而耗盡。
- 如要啟動 5DollarFootballAPI：到 [GitHub Actions Secrets](https://github.com/CHANCHUNWA1989/football-king-report/settings/secrets/actions) 設 `FIVEDOLLAR_FOOTBALL_API_KEY`。不要在聊天傳送 Key。
- 使用 SportScore 資料於公開手機網站前，必須先根據官方要求加入可見且可索引的 `Powered by SportScore` 來源連結。現在只發布 GitHub Actions 衍生計數工件。

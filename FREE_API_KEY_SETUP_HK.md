# 足球王者 V4.1｜免費足球 API Key 申請及 GitHub 自動接駁（iPhone 版）

**[最新真實免費 API 設定及權限狀態](FREE_API_PROGRESS_2026_10_09.md)**

**重要更正（2026-10-09）**：`API_FOOTBALL_KEY` **已設定**，真正免費採集測試發現 2026/27 季不在 Free 權限範圍內。唔係 Key 未接通，**重新貼相同 Key 唔會解決季別授權**。TheSportsDB 最近一輪已真實收集53場免費賽程樣本（以 `sources/latest.json` 為準，非完整聯賽覆蓋）。football-data.org 同 Sportmonks 尚未配置。


> 目標：只用免費合法數據源；所有 API Key 留喺 GitHub Actions Secrets。**唔好喺 GitHub Issue、公開 Repository、網頁、截圖、聊天或 README 貼出任何 Key。** 本文件唔會產生、傳送、讀取或保存私人密鑰。

## 先了解真實狀態

- **TheSportsDB**：免費 V1 共用開發 Key `123`；足球王者已經連接，唔需要你開新戶口。免費 `eventsnextleague` 每聯賽只限一個下一場樣本；唔會變成六大聯賽完整市場賠率。
- **The Odds API**：已有 `THE_ODDS_API_KEY` 接駁；免費每月500積分，請勿移除或將其他服務 Key 填入同一 Secret。
- **API-Football**：個人 Key 已存在；Free每日日常100次上限，但最新真實回應顯示2026/27當季**不獲免費使用權**。程式會停止不必要重複查詢；原有免費1X2仍由 The Odds API 提供。
- **football-data.org**：免費12 competitions、10 calls/min、部分比分/賽程延遲，**免費唔包 1X2 賠率**；等 `FOOTBALL_DATA_ORG_TOKEN`。
- **Sportmonks**：免費長期只有丹麥超聯 + 蘇格蘭超聯，**不涵蓋原本六大聯賽**；等 `SPORTMONKS_API_TOKEN`。優先級最低；唔好誤選需要付款或試用過後收費嘅方案。

## 新增：OpenFootAPI 免費 Starter（較值得優先申請）

1. 用 iPhone Safari 到 [OpenFootAPI 官方免費方案](https://openfootapi.com/pricing)，選擇 **Free Starter $0/月**，每月上限5,000次、最多60次／分鐘。毋須選開發者收費版本。
2. 依供應商介面親自註冊、驗證電郵、取得私人 API Key。**唔好用公開 Demo Key 作每日自動化**。
3. 打開 [GitHub Actions Repository Secrets](https://github.com/CHANCHUNWA1989/football-king-report/settings/secrets/actions)，建立：
   - **Name:** `OPENFOOT_API_KEY`
   - **Secret:** 你嘅私人 OpenFootAPI Starter Key
4. 用 [零額度 Key 設置核對](https://github.com/CHANCHUNWA1989/football-king-report/actions/workflows/football-king-free-api-keys-check.yml) → **Run workflow**；見 `OPENFOOT_API_KEY=PRESENT`。
5. 再手動運行 [新增免費研究來源採集](https://github.com/CHANCHUNWA1989/football-king-report/actions/workflows/football-king-research-extensions.yml)，檢查係咪 `FREE_STARTER_SAMPLE_ONLY`；只進行最多3次免費基本端點查詢，唔會買收費功能或輸出可下注賠率。

OpenFootAPI 免費 Starter **只有基本賽程、賽果、排名等能力**。其官方條款提醒原始上游來源仍各自有授權要求。歷史 StatsBomb Open Data 已經不需密鑰而接通，但需按其授權署名。

## 一、API-Football：首選，約 3–5 分鐘

1. iPhone Safari 開官方直接註冊頁：https://dashboard.api-football.com/register
2. 以 Google 或電郵建立賬號，**只選 Free / $0**。官方表示免費版唔使信用卡。
3. 如有驗證電郵，喺你自己信箱開啟並按確認連結。呢步要由你本人完成。
4. 登入儀表板，左方 **Account → My Access**，取得你個人 `api-key`。
5. 暫時複製密鑰，打開下面 GitHub Secrets 設定頁，建立：
   - **Name:** `API_FOOTBALL_KEY`
   - **Secret:** 貼上 API-Football Dashboard 顯示嘅密鑰
6. Save / Add secret。**唔使將 Key 回覆畀 ChatGPT。**

官方教學：https://www.api-football.com/news/post/how-to-get-started-with-api-football-the-complete-beginners-guide

**現有免費程式做緊乜：** 每次獨立工作流程最多12次呢個服務請求（每日最多兩次）；當免費季數被拒，會提早停止，唔會繼續扣無用請求。（6聯賽每個3場賽程 + 6個免費 1X2 市場*覆蓋探測*）；後者只計算可見市場事件數量，唔保存或發布原始博彩公司價格。免費容量及季數按供應商回覆為準。

## 二、football-data.org：約 2–4 分鐘

1. iPhone Safari 開官方註冊：https://www.football-data.org/client/register
2. 填寫 Name、Email，閱讀並自行接受條款，按 **Create account**。
3. 到你自己嘅電郵信箱取得 API Token；需要時可使用官方 **Resend token**。
4. GitHub Repository Secret 建立：
   - **Name:** `FOOTBALL_DATA_ORG_TOKEN`
   - **Secret:** 貼上官方寄畀你嘅 Token
5. 呢個來源只補賽程／賽果，**唔好以為佢提供免費博彩公司 1X2 賠率**。

官方方案：https://www.football-data.org/pricing

## 三、Sportmonks：選做，約 3–5 分鐘

1. iPhone Safari 開官方帳戶：https://my.sportmonks.com/
2. Register，使用電郵、Google 或 GitHub 建立賬號。
3. 如有確認郵件／驗證碼，親自完成；選 **Free Forever**，唔揀收費試用。
4. 到 MySportmonks 的 **Settings / API Tokens** 建立個人 API Token。
5. **Token 通常只展示一次**；立即放入 GitHub Repo Secret：
   - **Name:** `SPORTMONKS_API_TOKEN`
   - **Secret:** 剛建立嘅 Token
6. Sportmonks 免費版現時只限丹麥超聯／蘇格蘭超聯；足球王者只會探測呢兩項免費聯賽，唔會私下探測未授權嘅六大聯賽。

官方免費方案：https://www.sportmonks.com/football-api/free-plan/

## 四、三條 Key 全部都係同一 GitHub 設定頁

**GitHub Secrets（直接連結）：**
https://github.com/CHANCHUNWA1989/football-king-report/settings/secrets/actions

iPhone Safari：
1. 登入 GitHub，按上面連結；如介面太窄，可用 Safari 網站設定「要求桌面網站」。
2. **Settings → Secrets and variables → Actions → Repository secrets → New repository secret**。
3. 逐條填入上面指定嘅 **Name**；**Secret** 放入你喺個別供應商私人 Dashboard 取得嘅值。
4. 每次按 **Add secret**，總共最多三條。已有的 `THE_ODDS_API_KEY` 無需再填。
5. **唔好**將 Key 加到 GitHub Variables：要用 **Repository secrets**。

GitHub 官方操作：https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-secrets

## 五、不暴露 Key 嘅自動驗收（唔扣供應商請求）

1. 開啟：https://github.com/CHANCHUNWA1989/football-king-report/actions/workflows/football-king-free-api-keys-check.yml
2. 右邊按 **Run workflow**，選 `main`，再按綠色 Run。
3. 幾十秒後打開最新運行紀錄 → **Summary / Configure status**，檢查三條 Key 係 **已設定** 還是 **未設定**。只會顯示布林配置狀態，**唔讀取／列印真實 Key**，亦唔呼叫供應商，所以唔消耗 API 額度。
4. 原有 **四免費後備來源** 自動流程每天香港時間約 **05:43、17:43** 各嘗試資料採集一次；亦可喺 https://github.com/CHANCHUNWA1989/football-king-report/actions/workflows/football-king-secondary-sources.yml 手動按 **Run workflow**。只有執行該流程先會嘗試真正對應供應商 API 請求。
5. 查看 https://chanchunwa1989.github.io/football-king-report/ 頁面嘅「四個額外免費資料渠道」，或者 GitHub `sources/latest.json`；見到 **NOT_CONFIGURED** 代表未有 Key，**HOLD / PARTIAL** 代表有 Key 但仍可能有免費方案、供應商或覆蓋限制，唔等同授權成功。

## 六、如果開 Key 遇到問題

- **註冊頁要信用卡／進入付費試用**：立即退出；唔好為咗足球王者付費。
- **搵唔到 API Key**：喺官方 Dashboard／Email 查找，不可向陌生網站提交登入資訊。
- **GitHub 無 Settings**：喺你自己 GitHub 帳戶登入、Safari 切換桌面網站。
- **Secrets 已新增但仍顯示 NOT_CONFIGURED**：先核對名稱完全相同，再手動重新執行 key status workflow；後備來源實際資料要等下一次採集。
- **有 Key 但無資料**：可能係免費季數、賽事日期／覆蓋、區域存取、端點限制；唔會冒充有免費賠率。

## 安全承諾與功能邊界

GitHub Actions 只喺真正呼叫對應來源嗰一步可見其密鑰；公開網站、`sources/latest.json`、報告及測試輸出都唔應該包含 API Key。程式限制配額並標明來源同時間戳，**未驗證原始賠率／可下注價格唔會自動產生實盤推薦**。正式下注資格仍然 `HOLD / DISABLED`。

# 足球王者 V4.1｜iPhone 免費 API Key 申請全流程

**最後核實：2026-10-09。** 三個第三方帳戶嘅註冊、電郵驗證及同意條款，必須由你本人完成。請只用免費方案，絕對唔使喺 ChatGPT 提供 API Key。

## 已可使用：TheSportsDB

TheSportsDB 公開免費 v1 API Key 係 123，現時已經接通，唔需要註冊或存 GitHub Secret。The Odds API 先前已有獨立 Key，亦唔使更改。

## 1. API-Football｜優先申請

- [官方免費註冊](https://dashboard.api-football.com/register)
- [官方免費方案：100 次／日](https://www.api-football.com/pricing/)
- iPhone Safari 註冊帳戶，完成電郵驗證，登入 Dashboard，找到 API-Football 直連 v3 API Key。
- 選擇 $0 Free；唔好將 RapidAPI 平台嘅 Key 混用；免費季節限制及賠率覆蓋需要真正實測。
- GitHub Repository Secret 名稱：**API_FOOTBALL_KEY**。

## 2. football-data.org｜補賽程、延遲賽果

- [官方免費註冊](https://www.football-data.org/client/register)
- [免費計劃範圍及限制](https://www.football-data.org/pricing)
- 輸入名字與電郵；閱讀服務條款；註冊後於電郵取得 API Token（留意垃圾郵件）。
- 免費版有12個指定賽事、10次／分鐘；賽果及賽程可能延遲。免費版**沒有即時 1X2 賠率**。
- GitHub Repository Secret 名稱：**FOOTBALL_DATA_ORG_TOKEN**。
- 來源條款要求公開服務標示 **Football data provided by the Football-Data.org API**，以及保護金鑰，不得放喺公開程式碼。

## 3. Sportmonks｜額外免費資料研究

- [MySportmonks 免費註冊](https://my.sportmonks.com/register)
- [MySportmonks API Tokens](https://my.sportmonks.com/api/tokens)
- 建立帳戶，選 Free（不要選付費 14 日試用）。登入 Tokens 分頁，填 Token name，再點 Create。
- Token 可能只顯示一次，即時複製去 GitHub Secret。
- GitHub Repository Secret 名稱：**SPORTMONKS_API_TOKEN**。
- 永久免費聯賽只包丹麥超聯及蘇格蘭超聯，**唔會免費提供六大目標聯賽**。[官方說明](https://www.sportmonks.com/football-api/free-plan/)

## 4. iPhone 直接安全加入 GitHub

1. 先用 Safari 登入管理足球王者嘅 GitHub 帳戶。
2. 打開 [Repository Settings → Secrets and variables → Actions](https://github.com/CHANCHUNWA1989/football-king-report/settings/secrets/actions)。
3. 按 **New repository secret**。
4. 在 Name 貼上 **API_FOOTBALL_KEY**，在 Secret 貼 API-Football 官網剛產生嘅 Key，按 Add secret。
5. 另外兩個分別用 **FOOTBALL_DATA_ORG_TOKEN** 同 **SPORTMONKS_API_TOKEN** 重複。
6. 你之前嘅 **THE_ODDS_API_KEY** 唔需要更改；四個不同供應商嘅 Key 不可互用。

**安全規則：** 只放 GitHub Actions Secrets，唔好喺 GitHub Issues、公開網站、Repository 原始碼、ChatGPT 貼上 Key。保留少量有權管理工作流程的協作者。

## 5. 申請後一鍵驗證

1. 開 [足球王者｜新增API Key安全驗證（免費）](https://github.com/CHANCHUNWA1989/football-king-report/actions/workflows/football-king-api-key-check.yml)。
2. 按 **Run workflow → main → Run workflow**。
3. 點入該次執行，展開 **Check three optional free keys**。
4. 看以下安全結果：
   - **KEY_ACCEPTED**：成功驗證 Key，但六聯賽／免費市場覆蓋仍要等真正採集。
   - **NOT_CONFIGURED**：相關 Secret 未加入。
   - **KEY_REJECTED**：Key 被拒絕，檢查有冇貼錯。
   - **PLAN_OR_KEY_REJECTED**：當前免費方案無權限或 Key 有問題。
   - **FREE_RATE_LIMITED**：已達免費頻率限制，稍後再試。
   - **NETWORK_FAILURE**：暫時連唔到供應商。
5. 系統只會輸出狀態，**唔會喺執行日誌顯示原始 Key**。

## 6. 每日自動同步

[四個免費來源每日採集流程](https://github.com/CHANCHUNWA1989/football-king-report/actions/workflows/football-king-secondary-sources.yml) 已設每日香港時間約05:43運行（GitHub 排程可能延遲）。有 Key 先測試對應供應商，冇 Key 就會標示 NOT_CONFIGURED，不會打斷目前六聯賽研究與 The Odds API。

若全部成功加入，可回 ChatGPT 說：

> 三個免費 API Key 已經加入 GitHub Secrets，請檢查真實接通情況。

唔需要將密鑰、密碼、驗證電郵或私隱資料發給 ChatGPT。

**備註：** 呢個流程幫你建立連線，而唔會自動註冊第三方帳戶、信用卡或訂閱。正式投注建議繼續 HOLD，來源數量增多唔等於預測已證實可靠。

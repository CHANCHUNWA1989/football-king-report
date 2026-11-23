# 足球王者 VNext｜外部資料供應商授權與證據採購包（2026-11-23 HKT）

> **狀態：BLOCKED / RESEARCH ONLY**。這份文件是接洽與獨立審核清單，**不是**授權、採購訂單、法律意見、來源認證、API key、外部時間見證或已配置的實時連線。任何外部資料進入正式模型之前，必須通過下列驗收。

## 1. 真正阻塞
- 來源、用途與撤銷聲稱的 synthetic gate 已在 Draft PR #545 / #549 實作；**caller-supplied hash、名字、host 與「未撤銷」欄位無法自行證明授權**。
- GitHub issue #452：仍欠有權供應商簽署的資料授權、真正歷史／即場原始收據、賽前賠率時間戳、不可偷看結果的前瞻樣本。
- GitHub issue #439：main 分支規則／獨立 review / signer 保護未獲獨立驗收。CI 綠燈唔等於可以 merge。
- **唔做**無許可 scraping、不接未審核真實 provider HTTP、唔將合約或憑證提交 public repo、唔自行批准任何批准證據。

## 2. 供應商研究起點（要由有權人逐項確認）
| 供應商 / 主要用途 | 官方面向公眾的資料 | 待書面釐清 | 本專案狀態 |
| --- | --- | --- | --- |
| Sportmonks（潛在 live fixture / 事件 / xG） | https://www.sportmonks.com/integrity-support/ 及 https://www.sportmonks.com/terms-of-service/；企業套餐頁 https://www.sportmonks.com/football-api/enterprise-plan-v2/ | HK 使用範圍；實時事件及 xG 欄位保障；AI 推理、訓練、派生概率、商業／投注建議用途；原始回應私有保留、重播、外部簽名證據、再分發；費率、限速、撤銷；是否有真正上游獨立性 | **未接洽／未簽署／未授權** |
| StatsBomb Open Data / Hudl（歷史研究候選） | https://github.com/hudl/open-data/blob/master/README.md；明示部分研究資料公開及引用要求 | 覆蓋哪些比賽、引用、AI 模型／商用／再分發／保留許可；是否只限歷史研究；不能當即場盤口來源 | **未獲個別用途確認；不可當 live provider** |
| Football-Data.co.uk（歷史賠率資料候選） | https://football-data.co.uk/contact.php；免費 CSV/Excel 主要供個人及學術研究，不擬供部分 AI training / commercial bots | 是否有適合本專案的正式收費商用授權、歷史盤口 capture 時間、供應商 provenance、可否訓練／重播／衍生出售、配額與 API | **免費版本不預設合格；未授權** |

**重要：** 兩個不同供應商名稱不保證彼此原始事件獨立；兩個指向同一 upstream vendor 的資料可能係相關聲稱。若只一個供應商合格，記錄 source coverage 不足，而非假造二源共識。

## 3. 必須向供應商提出的書面問題
請供應商提供由有權簽署者確認的文件或可稽核工單編號，逐項回覆：
1. 法律主體、正式商用授權合同、簽署人權限、授權持有人名稱、使用地域（包括香港）、有效開始／截止、撤銷及到期通知。
2. `internal_research`、`inplay_analytics`、`model_training`、`odds_analytics`、`betting_recommendations`、`redistribution` **逐項 allow/deny**；不能以「可以做 App」推定所有用途。
3. 來源 API 官方端點、可取欄位（fixture/event ID、kickoff、score、red card、VAR、xG、lineups、odds）、對應聯賽及賽季、更新延遲、live 與 historical 限制。
4. 是否允許私有保存 exact raw HTTP response bytes、request/response metadata、SHA-256 manifest、TTL/留存期、刪除政策、第三方可信時間戳、獨立審計與內部模型回放。
5. 資料回傳可否附帶來源簽名、可靠事件主鍵、原始發布時間，如何處理更正、撤銷、延後發布、VAR 與 red card 修正；若無則明確 `unattested`。
6. 費用、試用資格、速率限制（每秒／每分鐘／每小時）、重大賽事峰值、429/5xx、可用性、故障回退、支援與退出成本。
7. 供應商是否資料原始發布者或聚合者；同其他候選來源共享相同上游 feed 與否，能否提供來源獨立性證據。
8. **如含投注相關場景**，是否容許向個人提供盤口分析／投注建議、展示來源名稱，及任何需另簽約的 bookmaker quotes。不能將 live 比分訂閱當成賠率授權。

## 4. 驗收證據文件（只保存於受控私有系統）
| 證據類別 | 必要證明 | 未通過處理 |
| --- | --- | --- |
| 書面合同/供應商授權 | 簽署原本、權利主體、用途 matrix、地域、留存、再利用及撤銷條款；獨立法律／商務 reviewer 確認 | `source_authorized=false` |
| 外部取消／撤銷查詢 | 受信來源和查詢時間、有效期、owner/ reviewer、撤銷理由 | `source_data_access_enabled=false` |
| 來源及真實事件 | 合法受控憑證、TLS/API endpoint、native ID、原始 response byte digest、私有檔案 readback | `original_provider_response_authenticated=false` |
| 時間證據 | response receipt、自動紀錄接收時刻與模型決策時刻，外部 RFC3161 TSA/見證 token，驗證 chain | `third_party_timestamp_verified=false` |
| 真實兩來源 | 不共享上游的獨立性核實、主客／kickoff ID 對齊、比分／紅牌／VAR一致及衝突 fail-closed | `source_independence_verified=false` |
| 可交易盤口 | bookmaker/selection/line/decimal odds、抓取時間、live usable quote、盤口類型與亞洲盤拆單邏輯 | `positive_ev_verified=false` |
| 前瞻 OOS | 訓練截止、事前凍結模型/預測、獨立封存賽果、重複及 lookahead 排除、CI、reviewer、Brier/log-loss/ROI 及 CI | `certified_forward_samples=0` |

**任何人工簽名或憑證文件都唔上傳公眾 GitHub repo / logs / PR / Actions artifacts**。Public repo 只保存不帶機密資訊的工作狀態、PR 連結、結果為 HOLD 的文字及准許公開的 digest；私有證據來源由獨立合規／安全 reviewer 管理。

## 5. 成功交付的定義
- [ ] 採購責任人取得**至少一個**簽署並逐用途釐清的有效授權；任何不確定欄位標記 `DENIED/UNVERIFIED`，不得默認授權。
- [ ] 安全及法務 reviewer 在**外部受控記錄**驗證來源、撤銷查詢與秘密存儲；供應商原始回應採集須有合法可控測試環境。
- [ ] 用一個獲允許的、可重播的真實事件 sample 驗證原始 bytes、時間及 native ID；如供應商未提供，保持 source gate HOLD。
- [ ] 獨立第二來源與可核實 bookmaker quotes 另行授權，未具備就不能宣稱二源共識或正 EV。
- [ ] main 分支規則及上游 Draft PRs 獨立審核、最新 SHA 的安全回歸 CI 通過；除錯或核對不能直接放行模型。
- [ ] 以事先封存、樣本外真實 cohort 評估，無足夠證據不得聲稱預測改善。

**持續限制**：`PRODUCTION_RECOMMENDATIONS=DISABLED`、`POSITIVE_EV_VERIFIED=False`、`certified_forward_samples=0`。本文件只將外部依賴明確化，**不新增 live source、數據、訓練樣本或模型功能**。

## 6. 關聯
- 實際授權／真實數據阻塞：https://github.com/CHANCHUNWA1989/football-king-report/issues/452
- 安全／獨立 review 阻塞：https://github.com/CHANCHUNWA1989/football-king-report/issues/439
- 研究用權益預檢：https://github.com/CHANCHUNWA1989/football-king-report/pull/545
- 地域／用途／撤銷檢查：https://github.com/CHANCHUNWA1989/football-king-report/pull/549

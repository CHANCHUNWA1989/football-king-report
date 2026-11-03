# KPL V9 — 來源權利、身份及離線 BP 接入審計（2026-11-03）

## 來源審計（能公開閱讀，不代表有批量採集／再發布授權）

| 類別 | 來源 | 觀察 | 策略 |
|---|---|---|---|
| 官方展示 | https://pvp.qq.com/matchdata/ | 官方賽事資料中心可公開瀏覽；頁面抽取可能顯示舊預設內容 | 只用作來源識別參考 |
| 前端資料服務 | https://prod.comp.smoba.qq.com/leaguesite/ | 非官方開源專案記錄賽事、場次、逐局 BP 資料路徑；本次未獲可核實的資料服務授權 | 禁止網絡採集；只有離線資料結構檢查 |
| 非官方 BP 數據集 | https://github.com/Fire-Phoenixs/kpl-bp-dataset | 說明 battle_id、match_id、bp_list 等欄位；衍生資料有非商業條款，來源權利屬騰訊等原權利人 | 僅參考公開欄位規格，不複製實際 BP 或程式 |
| 非官方分析平台 | https://github.com/hccccc01333/kpl-research | 標示非官方及非商業，賽程比分以官方為準 | 不當成授權機器資料服務 |
| 媒體 | 虎撲等 | 可供獨立人工查證，不等於獲授權抓取 | 等待單獨合約核查 |

參考：
- https://github.com/Fire-Phoenixs/kpl-bp-dataset/blob/main/docs/source.md
- https://github.com/Fire-Phoenixs/kpl-bp-dataset/blob/main/docs/fields.md
- https://www.gamelaw.cn/contract/2018/1103/59.html （騰訊遊戲協議轉載；以權利人現行正式條款為準）

**結論**：未找到已獨立核實、明確准許自動抓取、保存、商業利用及二次分發 KPL 逐局 BP 的特定授權。robots.txt 未禁止和頁面可讀均不等於授權。不編寫 HTTP 抓取器、不開排程、不宣稱任何非官方資料已獲官方認證。

## 新增離線接入器

模組：research/kpl_v9_offline_source_ingest.py

函數：inspect_offline_battle(payload, match_index, provenance, now_utc, previous_games)

僅接受使用者或已獲權利提供者合法取得的離線快照；接口採用第三方文件描述的官方形式欄位，未核實第三方文件等同官方版本承諾。

- payload 須包含 league_id、match_id、battle_id、battle_seq、兩隊 camp 的 team_id、逐手 BP 的 camp / is_ban_or_pick / hero_id。
- match_index 是另一份輸入，須以固定參賽隊 ID 及每局 battle_id / 藍紅方對照，檢驗大場和逐局身份；**程式無法證明兩份輸入真的獨立**。
- provenance 需提供 HTTPS 精確官方形式來源 URL、SHA256 摘要、時區明確的發佈與擷取時間，及 OFFLINE_SUPPLIED_SNAPSHOT 傳輸模式。摘要只驗證輸入一致性，不保證真實來源。
- 拒絕冒牌域名、重複查詢參數、歷史漏局、BP 英雄重複／漏選、己方英雄跨局重複（第七局例外）、不合法時間戳、來源逾時。
- 輸出永久 HOLD；即使結構通過，source_authenticated 仍是 False，未核實的資料不會進入勝率模型、網站或投注系統。
- 不作任何網絡請求，不帶入真實逐局英雄資料、付費 API、密鑰或第三方商業數據。

## 驗收

1. 本地 18 個完全離線合成測試已通過；依賴 PR390 的額外整合測試由 GitHub CI 驗證。
2. Python 語法編譯已通過；完整倉庫安全回歸和 CI 必須待本 PR 開立後驗證。
3. 無任何正式推薦、勝率模型權重、賠率採集、歷史封存及自動投注能力的改動。

## 進一步資料接入的必要條件

須有經獨立審核的資料授權、穩定來源/時間戳認證、可追溯聯賽與場次 ID、明確負載版本及延遲限制，再引入只讀供應者適配器。之後先按時間切分回測 KPL BP、經濟及資源模型。投資及投注決策仍然 HOLD/DISABLED。

PR390 是前置分支；本輪以獨立 stacked Draft PR 提交，未獲審核和完整 CI 通過之前禁止合併。

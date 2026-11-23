# 足球王者 VNext｜第十五關：退役舊版直接 HTTP 賽事下載入口（2026-11-23）

## 問題及重現
PR #546 新增咗需先見到同組變更標記、同聯賽限速及原生 round/season/matchID 核對嘅條件式手動下載。但 PR #538/542 仍存在舊 `ops/inplay_openligadb_one_shot.py --manual-one-shot`：佢只經共享限速，**無需證明來源標記改變**就可能發出完整 GET。底層 `capture_once(matchID, root)` 同 `paced_capture_once(matchID, root)` 在不提供函式參數時亦能觸發預設真實網絡請求。

## 本輪具體安全修正
- 舊 `inplay_openligadb_one_shot.main()` 保留舊參數作兼容錯誤訊息，但永遠返回結構化 `HOLD / LEGACY_FULL_MATCH_CLI_DISABLED`，不讀取私人資料夾、無網絡請求，退出碼 2；唔會自動改走新入口或代替操作員填寫 season/group。
- 底層 `capture_once()` 於 `getter=None` 時先於開檔、載入資料和 HTTP 直接 HOLD，回傳 `DIRECT_HTTP_GET_DISABLED_USE_CONDITIONAL_CLI`。
- 舊限速器 `paced_capture_once()` 於 `getter=None` 時先於建立共享限速狀態直接 HOLD，回傳 `DIRECT_FULL_MATCH_FETCH_DISABLED`。
- PR #546 的 `inplay_openligadb_conditional_capture.py --manual-changed-only` 保持唯一列明可進行真實手動完整 match GET 嘅 CLI：需要 `--match-id`、`--season`、`--group-order`、`--private-root`，執行前先核實 same-host change checkpoint、90秒聯賽窗口、5分鐘時效、一次性預留記錄與返回來源原生賽季輪次。
- 沒有自動排程、沒有真實網絡 request。現有 `getter` 依賴注入只留畀受控合成測試和已受保護的條件式內部路徑，不能宣稱所有 Python import 都防惡意開發者繞過；有本機程式碼寫入權的人依然可自行調用任何 HTTP 函式。

## 測試
新增 `ops/tests/test_inplay_openligadb_legacy_entrypoint_lockdown.py` 9項純合成回歸：舊 CLI 不能呼叫舊 pacer、冇檔案/HTTP；加入 season/group 亦不能用舊旗標繞過；兩個預設底層入口 fail closed；明確提供假 getter 嘅合成 byte capture／rate gate 舊測試仍可重播；新 conditional CLI 只分派給 `conditional_capture_once` 並拒絕舊 `--manual-one-shot` 旗標；舊回覆不含 ROI/賠率、永久 DISABLED。
另外保留並調整 PR #542 原有 manual CLI 回歸測試，由「必須通過 pacer」提升成「舊 CLI 必須直接拒絕」，不是刪除測試。

驗收指令：
```bash
python -m compileall -q ops
python -m unittest discover -s ops/tests -q
```

## 明確風險、缺口及部署前條件
1. 此修正只封閉 repo 公開指定的 **預設 CLI／無 getter 底層 HTTP 入口**。內部 Python 可注入任意 `getter` 進行研究，具任意原始碼執行權者唔屬於 Python API 層可防護威脅。若要全域強制限制，必須部署獨立網絡隔離、權限管理、集中 egress proxy 與跨 host 限速，並移除所有非授權網絡憑據及工作入口。
2. 以前 PR #538 及 #542 文檔內描述的舊 CLI 單場直接下載已 **退休，不可照行**；完整資料只使用 PR #546 新條件式手動 CLI。舊研究文檔只作歷史架構參考。
3. 仍然冇真實受控 POSIX 私有環境、雙獨立數據源、官方紅牌、可信時間見證、可成交賠率或前瞻樣本。成功 CI 只代表工程安全測試通過。
4. 永久 `production_recommendations=DISABLED`、`eligible_for_model_input=false`、`certified_forward_samples=0`、`positive_ev_verified=false`。任何科研輸出不構成投注建議，亦不證明模型預測準確率改善。
5. 疊加 Draft 依賴：#529→#530→#531→#532→#533→#535→#537→#538→#542→#543→#546→本PR。舊 PR 未經獨立 code review，不可以單獨合併到 main 或上線。
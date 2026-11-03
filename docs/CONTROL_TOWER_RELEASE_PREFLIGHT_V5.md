# AI 研究控制塔 V5：只讀正式發布前驗收

**研究階段，Draft；此閘門唔會批准發布、合併 PR、啟用投注或改變風控。**

## 前提與目標

- 上游依賴：PR #405，精確 HEAD 66035d2ffd9938f1a529d2b2cc33f5c6fb5dd2e1。
- 本階段為獨立堆疊 PR，base 係 #405 研究分支，唔會寫入 main。
- 驗收要求：PR #405 不是 Draft、仍 open；GitHub main 未偏離 PR base；main 具有效分支保護及必需審核／CI 政策；當前 HEAD 8 項指定 checks 成功；有另外一位具 repository write/maintain/admin 權限嘅正式 GitHub reviewer，該 reviewer 最近提交嘅 APPROVED review 綁定相同 HEAD；當前 HEAD 有成功監控 workflow 同對應 artifact metadata。

## 證據與 fail-closed

- 所有 Github HTTP 失敗、403、404、429、時鐘不明、部份分頁、條件不完整、錯版簽核、作者自我核准、CI 取消／失敗／未完成 → HOLD。
- GitHub Token 只讀，冇 write、deploy、issue、market API secrets、投注／交易權限。
- 若缺 branch protection policy 詳情（例如 repo 權限不足），HOLD，而唔係猜測有保護。
- Preflight 即使全部通過只會回 PRELIMINARY_ACCEPT_REQUIRES_MANUAL_RELEASE，因為仍需獨立審核程式、實際 artifact bytes、合併後網站 readback、排程及資料新鮮度。 `release_authorized=false`、`deployment_allowed=false` 永久不變。
- 此流程不讀取兩個私人（籃球／量化）倉庫，不修改既有市場、模型或輸出。
- 發布安全驗收同模型準確度屬兩回事；無真實授權報價、完整前瞻結算樣本，不得推定正 EV 或進行投注。

## 操作及單元測試

- 檔案：ops/control_tower_release_gate.py
- 測試：python -m unittest discover -s ops/tests -p test_control_tower_release_gate.py -v
- 工作流程：Control Tower V5 Release Preflight (read-only)
- 只會寫入暫存 artifact（7日），不喺主分支啟用任何新排程。

## 未完成發布前置條件

1. 真正獨立授權人員驗證 PR #405 及 V5（不可由作者冒充 reviewer）。
2. 管理員啟用 main branch protection 和真正 required-review／checks 規則；單一 CI 成功無法替代。
3. 確認所有必要 workflow及 artifact（實際內容）與 exact HEAD 綁定。
4. 經獨立批准後再提出合併計劃；如果獲准合併，另做實際部署及網站 readback 驗收，唔喺本 PR 自動進行。

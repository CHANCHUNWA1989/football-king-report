# 足球王者 VNext PR-11｜逐個 PR 審核、同場版次 CI 及安全准入證據表

2026-11-04 · **RESEARCH / DRAFT / HOLD / NOT DEPLOYED**

## 即時核對結果

- **目前主分支**：GitHub API `main.protected=false`；`rulesets=[]`；詳細 `branches/main/protection` 欄位仍回傳 **403**。沒有證據允許聲稱已設好獨立審核、admin 防繞過或禁止強推。
- **VNext 主依賴鏈**：PR `#429 → #430 → #431 → #433 → #434 → #435 → #436 → #437 → #438 → #440` 全部 OPEN/DRAFT/未合併，base/head 名稱與鏈相符。額外 PR #432 屬 PR-03 替代路線，**不**屬這個選定的依賴鏈。 並會單獨查核 PR #432 沒有被合併；如替代 PR 已合併或狀態無法查閱，直接 HOLD。
- **審核紀錄**：GitHub PR Reviews API 已逐個核查上述 **10/10 個 PR，全部 0 項 submitted reviews**，未有獨立審核批准。
- **CI：** PR #440 exact-head `0c2ade6091a08931fc4a7b2e558f6a0111970de3` 有六項所需 GitHub Actions checks 全部成功、對應 App ID 15368。較早階段曾有重名 `regression`；PR-10 已在研究分支改名，**但沒有合併至 main**。
- 上述 CI 成功 **絕不等同** main 受保護、PR 已 review、真實簽章、足球來源授權、模型更準或正 EV。

## PR-11 實際新增

`ops/vnext_pr11_stack_review_audit.py` 提供**只讀** GitHub API 目前證據盤點，不修改任何 PR、設定或部署：
- 固定倉庫及完整選定 stack；每個 PR 應有固定依賴 base/head，且只接受合法 exact-head 40字元 SHA。
- 檢查每個 PR 是否從 Draft 轉成可審核狀態、未被意外關閉／合併；要求在**最新 HEAD SHA** 上由**非作者、非 Bot** 的 GitHub 用戶提交批准。舊版 commit 批准、最新提交後被撤回／要求修改、缺頁、已搬動分支一律判 HOLD。
- 每個 upstream PR 都要有 `safety (3.11)`、`safety (3.12)`、`validate`、`ledger-tests` 四個 exact-head 成功檢查；PR #440 另要求新嘅 `security-regression`、`failover-regression`。六個都要係 GitHub Actions App ID **15368**，拒絕重複所需 context、假的成功 / 錯誤 app、過期 SHA 或不完整 API 回傳。
- 對 `main` 嘅 protected 狀態及 detailed protection policy 進行獨立核對：必須有新版本批准、stale review dismissal、last-push approval、admin enforcement、strict CI、六個受 App 綁定必需檢查及不可 force-push/delete。API 403/錯誤一律 HOLD。
- 再次讀取每個 PR HEAD，避免審核期間 SHA 靜悄悄改變。
- 對外只輸出**限制性狀態**和阻塞原因，不會輸出任何憑證。即使合成測試全部條件滿足，結果最高只可以係 `RESEARCH_REVIEW_CHECKS_OBSERVED_ONLY`，`permission_to_merge=false`、`independent_security_review_verified=false`、`production_recommendations=DISABLED`。
- CLI **永遠非零退出**，避免被任何 GitHub Actions 錯誤當成可自動合併、部署、簽章或解除安全鎖。實際該工具只係**預合併狀態盤點**，之後逐個已審核合併會改變底層 stack 形狀，需要另行明確遷移，不可以自行更改 base 來蒙混。

`ops/tests/test_vnext_pr11_stack_review_audit.py` 使用模擬 GitHub API 結果測試，包括10個相連 PR、舊 SHA 批准、作者批准、Bot、CHANGES_REQUESTED、錯誤 Base、403、未受保護主分支、CI 合同、錯誤 app 及重複 CI 名稱、檢查期間提交變更和 CLI 永不提升。

## 現存阻礙與 GitHub 權限

已另行追蹤於 [Issue #439](https://github.com/CHANCHUNWA1989/football-king-report/issues/439)。

1. GitHub 倉庫管理員需啟用主分支保護，強制獨立審核、更新後重新批准、必需 CI、禁止 admin bypass／強推／刪除；可能需要調整連接器 Admin **read** 權限，才能從 API 可靠檢視。
2. 每個 Draft PR 須有真正**不同人**獨立安全審核及應有授權，不可以由本工具自我審核、自動通過。GitHub 帳戶標記 `User` 也**不等於**獨立證明真人身分。
3. PR-08 合成簽章只係將來受控工作流程，未有主分支真實 Sigstore/Rekor 已驗證產物；而來源授權、獨立數據、樣本外勝率／校準、亞洲盤／大小球可成交價及 EV 仍未證實。
4. CI 只驗證程式守衛與 Mock 規則，唔係對 GitHub Main 現狀作批准。

## 驗收

```bash
python -m compileall -q ops
python -m unittest discover -s ops/tests -q
```

只可喺**exact final PR HEAD** 並成功執行所有測試後報告工程 CI 通過；不能將之誤寫成 release-ready。之後如要以 workflow 監察，應保持讀取權限最小及 `HOLD` 明示，永遠唔好把進程成功碼當 release 授權。

**所有正式推薦和下注功能保留 `HOLD / DISABLED`。**

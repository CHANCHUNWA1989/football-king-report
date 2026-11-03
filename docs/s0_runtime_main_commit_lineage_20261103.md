# 足球王者 S0｜真實主分支寫入／網站發佈運行證據（2026-11-03）

**Status: PARTIAL_VERIFIED_RUNTIME_LINEAGE / S0 INCOMPLETE / NO RELEASE.**
本文件是對公開 GitHub 既有提交與 GitHub Actions 成功工作嘅讀取核對；
未部署新代碼、未執行額外市場 API、未觸發新採集或真實 BSD archive cutover。

## 1. Main branch and directly observed bot commits

從 GitHub REST `/branches/main` 讀取到提交
`b03a93818424bd207c2d961b43f076217a94c2f5`，`protected=false`。
從 `/commits?sha=main&per_page=30` 同指定 `path` 嘅提交歷史
**讀到以下 commit 位於 main 既有提交歷史**。同時逐個讀取
GitHub commit API 返回之 **實際 changed files**，唔係只靠 commit title：

| Main commit SHA | UTC commit / 實際修改檔案 | 觀察到嘅流程作用 |
|---|---|---|
| [`17f3eecc`](https://github.com/CHANCHUNWA1989/football-king-report/commit/17f3eecc865e06c00ac57322dd46c0b2f130d831) | 2026-11-02 23:40 UTC；`sources/bsd_status_latest.json` | BSD 免費後備來源仍然實際寫入 main |
| [`5a9c7f78`](https://github.com/CHANCHUNWA1989/football-king-report/commit/5a9c7f788f441115d0897be1ed84fe81ca464393) | 2026-11-03 04:35 UTC；`sources/latest.json` | 次級免費來源寫入 main；網站發布流程直接讀此檔 |
| [`a50859ce`](https://github.com/CHANCHUNWA1989/football-king-report/commit/a50859ce2d62a873739ac36fc52359cf817267aa) | 2026-11-03 01:59 UTC；`market/latest.json` | 研究用市場概率持續更新 main；非可成交莊家報價保證 |
| [`34b2acd2`](https://github.com/CHANCHUNWA1989/football-king-report/commit/34b2acd25d86038909319bce0655592172f9380e) | 2026-11-02 22:31 UTC；`evidence/settled.json` | 研究結算紀錄寫入 main，非獨立認證前瞻結算 |
| [`3711347e`](https://github.com/CHANCHUNWA1989/football-king-report/commit/3711347ed8924700bb17d4f347ac583985bb9787) | 2026-11-03 04:38 UTC；`history/2026/11/03/41579070273-1.json.gz`、`research_pairs/...`、`shadow/...`、`verification_slates/...`、`worldwide_shadow/...`，共五個檔案 | iPhone run 41579070273 嘅研究封存，工作流程原碼直接推 main |
| [`b03a9381`](https://github.com/CHANCHUNWA1989/football-king-report/commit/b03a93818424bd207c2d961b43f076217a94c2f5) | 2026-11-03 04:38 UTC；十個 `forecast_provenance/2026/11/03/41579070273-1/*` 證據檔 | 同一 run 嘅公開預測證據封存到 main；Git commit 唔係可信外部時間見證 |

## 2. Actual GitHub Actions run cross-check

[GitHub Actions run #41579070273](https://github.com/CHANCHUNWA1989/football-king-report/actions/runs/41579070273)
之 GitHub API 原始 run metadata：
- Workflow：`Football King V4.1 iPhone Daily Report`
- Workflow file：`.github/workflows/football-king-iphone.yml`
- Event：`workflow_run`，`head_branch=main`，`head_sha=5a9c7f788f441115d0897be1ed84fe81ca464393`
- Time：`run_started_at=2026-11-03T04:35:59Z`，
  `updated_at=2026-11-03T04:39:10Z`
- `status=completed`、`conclusion=success`
- GitHub job metadata：`publish` success、`archive` success、
  `archive_provenance` success、`attest_research` success、
  `close_resolved_incident` success、`notify_failure` skipped。
- 實際 `archive` job 原始 log 顯示 `[detached HEAD 3711347]` 同
  push 成功，後面 settlement merge 輸出
  `{"merged_samples":73,"newly_settled":0,"production_recommendations":"DISABLED"}`。
- `publish` job 原始 log 包括 GitHub Pages 目標
  `https://chanchunwa1989.github.io/football-king-report/`，job 結果 success。
  但未針對呢次部署另外核對網站最新 data hash／分鐘級生效時刻，
  **唔可將 job success 當成已獨立完成網站逐檔核實**。

## 3. Writer→file→reader relationships (what is truly proven)

1. **main writer evidence = confirmed for above SIX concrete commits.**
   Source file changed in main commit history and commit API shows exact path.
2. **Publisher successful run = confirmed for one iPhone workflow run** (#41579070273)；
   run/job API metadata 與 main commit paths 含同一 run ID 作交叉核對。
3. **Reader wiring = source-code-confirmed, not newly deployed archive branch**：
   `.github/workflows/football-king-iphone.yml` 目前用
   `sources/latest.json`、`market/latest.json`、
   `sources/bsd_status_latest.json`、`evidence/settled.json`
   以及相應 overlay／研究模組。
4. **No BSD archive cutover verification.** Draft
   [#382](https://github.com/CHANCHUNWA1989/football-king-report/pull/382)
   只完成離線改寫與測試，唔係上面既有 main archive 歷史嘅替代。
5. **Not external attestation.** GitHub action 完成、commit 著錄、工序 log
   唔能代替可信第三方賽前時間見證、真實獨立賽果來源、或經授權
   bookmaker executable quotes。收益／正 EV 仍未獨立驗證。

## 4. S0 remaining stop criteria

- [x] 利用 GitHub main commit history、每個 commit 真實 changed files
      及 Actions run/job/log 對照**至少一條實際來源→網站→封存運行路徑**。
- [x] 給出 main 組別（source/market/evidence/網站 archive）嘅實際提交 SHA，
      可被獨立 reviewer 重讀，而唔係抽象計數。
- [ ] 動態檔名、所有 producer/reader (包括 JS／間接 ops)、其餘 main
      writers 嘅運行證據及權限尚未逐一驗證。
- [ ] 按 PR #382 的新 archive branch 作 **受控真實 canary**、
      同時證明 Pages 讀取新分支、快照新鮮度、HOLD、rollback。
- [ ] 經不同身份嘅有效 independent Reviewer 正式批核；
      現階段不允許合併或自動開放預測。
- [ ] 確保其餘 main writers 全數隔離、驗證 GitHub branch/ruleset
      真正生效。現有 main `protected=false`。

**Remains `HOLD`, `production_recommendations=DISABLED`, `verified_ev=false`。
S0 仍然 PARTIAL；呢份報告唔係 production go-ahead。**

Tracking： [Master #383](https://github.com/CHANCHUNWA1989/football-king-report/issues/383),
[Release blocker #56](https://github.com/CHANCHUNWA1989/football-king-report/issues/56),
[Static inventory PR #381](https://github.com/CHANCHUNWA1989/football-king-report/pull/381).

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

## 4. Live main Git lineage — repeatable GitHub CI, NOT writer identity attestation

The earlier sections record manually checked commits and workflow logs.
This latest phase adds `ops/main_writer_git_lineage.py`, 9 real-local-Git
regression tests and a **second read-only CI job**
`runtime_main_git_lineage` in
`.github/workflows/release-main-archive-audit.yml`.
The job checks out the actual `main` branch into a separate read-only
sparse worktree (60 commits of Git history), then inspects **each Git
commit's actual changed paths** using `git diff-tree`. It never invokes
the optional market vendor, writes to the Git repository, performs a
GitHub Contents PUT, deploys Pages or executes data-branch code.

[Successful runtime evidence Actions #41609829635](https://github.com/CHANCHUNWA1989/football-king-report/actions/runs/41609829635)
captured the actual main HEAD
`131b6f8228ca00fe3c97d5905e65cf05d2997f76` at approximately
**2026-11-03 09:17 UTC**. Observed **60/60 sampled main commits** with
research-path changes, aggregating **6,866 matching changed-path instances**.
This is a count of changed path occurrences across commits, **not a count
of distinct files**. The research-related commit category counts are:

| Direct Git path category | Commits observed in 60-commit window |
|---|---:|
| `sources/bsd_status_latest.json` | 2 |
| `sources/latest.json` | 2 |
| `market/latest.json` | 2 |
| `evidence/settled.json` | 1 |
| `forecast_provenance/` | 10 |
| `history/` | 9 |
| `research_pairs/` | 9 |
| `shadow/` | 9 |
| `worldwide_shadow/` | 9 |
| `verification_slates/` | 9 |
| Other `sources/` paths | 35 |
| Other `market/` paths | 4 |
| `ndr_capture_provenance/` | 2 |
| `openliga_capture_provenance/` | 2 |

One bulk commit exceeded the receipt's per-commit detailed path list cap
(1,000 retained candidate paths per commit), so the **individual path
list is explicitly marked truncated**. All 6,866 matching paths still
contribute to the total and per-category counts. The Git checkout is
depth-limited to 60 commits: **this is not a full-main-history audit**.
The successful run retained `s0-real-main-git-commit-lineage`
(artifact **13218441918**, 14-day retention, expires
**2026-11-17 09:17:40 UTC**), alongside the separate conservative
static workflow candidate map. Those are GitHub Actions artifacts,
**not independent immutable or third-party timestamp witnesses**.

The first real-run attempt stopped at the conservative 2,000-files-per-commit
limit; it was explicitly marked `MAIN_RUNTIME_LINEAGE_AUDIT_INCOMPLETE`.
The updated scanner counts large commits completely and marks truncated
per-commit listings; 9/9 offline tests then passed, including the truncation
case. GitHub CI on code head `2742cc7842bdb035e31be5ee48e814ccb15867c3`
verified this real scan. Subsequent documentation-only commits require
their own exact-head CI before acceptance.

**What remains unproven:** Which exact workflow actor/credential wrote
each commit, indirect/dynamic reader and writer edges, completeness beyond
the sampled 60 commits, enforceable branch protection, external odds/data
authenticity, independently sealed forward evidence, independent Reviewer
approval or any real BSD branch cutover. All promotion flags stay FALSE;
`HOLD` / `production_recommendations=DISABLED` remain required.
The current #381 and #382 PRs are open and Ready for review but **not
merged or independently approved**.

## 5. Real Actions Run→Job→main Git commit correlation (two historical jobs)

The preceding bulk 60-commit scanner identifies changed paths but **cannot
attribute a specific writer actor**. This separate, narrow gate now confirms
**two concrete Job→commit associations** by independently reading historical
GitHub Actions run metadata, each named job's raw log (private to this CI run),
and the corresponding exact changed files and parent SHAs from an actual
`main` Git checkout.

Historical [iPhone Daily Report run #41603036531](https://github.com/CHANCHUNWA1989/football-king-report/actions/runs/41603036531)
was the `schedule` event, `head_branch=main`, immutable run attempt 1,
`head_sha=ed576e4a744b129d68e85d6f07a5a0ef5676eb7f`,
GitHub `status=completed`, `conclusion=success`. The dedicated read-only
validation checks:

| Historical Job | GitHub Job ID | Confirmed main commit | Exact changed paths |
|---|---|---|---|
| `archive` | `125806924489` | `73ebf27610c501c971dffa56aac0f681bf300f6f` | Five files: `history/`, `research_pairs/`, `shadow/`, `verification_slates/`, `worldwide_shadow/` under `2026/11/03/41603036531-1.json.gz` |
| `archive_provenance` | `125807102939` | `d72090777c7b084e6f20dd5bba19b27225997dcf` | Ten files under `forecast_provenance/2026/11/03/41603036531-1/`, including sealed research/negative-check artifacts |

Both historical job logs contain their **actual detached HEAD commit shorthand,
changed file paths and successful `HEAD -> main` push line**. The first
commit's direct parent is the original run's head SHA; the second's
direct parent is the first commit. These two commits were verified as
ancestors of the independently checked-out `main` HEAD.

The new PR #381 code `ops/main_workflow_job_lineage.py` rejects wrong run
attempt/status/repository, wrong job IDs, missing or forged job log push,
changed paths, ancestry mismatches, duplicate JSON keys and ambiguous
metadata. CI `runtime_job_correspondence` fetches **one pinned public
run** and the two jobs using read-only `gh api` permissions
(`contents: read`, `actions: read`), then validates against the real
separate Git checkout. **Raw job logs are never uploaded or published in the
artifact**; the artifact contains only the checked identities, file paths
and hashes of normalized logs.

[Successful GitHub Actions #41611717364](https://github.com/CHANCHUNWA1989/football-king-report/actions/runs/41611717364)
on code head `8444803b7eef6bd13fe85ceecdeb2c8de3767145`
has **6/6 successful CI workflows**, including 8/8 isolated negative
lineage tests, the original 9 Git-history tests and 16 workflow static
tests. The result is
`TWO_HISTORICAL_MAIN_WRITER_JOBS_CORROBORATED`.
Dedicated evidence `s0-two-verified-main-writer-job-links` GitHub
Actions artifact **13218359590**, expires
**2026-11-17T09:31:39Z**, from the same run. The underlying raw historical
logs remain available via GitHub authorized job-log views but are not
bundled in the attachment. Any subsequent documentation commit must be
validated again at its own SHA.

**Limits:** This identifies **which two named jobs produced two concrete
main commits**, not the personal credential/independent identity, and not
all other main writers, the exact source/vendor authenticity, or any
independently witnessed external market timestamp. It does NOT show that
the proposed BSD archive branch has been used by the real collector,
nor establish protected main, approval, forecasting performance or positive
EV. All release flags remain false. Independent S1 reviewer required.

## 6. S0 remaining stop criteria

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

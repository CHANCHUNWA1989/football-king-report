# 足球王者 VNext PR-14｜每週報告隔離封存（第二個試點）

2026-11-04 · **DRAFT / RESEARCH ONLY / HOLD / DISABLED**

## 實際問題

GitHub `main` 上 `.github/workflows/football-king-weekly.yml` 每星期五香港時間18:20使用 `contents:write`，將 `ops/weekly_digest.py` 產生的 `reports/weekly/YYYY-MM-DD.md` 透過 GitHub Contents API PUT 直接寫到**默認主分支**，並另行以 GitHub Issue 通知。當日後落實 PR-only / 嚴格 main 分支保護，這個現有寫入流程可能被正確阻止。

前一個 [HKJC寫入研究PR #442](https://github.com/CHANCHUNWA1989/football-king-report/pull/442) 及 [讀取PR #443](https://github.com/CHANCHUNWA1989/football-king-report/pull/443) 仍未合併。呢個第二試點**獨立從 main 建立**，唔依賴 #442 / #443，亦唔改任何市場模型或供應商採集流程。

## 已修改（未部署）

- 預先建立 `research/weekly-report-archive` **隔離封存分支**（由當時 main 建立，無新增資料）。
- 新增 `ops/weekly_isolated_archive.py`。只准向該倉庫該分支的 `reports/weekly/YYYY-MM-DD.md` **首次新增**，不能改寫已存在的每週報告，更不會 PUT 主分支。
- 封存前確認固定研究分支的 Git commit ref；驗證本地報告固定標頭、研究免責文字、6個聯賽、`HOLD / DISABLED`、UTC截點與香港曆日對應、24小時內生成、UTF-8、大小上限、無已知秘密或賠率正文標記。
- `GET` 只用 `?ref=research%2Fweekly-report-archive`，已存在報告必須用 Git blob SHA-1 驗證精確 bytes。**相同內容重跑**容許原樣保留；**同日不同內容、HTTP 403、409／422衝突、不可讀metadata、非法路徑**均 fail-closed。Git blob SHA只用於API一致性，唔係Sigstore/Rekor或外部時間見證。
- 工作流程只更換檔案封存步驟成 `python ops/weekly_isolated_archive.py`，保留**原本每週統計計算、免費API零額外請求、全套fail-closed單元測試、GitHub Issue通知**及生成報告；checkout採用固定SHA+ `persist-credentials:false`。只限固定倉庫嘅 main 分支執行正式排程。
- `ops/tests/test_weekly_isolated_archive.py` 覆蓋建檔、重跑、衝突、時間錯誤、冒充敏感資料、錯branch、被改寫blob、403、GitHub API邊界及工作流程靜態檢查；完全為synthetic mock，不觸碰真實供應商或市場。

## 重要運作後果

- 原本 `main/reports/weekly/YYYY-MM-DD.md` 歷史不刪、不重算。將來若本研究PR經真正獨立審核合併，**新嘅每週報告會只出現在隔離分支**；任何只讀main報告檔的用戶或程式將看不到新一週。GitHub Issue每週通知仍有報告內文，但不應當作經認證的準確率或博彩授權。
- 本試點用 **同日不同內容 => HOLD**，特別係人工重新Run同一日產生不同截止時間嘅報告，唔會悄悄覆蓋第一次版本。需要更正必須用獨立檔名、受審核PR或後續設計正式修訂紀錄。
- 原有定時工作一旦被主分支保護規則拒絕，應有可見CI失敗，不可回退默認main寫入。
- 此第二個試點只針對15個已有直接repo寫入候選之中的週報；其餘 HKJC + 13條仍未部署或遷移。主分支 `protected=false`，詳細Admin-read 403同獨立審核欠缺仍須按 [Issue #439](https://github.com/CHANCHUNWA1989/football-king-report/issues/439) 處理。

## 安全與驗收

`production_recommendations=DISABLED`、`can_execute_bet=false`、`positive_ev_verified=false`。報告可能包含歷史模型／市場研究數據，但**未獨立認證其來源、真實樣本外優勢、可交易報價或盈利能力**。程式CI通過也不能取代實際分支保護、獨立人類review或GitHub主分支簽章。

在本PR最終head須通過 `python -m compileall -q ops`、`python -m unittest discover -s ops/tests -q` 及5組 GitHub Actions CI，查閱原始日誌後先標記「工程驗收」。PR維持Draft，不合併、不部署、不更動原來香港時間每週排程。

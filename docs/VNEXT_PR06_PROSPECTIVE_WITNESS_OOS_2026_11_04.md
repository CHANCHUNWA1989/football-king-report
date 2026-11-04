# 足球王者 VNext PR-06：本地前瞻封存、來源政策及配對信賴區間

**2026-11-04 · 研究用 · 僅離線程式、無新API或來源採集 · 疊加PR #434 → #433 → #431 → #430 → #429**

## 先核實嘅現有授權與來源信任狀態

- Repo main 分支公開，GitHub API repo `license=null`；**唔可以由此推定供應商資料可複製／商業重用**。
- `README.md` / `DEPLOYMENT_STATUS.md` 表示 The Odds API 衍生市場共識機率不等於可執行賠率，公開倉庫唔保存原始 bookmaker 價格，免費資源有配額及現季權限限制。
- `ops/policies/result_sources_v1.json` 固定 `bundesliga/2026-2027/regulation-90-minutes`；NDR、DFB、OpenLigaDB、OpenFootball 上游獨立性 `UNKNOWN`，原始公開重用未確立；`ops/trusted_result_evidence._policy()` 有政策 SHA 綁定。
- `ops/shadow_external_evidence_collector.py` 明確禁止 DFB 自動採集及原始材料公開重用；唔會改動禁令、沒有新增 request。
- 現有 `ops/forecast_provenance_audit.py` / `ops/dixon_coles_witness_audit.py` 使用真實 GitHub Sigstore / Rekor 重驗受控原件，**但仍不證明實際開賽、來源獨立性或真實賽果**。PR-06 唔會將自述簽章或已儲存「verified」JSON 升格。
- PR #429–#434 均未合併。所有 PR-06 實作停喺獨立研究分支，永遠 `DISABLED/HOLD`。

## 新增程式1：`ops/vnext_prospective_local_seal.py`

功能：
1. 接受只包含雙模型賽前 `pair`、原始輸入證據 SHA 的**衍生 metadata**；禁止 bookmaker 價、終場賽果及 caller 自行聲稱的授權旗標。
2. 封存時以執行環境即時 UTC 做基本上界；`captured_utc` 明確只供測試／受控重播，**因此仍可偽造，唔係可信時間見證**。要求 `source_updated <= received <= available <= forecast <= captured <= forecast+2min <= kickoff-10min`。已過可用期或逾時拒絕。
3. 使用固定根目錄 fd、`O_NOFOLLOW`、`O_CREAT|O_EXCL` 排他建立 chmod 0600 JSON，立即 fsync file + directory，阻止同一 fixture+cut 覆寫。根目錄不可 symlink、不可群組/公眾寫入；檔名用 fixture+asof hash 避免路徑注入。
4. 對外返回當次檔案 SHA256；讀取必須攜帶**分開保存**的 expected SHA，同時重新讀 bytes、比對哈希與內文身份。不能靠同一文件自簽成為外部證據。
5. 只用 caller 自述 digest、原始 feed timestamp；完全唔會自行驗證 upstream、真實取用、網站政策或外部 tlog。狀態只可為 `LOCAL_SEALED_RESEARCH`。
6. `audit_source_independence` 直接讀**現有已固定 SHA 的政策**；只處理政策涵蓋 Bundesliga 2026–27 兩個來源提供的同場完整90分鐘比分。若雙來源顯示相同 -> `observation_agreement=True`，但 `status=HOLD`、`independent_result_authentication=False`。相異則明確衝突，未知聯賽/季別一律拒絕。兩站同分不是獨立供應商認證。

**本地 O_EXCL 不能防止具有檔案系統權限的管理者在事後移除/覆寫；需要日後以已驗證的 Sigstore 証明、Rekor 外部時間、受審計外部 witness 及固定實際 fixture ID 完成額外的來源可信鏈。** 本 PR 無任何聲稱真實授權來源已簽發呢啲見證。

## 新增程式2：`ops/vnext_prospective_block_bootstrap.py`

目標：可嚴格檢查事前 manifest 提供的**完整 cohort**，並以逐賽事 ID 而非逐分鐘為樣本單位：

- 300–3000 個不同 fixture；至少12個 UTC ISO 週；一個賽事一個唯一賽前截面。
- 事前固定 `cohort_id`、訓練 cutoff、註冊時間、評估截止、base/challenger 模型ID、主指標 LOG_LOSS、重抽樣單位 UTC_ISO_WEEK。
- `training_cutoff < registered <= forecast <= captured < kickoff <= evaluation_end <= evaluated`；實際 result `received >= kickoff+90min`。
- 每一個案例重新打開獨立封存檔、核對 SHA、對照 manifest，不得漏一場／重複一場；讀兩來源得分是否一致，與結果完全一致。來源仍未知獨立，數值只能用於探索性診斷。
- 重用 PR-05 `_row` 同 `_score`，對同場同時點 baseline/challenger 計三分類 Log Loss、Brier、Draw Brier 差（基準減挑戰者），並按週做**500次固定seed叢集bootstrap**，提供兩側95%百分位區間。
- 正面點估計／區間不跨0 **均唔代表模型獲實證批准**；bootstrap本身唔修復選樣偏差、資料來源不真實、多重測試或參數過擬合。
- 沒有已認證授權賽果、外部宣告文件、凍結訓練流程或真實holdout；輸出永久 `EXPLORATORY_ONLY`，`independently_verified_real_oos=False`，`model_accuracy_improvement_verified=False`、`market_ev_verified=False`、`production_recommendations=DISABLED`。
- 任一檔案、時刻、授權、比分、來源政策、manifest或模型版本不符，整批 `HOLD`，不靜默過濾，亦不提供賭注或可執行價格。
- 300場及12週係**工程/樣本涵蓋閘門**而唔係統計檢定力保證；真實數據需要按聯賽/時間聚類設計、原先註冊之多重假設控制、分開報告缺失選樣及差異置信區間。

## 本次實際完成／尚未完成

**實際完成：** 兩個離線研究模組、單元/逆向測試、以合成資料驗證本地排他封存、固定來源政策、配對評分和週叢集CI。

**尚未完成：**
- 已授權、真實來源賽果及球員事件採集（未新增任何外部API或耗費配額）。
- 真正 `gh attestation verify` + Rekor 外部時間見證連結到**新 PR-06 的每筆實際封存**；現有 v4.1 封存驗證不自動轉移為 vNext 的核證。
- 客觀上游獨立性、完整一致之實際開球 / 完場 / VAR 身份、第三方授權文件。
- 真正完整 holdout 事前登記、不可由結果回溯修改的模型+數據，以及獨立OOS信賴區間。
- 任何可成交亞洲/大小球盤口、CLV、ROI、EV或真實收益證明。

## CI 驗收

```bash
python -m compileall -q ops
python -m unittest discover -s ops/tests -q
```

測試完全使用 synthetic fixtures + local temp archives，不准在CI中抓商業賠率、使用 API Key、下載即場資料、合併正式系統或清除安全閘門。GitHub exact-head workflow 必須通過；原始測試日誌需確認新增案例已執行。獨立 code review、授權與外部證據審核完成前 **勿 merge**。

> `HOLD/DISABLED` 係刻意保留嘅安全結果，唔係可以透過改一個 `verified=true` 布林值解除。

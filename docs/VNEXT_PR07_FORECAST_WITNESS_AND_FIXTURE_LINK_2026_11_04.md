# 足球王者 VNext PR-07：外部前瞻見證驗證／來源資格閘門／逐場證據連結

2026-11-04｜**Draft research only**｜疊加PR #435 → #434 → #433 → #431 → #430 → #429

## 核查過的事實

1. 上述6個上游PR均仍係 OPEN/DRAFT，未合併、未部署；原有V4.1及所有投注狀態不變。
2. `ops/forecast_provenance_audit.py` 同 `ops/ndr_capture_provenance.py` 已使用每次新執行的 `gh attestation verify` + 已驗證Tlog時間（而非保存過的「verified」JSON）檢查**舊版指定產物**。原封存簽章唔自動適用PR-06的新封存檔。
3. `ops/policies/result_sources_v1.json` 經 `ops.trusted_result_evidence._policy()` 固定SHA核對；Bundesliga 2026–27 NDR、DFB、OpenLigaDB、OpenFootball 來源上游獨立性均 `UNKNOWN`，原件重用授權未確立/需逐範圍核查。資料商或caller自行提供的網址、來源group、布林 `licensed=true` 均無授權效力。
4. DFB自動採集／公開原件複製喺現有 `ops/shadow_external_evidence_collector.py` 已封鎖；今次**無新增任何網絡採集、API Key、配額消耗或公開商業原件**。
5. 本公開repo GitHub API `license=null`，唔等於足球供應商授權。
6. GitHub CLI官方 `gh attestation verify --bundle --repo --signer-workflow --source-ref --source-digest --signer-digest --deny-self-hosted-runners --format json` 確認支援驗證；官方強調 **certificate 同 verifiedTimestamps** 係可信身分與時間，`statement.predicate` 由工作流程產生，唔係獨立事實。
   - https://cli.github.com/manual/gh_attestation_verify
   - https://docs.github.com/en/actions/how-tos/secure-your-work/use-artifact-attestations/use-artifact-attestations

## 新增模組 A：`ops/vnext_forecast_attestation_gate.py`

真正執行前需要：

- `root` 內**PR-06實際寫入**且未篡改嘅本地封存 `<sha256>.json`、原檔 SHA256 pin；
- 獨立提供嘅 Sigstore attestation bundle，必須係受信任工作流程**實際對呢個檔案**簽發；
- 外部固定之 GitHub `source_commit`, `workflow_commit`, `run_id`, `attempt`；不可用自述成功報告代替；
- 每次**重新**運行固定命令 `gh attestation verify`，不用shell/網絡程序自定參數或caller指定Signer；
- 精確比對 GitHub OIDC簽署證書：repo、owner ID、workflow path/ref、source/signer commit、run/attempt及hosted runner；
- 比對 verifier 本次回傳 bundle、單一statement/single SHA256 subject（原 seal filename+bytes）、SLSA predicate type；
- 比對**經驗證的單一Rekor Tlog時間**：`forecast_as_of <= local_capture <= verified_Tlog <= kickoff_utc - 10分鐘`，以及Tlog不能比驗證時刻未來超過5分鐘；
- 檔案路徑無symlink、不可超過大小上限，拒絕狀態不明、缺CLI、cert錯配、bundle換檔、閾值後簽署、誤指其他賽事。

成功只表示 `WITNESSED_BYTES_RESEARCH`、`signed_seal_bytes_verified=True`、`external_forecast_time_witness_verified=True`：**指定bytes確實由指定官方工作流程簽署且在記錄開波前留下可信時間上界**，而**唔代表資料來自真正博彩公司/官方、預測正確、實際開波時間可信或已符合資料授權**。

**非常重要：** PR-07保留 signer workflow 路徑
`.github/workflows/football-king-vnext-forecast-attest.yml` **作未來受控簽發器的固定身份契約**。此PR只提供驗證器，**並無虛構該工作流程已存在、已發出Sigstore bundle、已成功實際簽署PR-06封存，亦未加入會自動抓取/簽發未授權資料的workflow**。要有真正簽章必須先獨立審核并實作 trusted producer workflow，於 main 以 GitHub OIDC 真正簽發，喺開波前完成驗證；今次所有正面測試均係**mocked CLI output，唔係真實簽章**。

## 新增模組 B：`ops/vnext_fixture_evidence_link.py`

- `audit_source_access` 只讀經SHA固定的原始來源政策，不接受caller政策文件或授權旗號；按 provider、範圍、操作分開審查。既有來源目前全部`HOLD`。尤其DFB自動採集同原件公開複製永遠明確拒絕（本PR不改現有采集許可）。
- `link_fixture` 使用**同一fixture ID、完全一致的UTC開波時間**，要求已通過有效簽章時間檢查的賽前封存、觀察時刻後真實可見嘅後驗結果、兩個政策內來源觀察比分一致、結果完整身份/受控sha、結果資料時間不早於90分鐘常規時間及不晚於此次檢查時間。
- 返回每場 `forecast_sha256`、Rekor witness UTC、原賽前來源ID/digest、結果兩來源各自 fixture ID/digest、資料來源政策ID，**只含允許衍生metadata，唔儲存/公開商業原件或可成交賠率**。
- 即使有一場結構完整，總狀態必然 `HOLD`：來源上游獨立性、授權、實際開賽及終場真實性未知，絕不算獨立已驗證OOS樣本。
- 缺簽章、結果未到達、來源不同比分、錯賽事、入球資料不能結算、caller自述 `verified=True`、亂填官方IP/原件權限 → 立即拒絕。

## 本PR新測試與尚欠項目

```bash
python -m compileall -q ops
python -m unittest discover -s ops/tests -q
```

全部新增單元測試使用本地PR-06 synthetic seal及mock `gh`回應，針對上述規格重現攻擊型輸入。CI通過僅證明代碼安全判斷正確，不能證明**真實**外部簽章已驗證。不可將陽性mock或 `WITNESSED_BYTES_RESEARCH` 抄入正式放行計數。

後續必須另外完成：
1. 授權清晰嘅 real source producer（有固定源、限制權限及有效fixture ID，無未授權原始資料重用）；
2. GitHub Actions main 上固定受信任簽發器、Sigstore bundle／Rekor 真實時間重驗及公開可檢查的簽章原件，仍不得將簽章等同足球數據真值；
3. 實際官方/獨立來源上游資料及其授權、真實90分鐘賽果及實際開賽可信身份；
4. >300場及12週真實且事前封存同場對照、獨立保持未觸碰嘅樣本外數據及按週不確定度，獨立評審後仍須檢查欠樣/選樣、多重檢定；
5. 真實可成交價、合法結算規則同成本；而家不計EV/ROI/CLV。

**無自動上線、無新增自動付款/投注/通知/外部網絡抓取；所有產物保持 `HOLD/DISABLED`。**


## 2026-11-15：賽果觀測原件 SHA-256 缺口審查與最小修復

**發現：** 原 `link_fixture()` 對 `result_record.source_raw_sha256` 只比較
`result_observations[].raw_sha256` 嘅*caller聲稱值*，但未有讀取原件並
重新計算 hash。兩個一致嘅字串可以係自行抄寫，並非 SHA 真正綁定到原始
觀測 bytes。之前「觀測同意」只表示兩個聲稱分數一致，從來唔足以證明真正
比分、授權、來源獨立或 OOS 認證。

**實際倉庫現況：** 2026-11-15 直接讀取 `main` 嘅
`evidence/settled.json`（Git blob
`c8d8fadf4b7edbe9613d760cde868e96e9bcd4ac`）：
`samples` 有 **104 條**，**0/104** 含 `source_raw_sha256` 或
`fixture_result_source_raw_sha256`，**0/104** 有
`fixture_result_source`。所以現存記錄**唔可以用作已獨立核實嘅賽果
樣本**；本 PR 唔會補造原件、勝負或已驗證旗標，亦無更改正式 main 計數。

**本次 Draft PR-07 研究修復：**
- `link_fixture(...,result_observation_files={provider: local_path})`
  依每一個原始觀測嘅指定 provider 讀取獨立本地檔案、重新計算 SHA-256，
  同該 provider 観測記錄嘅 `raw_sha256` 逐項比較。
- **缺少任何原件就先 HOLD**（`RESULT_OBSERVATION_ORIGINAL_FILES_REQUIRED`），
  原件雜湊錯誤即 HOLD（`RESULT_OBSERVATION_RAW_SHA256_MISMATCH`）。
  同時拒絕 provider/file 錯配、相同 inode 重複冒充兩個來源、symlink、
  非普通檔、異常大小或讀取時被修改。原件最多 **2,000,000 bytes**；
  用受限 fd 讀取，無網絡獲取、無原件複製/上傳。
- 即使 **合成測試原件**真實重新算出一樣 digest，都只代表
  `result_original_bytes_sha256_verified=true`（**本地 bytes 比對**）。
  `original_provider_identity_independently_verified=false`、
  `publisher_independence_authenticated=false`、
  `result_truth_verified=false`、
  `source_access_authorized=false`、
  `eligible_for_model_scoring=false`、`eligible_for_betting=false`、
  `positive_ev_verified=false`、`production_recommendations=DISABLED`。
  未有可信原件上游身份、實際開球、賽果真偽及資料用途授權，不可升格。
- `ops/tests/test_vnext_fixture_evidence_link.py` 新增**七個**合成反例／正面
  案例，測試沒有原件、同大小篡改、更換 provider、原件對得上都唔會放行、
  symlink、缺少其中一個 provider 檔案、用同一檔案冒充兩個來源；測試
  僅使用 ephemeral 本地 synthetic bytes，並未接觸任何真實足球賽果原件。

**TDD 記錄：** 只加測試嘅 commit
`38d8d3e1e23045017334f573ba257a387e2840c0`
已令 GitHub 真實回歸 CI **FAIL**（驗證缺口存在），並非成功驗收。
修正候選為 `b282bf3fdddd98d170e58d14689fa67ad894704d`；
第一次 CI 發現 `pathlib.PosixPath` 唔會通過
`type(path) in (str,Path)` 嘅過嚴輸入型別檢查，故用
`isinstance(path,(str,Path))` 喺
`cc37d8b18ca90d9e90a776494b9f336877b0585b` 再修正。**只有以
最終 HEAD GitHub CI 實際成功為準**；任何紅燈唔可以當合格。

**可驗證嘅界限：** 此變更驗證本地來源 bytes 同 caller 宣稱 SHA 一致，
**唔等於證明本地檔案由指定 NDR／OpenLigaDB 真實發布**。缺乏供應商授權、
實際第三方獨立結果原件、簽章／時間戳及真人審批，正式結果依舊
`HOLD / DISABLED`、獨立認證 OOS **0**、正 EV **未驗證**。
保持 Draft／未合併／未部署，不自我批准或繞過 Issue #439。

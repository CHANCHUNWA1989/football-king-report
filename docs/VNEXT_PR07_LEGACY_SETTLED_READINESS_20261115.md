# PR-07：既有已結算紀錄原件／前瞻證據資格審核（2026-11-15）

**結果：HOLD／DISABLED。** 呢份記錄唔係模型準確率報告、賽果來源身份認證、
樣本外（OOS）獨立評估、第三方資料授權或正 EV 審批。

## 上一階段缺口同本次獨立核查

PR #436 早前已加入逐來源本地賽果觀測原件重新計算 SHA-256。
但 **沒有真實、獲授權、具外部來源身份證明的觀測原件**；現有
`evidence/settled.json` 既有資料只能作回溯描述，不可因此當成獨立
賽果認證樣本。

本次從 GitHub 直接讀取同一個倉庫的**兩個實際不同版本**，
而唔係把研究分支誤當成最新 `main`：

| 項目 | `main` 確切提交 | PR #436 研究分支確切提交 |
| --- | --- | --- |
| Git commit | `2b5c5c2eaf0d87c4c3547b07e85acccfdf687db2` | `26651348c8357d35d5355daa4c4053d7f47be253` |
| `evidence/settled.json` Git blob | `c8d8fadf4b7edbe9613d760cde868e96e9bcd4ac` | `884bfd068e6c6934bab9226088be86e51b2a938d` |
| 檔案大小（bytes） | 91,755 | 57,952 |
| 已結算觀測紀錄 | **104** | **73** |
| 可結構核對紀錄 | **104** | **73** |
| 附有 `source_fixture_identity`（provider + match ID） | **9** | **0** |
| 附有 `forecast_event_id` | **38** | **7** |
| 附有有效 `model_artifact_sha256` | **0** | **0** |
| 附有 `fixture_result_source` | **0** | **0** |
| 附有賽果原件 digest | **0** | **0** |
| 附有實際獨立外部簽章或可重驗賽前見證證據 | **未提供** | **未提供** |
| 真正通過 PR-07 賽果原件身份核實 | **0** | **0** |
| 獲獨立認證的前瞻樣本 | **0** | **0** |

最新 main 案例按聯賽分布為
Bundesliga 45、Championship 19、EPL 13、La Liga 11、Ligue 1 7、
Serie A 9；合計 **104**。此為歸檔觀測分布，**不是**獨立比對過
官方比分的認證分布。

`main` 這份封存檔自述的 `checked_utc` 為
`2026-11-12T17:44:06.378393+00:00`，`results_independently_verified=false`，
`profitability_verified=false`，
`production_recommendations=DISABLED`。這些是**檔案自述值**，
不是第三方不可抵賴簽章或獨立來源確證。

## 實際新增：只讀證據資格閘門

`ops/vnext_legacy_settled_readiness.py` 只接受一份本地 JSON 原件
以及**另外由可信 GitHub 倉庫指定版本查得**的 Git blob SHA-1。
使用 Git blob `sha1(b"blob " + length + b"\\0" + bytes)` 格式核對
傳入的 archive bytes，拒絕原件被換、改動一個 byte、超過 8MiB、
重複 JSON keys、NaN、重複賽事 key、非法概率、非 UTC-aware
時間或錯誤先後次序。

**精確風險界限：** Git SHA-1 一致只建立「bytes 與獨立提供的
Git blob 識別符一致」；不等於 cryptographic publisher signing、
獨立賽果來源身份、真實比賽結果、事前封存時間或資料授權。
如果使用者自編一個預期 blob SHA，並無獨立驗證效力。
本工具**不下載源站、不改動舊檔、不引用 provider API、
不計算回報、從不自動轉正 OOS/EV**。

`ops/tests/test_vnext_legacy_settled_readiness.py` 新增 12 項
完全由標準 Python library 運行的 synthetic 測試；重點包括
相同長度的 archive tamper、填入假的 `independently_verified=true`
或者 `eligible_for_model_scoring=true`、偽裝 provider ID、
假 source raw SHA、時間逆序、概率錯誤、JSON 鍵重複、上限及
`production_recommendations=ENABLED` 硬拒絕。

## 已實際在隔離研究沙盒重播

2026-11-15 UTC，隔離研究環境：
1. 用 GitHub commit `26651348c8357d35d5355daa4c4053d7f47be253`
   下載審核程式與 12 項測試，逐檔與 GitHub 所列 Git blob SHA 核對。
2. 另由**固定 main commit**下載 104 條版本，與其 Git blob
   `c8d8fadf4b7edbe9613d760cde868e96e9bcd4ac` 比對；由 PR #436
   研究 branch commit 下載 73 條版本，與
   `884bfd068e6c6934bab9226088be86e51b2a938d` 比對。
3. `python -m unittest ops.tests.test_vnext_legacy_settled_readiness -v`：
   **12／12 OK**；兩份真實 JSON 經 Python 審核器核對，結果
   **104／104** 及 **73／73** 結構可讀但獨立認證 **0**，
   `status=HOLD`、`production_recommendations=DISABLED`。

由於 PR #451 已有 `ops/audit_existing_1x2_evidence.py` 做
描述性 Brier／Log-loss 回溯分析，本次**刻意不重寫計分引擎**，
只檢查原件身份與外部證據資格，避免使用歷史評分反過來當作
賽前真正預測。

## 重現方式（僅供本地證據審核）

```bash
python -m ops.vnext_legacy_settled_readiness \
  --archive /private/exact-main-evidence/settled.json \
  --expected-git-blob-sha1 c8d8fadf4b7edbe9613d760cde868e96e9bcd4ac
```

必須自行從**上述固定 main Git commit**提取完整原始 archive bytes，
不要拿 PR #436 舊分支版本配 main 的 blob hash；兩個版本絕不互換。
GitHub Actions 只執行本地 synthetic tests；以上兩份真實 archive
之實際重播由獨立研究沙盒執行。**冇將任何外部賽果源站原始檔案、
第三方機密、私人授權憑證加入本 PR。**

## 後續必要關口

1. 先處理真正可提供授權賽果原件的獨立供應商，取得各 fixture
   provider event ID、捕獲時間、來源文件原始 bytes 及
   獨立出版身分驗證；**不能用原 archive 欄位自行填資料來通過**。
2. 另取得事前封存的預測檔，使用真的受信任簽發器與
   Sigstore/Rekor timestamp 重新驗證，而非 mock `gh` output。
3. 對同場比分／身份／時間／賠率與資料使用條款做人工獨立審查，
   之後才可能設計預先註冊的長期前瞻比較與不確定度統計。
4. `main` 分支保護、獨立 reviewer 同其他治理要求見
   [Issue #439](https://github.com/CHANCHUNWA1989/football-king-report/issues/439)。

此 Draft PR 不合併、不部署、不得將 104 或 73 列為
`certified_prospective_rows`、不得宣稱 ROI／正 EV。
**HOLD / DISABLED，獨立認證前瞻樣本仍然 0。**


## 2026-11-15：跨版本歷史歸檔漂移審核（append-only）

新增 `ops/vnext_legacy_cohort_delta.py` 同
`ops/tests/test_vnext_legacy_cohort_delta.py`（**13 個 synthetic tests**）。
唔修改任何一份 `evidence/settled.json`，亦無新增網絡下載。

**用 GitHub 精確 Git 版本實際比對：**

- PR #436 嘅舊分支版本：Git blob
  `884bfd068e6c6934bab9226088be86e51b2a938d`，
  **73** 條已結算研究紀錄；
- main（commit
  `2b5c5c2eaf0d87c4c3547b07e85acccfdf687db2`）：
  Git blob `c8d8fadf4b7edbe9613d760cde868e96e9bcd4ac`，
  **104** 條已結算研究紀錄。

於隔離研究環境由 GitHub immutable commit 下載兩份**真正歸檔 bytes**，
先逐份按 Git blob SHA1 公式核對，再通過既有
`vnext_legacy_settled_readiness.audit_archive_bytes()`
完整檢查時間、概率、key 同禁用狀態，最後按 fixture key
比較**所有歷史欄位的完整、確定性 JSON digest**。
測試結果：

| 項目 | 實際核對結果 |
| --- | ---: |
| 舊分支總紀錄 | 73 |
| main 總紀錄 | 104 |
| 重疊 fixture key | **73** |
| 全欄位完全一致的舊紀錄 | **73** |
| 舊紀錄改動 | **0** |
| 舊紀錄被移除 | **0** |
| main 新增紀錄 | **31** |
| 舊紀錄是否保持原順序、作為新版前 73 條 | **是** |
| 狀態 | **APPEND_ONLY_BYTES_CONSISTENT_RESEARCH / HOLD** |
| 認證前瞻樣本 | **0** |

即係今次可以由**實際檔案**支持「舊 73 條未見改動，新增 31 條」
呢個*相對歸檔一致性*結論，唔係由 git log、自述成功文字推測。
新增 31 條嘅 kickoff UTC 由 2026-11-03 至 2026-11-08，
不代表當時擁有可證明事前來源資料。

另外用相同真實 main 104 條歸檔做**兩個實際反例**：
1. 把原舊樣本其中一條 `y` 結果改成另一結算類別，
   為篡改後歸檔**重新計算有效 Git blob SHA**再審核；
   仍回傳 `HOLD_HISTORICAL_RECORD_DRIFT`，
   `modified_overlap_rows=1`，CLI exit 1。
2. 把原舊首兩條樣本互換次序，**再重新計算有效 Git blob SHA**；
   `modified_overlap_rows=0` 但 `older_rows_preserved_as_prefix=false`，
   同樣 exit 1，唔會當成 append-only。

只靠「原本 SHA 不匹配」不足以防止來源在新版本有效更新 hash 後
靜默改寫歷史內容，因此特別新增**逐個舊 fixture 全欄位比對**
同**舊次序不得移動**規則。13 個 synthetic tests 亦覆蓋
篡改比分、篡改原始 `p`、亂填 `independently_verified`、
刪除／插入／重排歷史資料、重複 key、錯誤預期 blob、
非法時間、造假新資料驗證旗號。

**研究用 CLI（兩個 Git 版本的 bytes 需自行獨立取回）：**

```bash
python -m ops.vnext_legacy_cohort_delta \
  --older /private/old-pr436/settled.json \
  --newer /private/current-main/settled.json \
  --expected-old-git-blob-sha1 884bfd068e6c6934bab9226088be86e51b2a938d \
  --expected-new-git-blob-sha1 c8d8fadf4b7edbe9613d760cde868e96e9bcd4ac
```

**非常重要：** 指定 Git blob SHA 驗證「檔案版本身份」，
係相對內容完整性，**唔係外部第三方供應商簽章**；
caller 自己偽造 SHA/檔案並無獨立證明力。
有 73 條內容保持不變，**不代表其賽果、模型、來源原件、
預測封存或資料授權已獨立證明**。
正式結果仍 `HOLD / DISABLED`，
`certified_prospective_rows=0`，
`positive_ev_verified=false`，
PR #436 保持 Draft／未合併。

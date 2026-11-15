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

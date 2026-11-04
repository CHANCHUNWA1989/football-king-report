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

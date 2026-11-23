# VNext｜OpenLigaDB 單主機聯賽共用限速閘門（2026-11-23）

> **2026-11-23 後續安全更新（PR #547 研究鏈）：原舊版 `paced_capture_once()` 在 `getter=None` 時會直接 HOLD，舊 `--manual-one-shot` CLI 已被停用。請採用 #546 的受控變更標記條件式 CLI；本文描述的舊入口屬歷史架構，而非當前可用直接下載指令。**

## 實際缺口與定位

PR #538 建立單場 OpenLigaDB 原始 HTTP 回應一次性私有收集器，但其手動 CLI 只有「無自動排程」限制，**並無多個合作進程共用的同聯賽請求間隔**。如果兩個 iPhone 前端或工作程序不小心在同一秒各自啟動，原 CLI 可以直接重複呼叫官方 API。官方 [2026-11-07 使用條款](https://www.openligadb.de/en/terms-of-use) 指明即場**每聯賽**約 30–60秒一請求，不是每場／每部手機配額，並要求用 `getlastchangedate` 作低成本變更檢查、減少完整 GET；超時/429/5xx 不應立即重試。

本 PR 只修正一個獨立問題：**同一 POSIX 主機、同一專用安全私有資料夾的所有合作程序**只能通過一把 `fcntl.flock` 鎖及一個持久共享時間閘。無排程，無背景輪詢，無自動重試，無直接正式投注。

## 變更

- 新增 `ops/inplay_openligadb_league_pacing.py`：`paced_capture_once(match_id,private_root,getter=None,now=None)`。
  - 原生 matchID 先驗證；私有根目錄須預先存在、屬操作者且權限 0700，並位於所有 Git repo 以外，沿用 PR #537 及原專案 `private_response_capture` 之 NOFOLLOW 安全目錄檢查。
  - 共享同聯賽 `bl1` 的固定 ` .openligadb-bl1-pacing.json` 內部檔案（實際 filename 無空格）。以 `O_EXCL/O_NOFOLLOW` 建立 0600 普通單連結檔，再由 `fcntl.flock(LOCK_EX|LOCK_NB)` 防止兩個程序同時跨越。讀取時強制 typed schema、完整 canonical JSON、原 inode 身份、權限、時鐘，檔案空白／遭竄改／symlink／hardlink／權限弱化／比之前時間倒退，均拒絕。限速檔案本身沒有網絡憑證或 raw body。
  - **HTTP 前先記錄保守600秒冷卻**（即使出現網絡失敗、HTTP429、解析失敗或程序崩潰，都不能直接立即重試）。單場 `capture_once()` 成功及私有 byte-readback 成功後，才將下次最早呼叫縮至今次開始後**90秒**。若任何寫入或 fsync 失敗，殘存 invalid state 令往後呼叫 fail-closed，不嘗試默默修補。
  - 相同私有 root 但不同 matchID 都共享單一 `bl1` 配額；全部操作全程以**一把主機本地排他鎖**控制，無 waiting busy-loop，忙碌即 HOLD。
  - 所有回覆保留 `RESEARCH_ONLY / HOLD`、`production_recommendations=DISABLED`、`certified_forward_samples=0`、`positive_ev_verified=false`、`eligible_for_model_input=false`。
- 修改 `ops/inplay_openligadb_one_shot.py` 的手動 CLI：明確改用 `paced_capture_once`；原本 `capture_once` 保留只作既有研究／依賴注入測試，**不得直接從定時 job 呼叫繞過限速器**。
- 新增 `ops/tests/test_inplay_openligadb_league_pacing.py`：14項 synthetic 無網絡測試，包含不同場次共用90秒窗、失敗600秒冷卻、一主機兩個 threads 競爭只得一個 GET、時鐘倒退、錯 ID、偽造／損壞共享記錄、symlink/hardlink、非私有目錄以及手動 CLI 必須經共享閘。

## 安全界線（必讀）

1. 此限速閘門 **不是跨主機、跨機房、跨雲 GitHub runners、跨多個私有根目錄、跨容器或對整個共享 IP** 的集中式節流；所有其它來源客戶端亦必須自律遵守供應商配額。使用者不可喺多部 iPhone 或多個伺服器直接調用本模組當作已經有全域鎖。
2. `getlastchangedate` **尚未接入**。因為這輪只處理手動單次 GET，唔可以宣稱已做到官方完整建議嘅「變更後先取 full response」。要變成排程式輪詢必須另一輪加入共享狀態、season/group 確認、change token 處理、相同時點安全快取，再完成供應商服務條款審核。**現在仍禁止自動排程**。
3. 研究 CI 只使用自己合成 `matchID=12345`、當場 fake JSON 同注入 getter，**唔向 OpenLigaDB 發出任何真實請求**；無產生真實賽事樣本、官方已認證比分、紅牌、真實xG、盤口、EV 或模型提升證據。
4. 本地鎖可被同一 OS user 有意刪改；lock record 並非不可篡改時鐘。操作者需保持私人目錄及進程管理安全，不應用它作 TEE、TSA、Sigstore/Rekor 的替代品。
5. 此 PR 純研究增量，疊加 #538→#537→#535→#533→#532→#531→#530→#529 仍未通過獨立審查及依賴合併。原先真實模型 PR #433 也仍未獨立合併。絕不能合併此 PR 直接跳過上游研究依賴。

## 驗收

```bash
python -m compileall -q ops
python -m unittest discover -s ops/tests -q
```

需查看本 PR 最新 **exact HEAD** 的 Github safety (3.11+3.12)、regression、ledger、stress 及 validate 全通過，並有獨立 code review 後才可考慮研究依賴順序合併。

**下一個關卡**：在獲授權、一台真正受控服務器上新增 `getlastchangedate/bl1/{season}/{groupOrderId}` 與變更條件 GET 的最小實作，對每個 league/season/group 封存 token、對上游429/5xx 實際退避。然後才係第二個來源、外部可信時間、真正可驗證的前瞻樣本。無任何解鎖正式下注／正EV資格。

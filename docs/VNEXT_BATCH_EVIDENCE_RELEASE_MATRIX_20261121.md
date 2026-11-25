# Football King VNext｜一次過整合研究驗收包（2026-11-21 HKT）

**一份 Draft PR、同一整合分支、統一回歸測試、最終 HOLD。**

## 來源、範圍與責任

此分支從 `main` commit `79d38fbbc55a3025b41c4631dc545282ac7d2c37` 建立。集中納入以下現存、分別經 CI 驗證的研究工作，不覆寫任何真實原始賽果、收據、模型訓練數據或下注 ledger：

| 起始 Draft PR |來源 head SHA|整合內容|仍不具備嘅證據|
|---|---|---|---|
| #506 | `476e6f6016c999cf28224aa51889e526cb17ac81` | private response SHA pin、賽前 forecast＋quote 原始 bytes、120秒新鮮度、RFC3161 原始 manifest 校驗、本機 E2E replay | 第三方 TSA policy、真實 model/provider origin、可成交盤口 |
| #502 | `c7600d21739506b9077af84ca2f45c9bd09665b8` | duplicate identity 全隔離；唔畀無效／重複 evidence 被任意 first-wins | 具來源真實可信的前瞻配對樣本 |
| #501 | `d4b6c67bd5111226ca2877dc4be663ea8450baac` | 0.25 亞洲盤分段結算、大小球精確 EV 及單元測試 | 實際莊家盤口、事前密封概率、已核實 EV |
| #463 | `531722a719a6186ee6b0614d500ac545b1a81fa1` | 研究版 RFC3161 `openssl ts` 驗證 | TSA 公信力、CA/政策獨立批准 |
| #460 | `ac275e1e129b86ccd9d917663c3aed1280f1955f` | same-case original A/challenger 及 pairwise OOS 漏洞審計 | 不回填真實前瞻成對樣本 |

**冇自動合併**以上五個原有 Draft PR；它們保持獨立審核歷史。此分支從各上列 head 的 UTF-8 文字檔案建立「整合候選」，並不構成合併核准或任何人手代簽。

**尚未整合、必須獨立審核：**
- **#464 TheSportsDB 私密賽果**：keyholder 原件解密、來源身份及二個真正上游獨立 FT 精確比分核驗未達到資格；不可將兩個舊公開 candidate 當作認證。
- **#465 team identity／home-away role**：大量模型原始資料、別名、訓練功能與 CI；需要獨立模型及跨季實驗審核，不能一次過推入正式模型。
- **#458 penaltyblog / soccerdata / 資料來源擴充**：研究適配器與本地對比，尚欠真實樣本外成對比較和授權來源接入；留喺 Draft。
- **#429–#434**：歷史 VNext 研究 chain；不以互相依賴嘅 PR DAG 作正式升格捷徑。

## 單次、可重現執行

CI 檔 `.github/workflows/football-king-batch-evidence-integrity.yml` 對同一 commit 執行：

1. `ops/tests/test_first_case_*.py`，包括只用虛構來源、臨時自簽 TSA 的**真實 OpenSSL** 加密學練習，以及私密原件校驗、重播中途調包、回填 hash、過期報價。
2. `test_forward_settlement_audit`、`test_asian_threeway_ev_research`、`test_total_goals_ev_research`、`test_value_research_pipeline`；錯誤四分之一盤 EV 不能視作二元全贏全輸，重複樣本不得由排序/結果挑選。
3. `test_rfc3161_timestamp_gate`、`test_paired_challenger_comparison`、`test_paired_snapshot_alignment_gate`、`test_sealed_evidence_integrity_audit`。
4. 最後以 `ops/vnext_batch_research_readiness.py` 讀取倉庫安全公開摘要，任何自報「已核證」或「正EV」只當作 claim，不計入 certified。CI 以獨立 assert 保證 `production_recommendations=DISABLED`、`independently_certified_forward_cases=0`、不可下注。

CLI（本地或私密 Actions runner；只讀，無網絡或可成交報價下載）：

```bash
python -m ops.vnext_batch_research_readiness \
  --collection market/collection_status.json \
  --market-summary market/private_summary_latest.json \
  --settled evidence/settled.json
```

此命令輸出只含**研究計數及驗收阻塞**，絕不輸出 sportsbook 報價、球隊 fixture ID、真正 forecast probabilities、憑證私鑰。

## 已有真實倉庫摘要（注意各來源時點不同）

- `market/collection_status.json`：2026-11-21 16:12 HKT 採集狀態 `HOLD`、原因 `FREE_QUOTA_GUARD`，API free quota `used=359`、`remaining=141`。唔等於已具 141 筆可成交報價。
- `market/private_summary_latest.json`：2026-11-21 01:58 HKT，匿名研究 `RESEARCH_ONLY=750`，市場 `h2h`，`VERIFIED_VALUE=0`，`quotes_are_executable=false`，**唔含單場原始盤口**。摘要聲稱當時 `settled_cases_in_archive=104`。
- `evidence/settled.json`：2026-11-21 10:56 HKT，`n=105` 條**未獨立核實**研究結算觀測，`results_independently_verified=false`；與舊摘要的104只是不同時點，**不得相加計成209**。
- 在未建成獨立、具來源可驗證嘅 certified prospective admission 之前，無論最新 public aggregate 顯示幾多，**independently_certified_forward_cases = 0 / 300**，不宣稱勝率、ROI 或正EV已提高。

## P0 外部證據交接（不能靠修改程式偽造）

- [ ] **真正事件身份**：模型 forecast raw、provider-native event、官方 KO、別名/換隊史，必須原件可還原；#465 先完成身份修正再准計樣本。
- [ ] **可信第三方時間戳**：原始 manifest bytes 存在於可信 pre-kickoff 環境；獨立 RFC3161 token、CA path、policy OID、簽發當刻及可用來源審計。
- [ ] **實際可成交報價**：指定 bookmaker、market、selection、line、stake-limit、來源原始回應 bytes；報價不得由已公開研究合意價替代。現有 The Odds API research `h2h` 非 executable；未取得 `spreads` / `totals` 原件。
- [ ] **完場兩來源**：獨立上游、原生 ID、90分鐘精確主客入球，官方紅牌為先，取消／加時／VAR 不得混淆。
- [ ] **回測與升格**：至少300獨立 certified 前瞻樣本、符合12週及跨聯賽分布門檻、paired OOS Brier/log-loss/Asian market ROI 或 EV 信賴區間；只有真正獨立來源合格時先考慮另行正式評審，絕不自動切換。

## 不應執行

- 不得將 CI 綠燈、假 TSA、handwritten proof flag、previously-settled public scores、匿名 quota summary 當作已認證樣本。
- 不得自動 merge `main`、啟用下注或調整真金白銀 stake；尤其不得使用未核實即時盤口或宣稱 `odds>=1.8` 正EV。
- 本批整合係 **研究 Draft／HOLD**，需要獨立 code review + 真實外部證據後才能另行審議。

## iPhone 操作方式

在 iPhone 的 GitHub App／Safari 開啟此 Draft PR 的 **Checks**，查看新增 `batch-originals-ev-tsa-oos-hold` 以及原有 regression / safety / validate / ledger 逐項結果。若工作流程成功，只代表合成測試及研究邊界合格；唔會生成正式買賣信號。

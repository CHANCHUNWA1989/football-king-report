# 足球王者 V：第一階段審計（2026-11-06 UTC）

結論：**HOLD／DISABLED**。現有研究架構可沿用，但尚未具備獨立認證的賽前封存、最終賽果及可成交盤口證據，不能聲稱預測優勢或正 EV。今輪先處理一項可獨立驗收的盤口身份修復，其他工作按下列關卡推進。

## 範圍及可追溯起點

- 研究起點：[Draft PR #451](https://github.com/CHANCHUNWA1989/football-king-report/pull/451)，commit `cb34d5903a68fa9453dac96a82e1180b2910d8a1`。
- clone 時 main：`c843cf0afc77cbfbee68823179972bf39eed9eba`；本次新分支從上述研究起點建立，沒有重寫 #451 或 main。
- 新分支：`research/phase1-audit-settlement-20261106`；新 Draft PR 以 #451 研究分支為 base，保留依賴關係。
- 已讀 AGENTS.md、README、部署狀態、核心安全更新及待辦清單。舊文件中的數量是歷史快照，本報告以實際檔案重新核對。
- 三路並行審計：結算／時間戳、資料／模型／回測、CI／安全／手機監察。盤點 64 個 workflow 及 256 個 ops 測試檔；深入檢查下列資料入口及安全邊界，並跑現有回歸。這是靜態程式及存檔審計，沒有滲透測試、外部來源重新認證或所有平台實機驗收，不能宣稱已排除所有風險。
- 沒有查詢投注或收費 API、沒有下載新商業資料、沒有更改正式設定、合併或部署。

## 實際資料盤點

以下是研究起點的公開儲存庫檔案，不是新取得的即時市場資料。SHA256 僅綁定受審檔案，不證明資料真偽或賽前存在。

| 檔案 | SHA256 |
|---|---|
| `evidence/settled.json` | `20bd00163acf6d6bc4c5611cd0e63070c589b17e327f02c465dec694ee1c755e` |
| `market/latest.json` | `7903fc454fc516d6aff2481d5ed47fbb0650a651872b92ffae7d5239facf13de` |
| `market/private_summary_latest.json` | `816d1bc821b74bffc9c998efd9a0abf73e075725a2dd8f0c87252f23b9fecabf` |
| `sources/seven_quality_gates_latest.json` | `b17c8ab8cb5ad40c5adef86a665418ef789923125f73948e57f4373e1e27b031` |

重現指令：

```bash
python ops/audit_existing_1x2_evidence.py evidence/settled.json
python ops/audit_existing_market_consensus.py market/latest.json
```

- 77 場已結算研究樣本（2026-10-09 至 2026-11-04），獨立認證賽果 **0**；77 場全部缺模型檔案 hash、結果來源及來源賽事身份。通過結構檢查不等於通過來源驗證。
- 分布：德甲 36、英冠 16、英超 9、西甲 8、法甲 5、意甲 3。不能按細樣本聯賽排名挑選策略。
- `market/latest.json` 為 108 場去水 1X2 共識；來源時間 `2026-11-05T14:21:34.881704+00:00`，requested markets 僅 `h2h`。108 場全部欠逐公司可執行賠率、亞洲讓球線、大小球線及獨立擷取收據。
- 私人報價**公開摘要**記錄 4,101 筆研究觀察，但 `VERIFIED_VALUE=0`、`quotes_are_executable=false`、`verified_bets=0`。此處沒有讀取或公開私人原始報價。
- 七關卡：1 PASS、5 PARTIAL、1 HOLD。已有資料收集及監察架構，但不能當成獨立認證完成。

77 場**未獨立認證**結果的描述性分數（multiclass Brier 為三方向平方誤差之和；Log Loss 用自然對數）：

| 指標（較低較好） | 模型 | 同場市場共識 |
|---|---:|---:|
| Brier | 0.641648 | 0.589440 |
| Log Loss | 1.059073 | 0.986501 |

此樣本中模型落後市場；不是已認證 OOS、校準或真實盈利證據。缺可執行價格，**ROI／CLV／亞洲盤正 EV 不可計算**。沒有以合成測試補足真實樣本或編造信賴區間。

## 發現、優先級與驗收方向

程式位置以研究起點為準；本次修復後行號可能移動。

| 編號／優先級 | 可重現發現／程式證據 | 影響與驗收要求 |
|---|---|---|
| A01／P0，本輪修復 | `ops/the_odds_api_adapter.py:73,81`：兩隊及 outcome 名稱缺失時，`None` 相等，錯誤生成主隊讓球報價；同名兩隊也有歧義 | 拒絕缺失、非字串、空白、相同主客隊；選項須精確匹配供應商原文；正常客隊與主隊盤口方向不變。詳見驗收報告 |
| A02／P0 | `ops/frozen_forecast_join.py:76`、`ops/snapshot_validation.py:101` 使用原始時間／數值字串去重；同一時刻 `12:00Z`／`20:00+08:00`、同盤 `2.5`／`2.50` 可被重複計數 | 用正規化 UTC instant 及數值去重；保留原文供溯源；真實不同快照不應誤刪；不得改寫既有封存 |
| A03／P0 | `ops/the_odds_api_adapter.py:78` 把歷史供應商 snapshot `timestamp` 寫成 `captured_at` | 分開來源快照、莊家更新、市場更新、實際擷取、預測凍結及開賽時刻；不從歷史 timestamp 推定真正擷取時間；缺收據不得通過賽前認證 |
| A04／P0 | `ops/asian_settlement.py:42-47` 接受負 total；`settle('total','over',-1,0,0,2)` 返回 `1` | 統一拒絕負總入球線；保留負讓球合法行為；加入贏半／輸半及串關回歸，防止非法資料生成收益 |
| A05／P1 | `ops/asian_settlement.py:17` 受 Decimal context 影響，`2.50000000000000000000000000001` 被當成合法四分線 | 不經四捨五入驗證線值，限制合理輸入精度；跨 adapter／snapshot／結算一致 |
| A06／P0 | `ops/prematch_evidence_capture.py:32-44,68` 僅驗呼叫者 metadata、hash 原始 bytes、禁止同一路徑覆寫 | 本地 hash／`open('x')` 不能阻止另存回填。沿用現有 provenance／witness 架構，綁定事件、內容、模型 hash、訓練截止及外部時間收據；拒絕賽後新增或修改；原 A/B/C 不重算 |
| A07／P0 | `ops/frozen_forecast_join.py:82-87,117-131` 只按 event_id 接比分，正確保留未認證旗標；`ops/forward_validation.py:358-376` 仍有球隊白名單及 ±45 分鐘／日期配對 | 認證入場需來源原生 ID、賽果原件、FT90／加時／互射十二碼範圍、完場狀態、擷取時刻、獨立出版者及衝突隔離；結構 join 不能代替獨立驗證 |
| A08／P0 | 主要公開市場檔只有共識；現有私人擷取／加密封存與配額保護可沿用 | 在有授權的私人存放區保存博彩公司、事件 ID、market／side／line／odds、來源識別、原始回應及時刻；審查額度與保留權；不得把商業原件推上公開倉庫。不是再造另一套 collector |
| A09／P1 | `ops/backtest_evaluation.py:33-73` 僅切掉初始時間段，沒有訓練來源／市場對照／CI，正確固定 OOS=false | 沿用 `offline_1x2_validation.py:44-60` 校準工具及 `model_evidence.py:139-150` 週區塊配對 bootstrap；鎖定時間切分、同場同截止市場、Brier／Log Loss／校準／ROI 的定義及區間；未達證據量不可聲稱優勢 |
| A10／P1 | `ops/shadow_forecast.py:263-285,463-465` 已有聯賽收縮 Poisson；`ops/lineup_guard.py:88` 是結構檢查 | 正選／傷停、休息日／賽程密度及盤口變動須 point-in-time 來源與模型實際使用證明；用獨立 challenger ID 做消融及樣本外比較，不能事後改 A/B/C |
| A11／P0 release blocker | [#439](https://github.com/CHANCHUNWA1989/football-king-report/issues/439) 仍 open：main 保護、無 bypass、獨立人手審核與可驗證 CI 未獲所需證據 | 本輪未修改 repository settings，未重新認證遠端分支保護。須由擁有人／安全管理員處理並獨立核對；助理程式覆核不等於獨立人手放行 |
| A12／P1 | `.github/workflows/football-king-iphone.yml:48,51-55,635` 手動 workflow_dispatch 可選非 main 分支並部署 | 後續獨立安全工單限制部署分支／環境；本輪不 dispatch、不部署。研究分支 push／PR 本身不觸發 Pages |
| A13／P1 | `football-king-ci.yml:25` 與 `football-king-regression.yml:21` 都叫 regression | 沿用既有治理研究工作，核對唯一 check 身份及 strict required checks，不以名稱模糊匹配放行 |
| A14／P2 | 64 workflow 中有 126 個 uses 非 40 位 commit SHA；Repository Safety Check 只做 AST＋tests，未見完整 secret／dependency／CodeQL workflow | 分批固定 Action SHA 及增加合適掃描；這不表示已發現洩露。Python 主要標準庫；age 安裝器已有大小及 hash pin，不能概括為依賴全無驗證 |

## 結算及現有架構評估

- 常規合法的亞洲讓球、大小球四分盤及串關 stake-weighted gross factor，現有測試未見算式回歸；非法線值與輸入驗證問題如 A04／A05 另案處理。合成測試只驗算式。
- PR #451 的 `asian_settlement` 主要連到 `backtest_evaluation`／`parlay_settlement` 及測試；每日手機流程仍經 `handicap_forward_pipeline` 使用舊 `asian_handicap_research.grade`。尚有其他結算重複實作，應先做相容性矩陣，再逐一收斂，不能宣稱新引擎已全面接入正式流程。
- 既有 `production_gate.py:119-124` 及 `shared/execution_guard.py` 保持 DISABLED／禁止 live execution。測試通過不能開閘。
- 手機監察已存在：`mobile_dashboard.py:105-125,283-306` 有時效／賽前檢查、DISABLED 驗證、每分鐘與 Safari 返回檢查，來源字串以 textContent 輸出。後續在此架構補上來源新鮮度、排除原因、獨立結果覆蓋、盤口／模型版本及 CI 證據；本輪沒有部署新網站或宣稱 iPhone 實機測試完成。

## 分階段路線與放行條件

每項獨立工單保留程式、失敗重現、測試、精確 commit CI 及驗收報告；所有階段維持 HOLD，合併／部署不在本次授權範圍。

1. **階段一（本輪）**：完成系統審計，修復 A01。驗收是正常盤口方向不變，歧義身份 fail closed，時間閘門也不能繞過，回歸與 Draft PR CI 可查。
2. **階段二（P0 核心）**：A02–A05 分成可單獨驗收工單；核對五段結算、串關、UTC／時區等價、重複與錯誤盤口。不得同時改模型權重。
3. **階段三（證據鏈）**：A06–A08；先核實授權與實際可用配額，沿用私人原始資料封存與來源接駁。若缺真實歷史賽前預測，開始前瞻收集，不能回造歷史。獨立結果認證未完成不得入認證回測。
4. **階段四（統計驗證）**：鎖定 cohort／訓練及測試截止，至少達既有 300 場、12 星期、4 聯賽各 40 場的證據門檻，再做同場同時市場比較及區間；達數量也不自動證明有優勢。未認證樣本只能描述性分析。
5. **階段五（模型與監察）**：A10 的新 challenger、消融、聯賽分層與漂移監察；沿用手機面板。研究篩選器須真實 odds ≥ 1.80、用相應分布計算淨 EV（含走盤／半贏半輸），缺任何證據即排除；驗證完成前只供研究，不能輸出正式投注推薦或注碼。
6. **安全依賴**：A11–A14 平行處理，獨立審核及 CI 不得被測試旗標或自簽 verified 欄位取代。

## 本輪測試起點

Python 3.12.14。修改前 `python -m unittest discover -s ops/tests -q`：2,487 tests OK，16 skipped（缺本地 pinned age）；跳過不算通過。具體修復、修改後測試及 CI 記錄見 [A01 驗收報告](phase1-a01-acceptance-2026-11-06.md)。

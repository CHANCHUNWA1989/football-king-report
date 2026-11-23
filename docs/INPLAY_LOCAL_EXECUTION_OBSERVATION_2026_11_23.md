# 足球王者 VNext｜即場候選模型本地執行觀察（2026-11-23）

## 定位、依賴及安全
本次只新增獨立 **研究用途** 的本地執行觀察器，不是真實獨立時間見證、正式前瞻收據或真實 PR #433 模型驗收。疊加 PR #530（同時點聲稱配對）→ PR #529（剩餘時間 Poisson 基準）；**三個 Draft 尚未獨立審核及合併**。PR #433 仍未合併，還依賴 #429→#430→#431。不可從本 PR 嘅合成測試聲稱 #433 真正曾於某場賽事執行。

## 實際新增
- `ops/inplay_pair_execution_observation.py`：`observe_local(case, challenger_snapshot, candidate_callable)`。
- `ops/tests/test_inplay_pair_execution_observation.py`：純合成正向、負向及對抗測試。

### 執行與防錯
1. 嚴格先用 #529 基準驗證案例，若 HOLD 即不調用候選。
2. 候選必須係已由受信任本地程式提供嘅 **Python callable**，唔係外部輸入嘅 JSON「模型結果」。研究工具冇 CLI 自動載入模型、唔下載任何程式、唔接觸 API。
3. 開始呼叫之前，先校驗賽事 ID、開賽 UTC、同一決策 UTC、90 分鐘鐘點、比分、紅牌、賽前主客入球率和賽前時間；當 event proof 帶 final_score／odds／roi 等賽後或市場欄位，**在呼叫之前 HOLD**。
4. 把快照深複製傳入本地 callable，**只呼叫一次**，即時記錄本機 `started_utc` / `finished_utc`；異常不重試、不顯示可能包含秘密嘅 traceback 或錯誤文字。
5. 呼叫後校驗候選有冇修改快照、原始輸入有冇變動；利用 PR #530 模組完成聲稱配對。只對通過者輸出原始輸入和返回物件的 **本機自計 SHA256**，以及三向概率差異。
6. 即使本機確曾呼叫函式，仍保留 `candidate_implementation_authenticated=false`、`genuine_pr433_execution_proven=false`、`externally_witnessed=false`、`formal_model_comparison_allowed=false`、`certified_paired_samples=0`、`positive_ev_verified=false`、`production_recommendations=DISABLED`。這些旗標**不能**靠自填 JSON 升級。

## 不能宣稱
- 本地程式呼叫只能觀察「某個 caller-supplied callable 被呼叫一次」。因候選函式由呼叫者指定，無法獨立證明其檔案、函式位元組、安裝來源、PR #433 真實版本或模型能力。
- UTC 時間係本機自行量度，不係外部 TSA、Sigstore/Rekor 見證；GitHub commit/自計 SHA 亦唔係第三方賽前存在性證明。
- 所有測試使用合成案例，冇真實雙來源賽事事件、官方紅牌、實際 xG、可成交賠率、樣本外勝率、EV 或 ROI。
- **無法從未合併的 PR #433 候選導入真正模型執行**；如果 PR #433 合併並經獨立審查，未來需在受信任隔離環境由已核實檔案來源直接導入、校驗實際模型程式碼雜湊，才可討論更強的執行來源保證，仍不會自動解鎖投注。
- 真實前瞻驗收仍要求相同 PIT、原生事件 ID、合法來源、可靠賽果及市場基準、≥300獨立場次／≥12週／≥4聯賽各≥40場，配對 Brier/Log Loss、校準及置信區間；且正式推薦要經額外人工審核。

## 驗收指令
```bash
python -m compileall -q ops
python -m unittest discover -s ops/tests -q
```
新模組無外部套件／網絡，至少包含：已呼叫一次、純回放結果拒絕、過期紅牌／錯誤比分時不呼叫、賽後資料混入不呼叫、函式修改輸入後 HOLD、异常不洩漏秘密、偽造概率／不合法輸出 HOLD、輸入保持不變。本輪仍需 exact-head CI + 真正獨立 code review 才可考慮按依賴順序合併。

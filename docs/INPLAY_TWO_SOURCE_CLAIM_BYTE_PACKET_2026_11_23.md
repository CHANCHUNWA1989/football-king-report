# 足球王者 VNext｜即場雙來源「聲稱位元組」截點封包（2026-11-23）

## 實際定位

研究疊加鏈：PR #529（剩餘時間Poisson）→ #530（同時點聲稱比較）→ #531（本地函式呼叫）→ #532（固定PR #433原始碼的合成 smoke）→ **本 PR**。

現有另一條尚未合併嘅研究鏈：
- PR #429：point-in-time 特徵可用時間截點
- PR #430：比分、紅牌、VAR事件的聲稱雙來源一致性
- PR #463：RFC3161 TSA token 的離線驗證研究
- PR #506：賽前原始預測與盤口位元組綁定

**本項獨立增量**：將兩份可疑來源嘅已正規化 JSON「聲稱文件」保留成原始輸入位元組進行 SHA256 對應，檢查同一賽事及時序，產出無密鑰、無 raw payload、不可升級嘅研究審核封包。它不複製 #430 的事件 revision-history 共識，不用 #463/506 來偽稱第三方已認證，也不允許下游用此輸出作真實模型輸入。**本模組不會接觸或下載實際來源網址。**

## 語義必須明確
- 所謂 `raw_claims` 指 **caller-supplied normalized claim JSON bytes**，**並非**經獨立見證嘅 FotMob/Sofascore/Flashscore 官方或原始 HTTP response bytes。即使 provider URL 指向合法域名，都不等於該提供者曾發送相關內容。
- 允許來源「聲稱名稱」fotmob、sofascore、flashscore；要求任意兩個不同聲稱發佈者。**不同名稱唔保證上游來源真正獨立。**
- `source_updated_utc`、`captured_utc`、`received_utc`、`identity_sealed_utc` 都係文件中的聲稱；即使互相時序合理都可事後偽造。代碼只負責 fail-closed 結構檢查，不應解讀成 RFC3161、Sigstore/Rekor或實時捕捉已成立。
- 只有兩份聲稱文件都包含同一 fixture ID、league、home/away stable ID、開球 UTC、同一比賽階段、分鐘、比分、紅牌數，且沒有未決VAR，先標示 `RESEARCH_ONLY`。其他情況 `HOLD`。
- 任意額外 `xg`、`odds`、`final_score`、`api_key`、`authenticated` 等欄位直接被嚴格 schema 拒絕；報告只列 metadata 和自算 hash，**不記錄任何原始位元組或秘密**。
- 輸出 `packet_sha256_unattested` 係本地根據 **JSON canonical representation** 計算，兩份來源排序固定；可幫日後做 byte-binding，但未保存任何外部不可篡改原件或具法律來源證據。

## 安全範圍

`ops/inplay_two_source_byte_packet.py` 模組提供純函式 `audit(fixture, raw_claims, now=...)`。預設 now 為本機 UTC，測試允許指定模擬時刻；呢個時鐘不是 TSA。對每份聲稱驗證：
1. 記錄主客識別碼 + sealed kickoff 至少提前10分鐘、decison 已開波。
2. 正規化 UTF8 JSON bytes 上限10KB，拒絕重覆 key、NaN、布林假數、錯 schema、未知欄位。
3. 僅接受 HTTPS 指定合法 host 無帳密／port／query／fragment，但並沒有實際請求、TLS驗證或服務條款核查。
4. 嚴格 `source_updated <= captured <= received <= decision <= audit-now`，更新至決策及決策至審核均最長120秒；一個聲稱為未來／過期即 HOLD。
5. `FIRST_HALF`、`HALF_TIME`、`SECOND_HALF` 比賽分鐘合理，從開球時刻計算的牆鐘容許中場休息，但不支持補時與加時。
6. 同比分、紅牌、時段、分鐘一致；VAR review 未完即 HOLD，並非宣稱已完整審計進球/取消入球的 revision history。

無論成功與否：`production_recommendations=DISABLED`、`eligible_for_model_input=false`、`eligible_for_model_scoring=false`、`source_independence_verified=false`、`third_party_timestamp_verified=false`、`certified_forward_samples=0`、`positive_ev_verified=false`、`recommendation=null`。

## 下一個真正的外部數據關卡
先確定合法／授權來源與用途範圍；建立從網絡實際獲取的 **原始 HTTP payload、來源原生 event ID、HTTP 來源與時間** 的保密存儲；核實真正獨立的上游；獨立的原始 bytes 見證和可信 TSA 接入；再適配 #429/#430 的事件證據、#532 的真正模型執行收據。**本 PR 不包含以上真實接入、封存和見證，不能由 source claim JSON 自動晉級。**

## 驗收

```bash
python -m compileall -q ops
python -m unittest discover -s ops/tests -q
```

15項新增合成測試覆蓋快照吻合但未認證、狀態衝突、紅牌、VAR、主客ID錯配、時間倒灌/過期、重複發佈者、網址偽冒、重複JSON鍵、浮點NaN、敏感額外欄位、過大文件、布林值、固定雜湊順序及舊輸入不變。全部 GitHub CI、獨立程式審核完成前保持 Draft、HOLD、DISABLED。測試成功**不**代表真實比賽資料已到手或預測表現有改善。

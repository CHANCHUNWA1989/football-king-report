# 足球王者 VNext｜第十二關：外部數據來源授權預檢（2026-11-23）

## 目的
上一關 #540 能夠核對本機私有封包是否完整，**仍然無法證明供應商真實身份、使用／再分發權益、事件原始 HTTP 回應、第三方時間或資料獨立性**。今次增加一個 **deny-only、零網絡、純合成／未認證 metadata** 預檢器；目的只係把準備交畀法律及來源審核嘅資料結構化，唔係發出准入證。

研究分支依賴 #529→#530→#531→#532→#533→#535→#537→#540→本 PR。上游都係 Draft，未經獨立審核／序列合併前，唔接入 main。

## 新介面
`ops/inplay_source_rights_preflight.py`

`assess_source_readiness(dossier, now=None)` 接受嚴格 JSON-like dict：

- 必須有 `schema`、`fixture_id_claim`、`decision_utc_claim`、`private_inventory_sha256_unattested`、`sources`。
- `sources` 必須剛好兩個不同的 **自稱 provider**，各有 `provider_claim`、`api_host_claim`（只接受小寫 ASCII host；唔收完整 URL）、`rights_record_sha256_unattested`、`capture_receipt_sha256_unattested`、`rights_expiry_utc_claim`、`requested_uses_claim`。
- 不接受 `source_authorized=true`、`approved=true`、隱藏 API key、額外 odds、xG 等 bypass 欄位；缺件、重複名稱／host／收據、非 SHA256、未來決策、過期權益聲稱、URL/host injection 等一律 `HOLD`。
- metadata 結構全符合時，只會有 `ready_for_independent_review=true`、兩個候選數及 deterministic `preflight_sha256_unattested`；總狀態**仍然 `HOLD`**，`source_authorized=false`，`source_data_access_enabled=false`。
- 任何結果都 `eligible_for_model_input=false`、`positive_ev_verified=false`、`certified_forward_samples=0`、`production_recommendations=DISABLED`。輸出唔會包含來源 host、fixture ID、保密路徑、原始回應或文書。
- `rights_record_sha256_unattested` 只係**呼叫者自稱的 hash**；冇取回／核實真正授權合約，亦冇驗證簽署人、權限範圍、真實來源或 DNS／TLS。即使兩個來源不同名／host，亦唔證明獨立。

## 人手審核／外部阻塞（目前全部未完成）
1. 以權威渠道聯絡資料供應商，確認係原始版權／資料權利人或獲授權轉售方；由有權人審查 signed terms、地域、期限、賽事範圍及商業／研究／衍生模型／公開分發／投注用途。
2. 取得清晰書面准許與合法存取機制，核實官方 API / 合法端點、配額／轉向條款、IP / DNS / TLS / redirect policy；**唔會透過本模組連接任何網絡**。
3. 以真實 publisher receipt、獨立 request / response byte capture、event ID／主客隊身份、官方 VAR／紅牌、來源更新／接收／決策時點防 lookahead。兩間不同網站本身唔係來源獨立證明。
4. 由獨立審核者以簽名／受控系統記錄批准、批准範圍、到期及撤銷機制；另行完成外部 TSA / Sigstore/Rekor 見證、密鑰隔離、保留政策、私有存儲及稽核。
5. 完成 code review、主分支 CI、真實前瞻樣本外研究、信賴區間及 bookmaker odds timestamp 驗證；全部核實前 **HOLD / DISABLED**，唔可以聲稱正 EV 或推介準確度改善。

## 回歸驗收
```bash
python -m unittest discover -s ops/tests -p 'test_inplay_source_rights_preflight.py' -q
python -m compileall -q ops
python -m unittest discover -s ops/tests -q
```

`ops/tests/test_inplay_source_rights_preflight.py` 有 **15 個合成測試**，確認：自稱授權不可自動升級、參考清單、來源去重、憑證 hash、host 處理、期限、時鐘、非預期欄位、用途與保密欄位。**此 PR 唔含任何真實供應商合約／API key／賠率／賽果**；CI 全綠只係程式工程驗收，唔係授權批准。
# 第十二階段：公開來源 URL 查詢參數防敏感資料外洩（Issue #401）

## 安全缺口

#406 `ops/live_quote_snapshot_guard.py` 及 #408 `ops/live_fixture_attestation_audit.py` 的 HTTPS URL 驗證禁止 userinfo、fragment、顯式 port，但未禁 `query`。假設有人輸入 `https://example.org/match/123?api_key=...`，之前仍有可能通過固定來源對照表驗證；而來源對照表預期會被提交公開 GitHub、輸入 Sigstore 封存及 Actions artifact，可能永久暴露 API Key 或其他憑證。這是**公開內容准入的實際缺陷**，不涉及博彩預測公式。

## 本 PR 範圍

- 在兩個入口均對 `urlsplit(...).query` 作嚴格拒絕：任何帶**非空**查詢參數的 URL 一律 `INVALID_SOURCE_URL`／`INVALID_FIXTURE_SOURCE_URL`，後續 research-only pipeline 必須 HOLD。
- 新增兩組負向測試，分別模擬 `?api_key=`、`?token=` 及看似普通 `?fixture=` 查詢參數，防止 URL 中不明參數被加入公開存證；原有無查詢字串嘅 HTTPS fixture permalink 正向測試保留。
- 不消耗供應商 API、不讀取 GitHub Secrets、不掃描真實帳戶及不儲存任何真實憑證。測試中的字串只係公開無效的合成例子。
- 研究仍需 #403 → #406 → #408 → #411 → #414，這次為 stacked Draft PR；未經獨立第三方覆核不得繞過前置 PR 合併 main。

## 仍然未能保證的部分

- **無查詢參數不代表無敏感資料**；URL 路徑中也可能出現憑證，或來源回應包含秘密。公開提交前仍須以人工及既有 repo secret scan 檢查，**絕不可將私人 API endpoint 當成公開 fixture permalink**。
- 此閘門係最小限度的防呆，不認證第三方 feed 真偽、真實賽事身份、實際 kickoff、可成交角球報價、模型概率或正EV。
- 某些合法 API 使用查詢參數作賽事 ID，此類 URL 必須改用不含憑證的公開 canonical permalink，否則研究維持 HOLD，不可為咗通過測試而放寬閘門。
- `production_recommendations=DISABLED`、`certified_positive_ev=False`、原有前瞻封存、下注功能完全保持不變。

# 足球王者｜賽中私人候選證據 RFC 3161 外部時間見證交接（HOLD）

## 本輪獨立缺口

上游 #544 管理雙來源、截圖與 quote 的**聲稱**同刻配對；#547 生成同一時刻的原始證據私密候選 `candidate-...tar`，但只帶本機時間與 hash，無法證明它在時間點已存在。#463 已有「賽前」 RFC 3161 驗證 research gate，惟該 gate 以 kickoff 之前作唯一合格時限，故不等於賽中的 proof。

本 PR 以**整份 #547 私密 tar** 為 RFC 3161 主體，新增 `ops/inplay_private_rfc3161_handoff.py`；唔改 model / bankroll / main / API 配額，亦唔連線到任何 TSA：

1. `make_query(archive_path, output_tsq_path)` 將完整 tar 以 SHA256 算出 digest，逐一核對 archive 名稱、允許的固定 tar 成員、來源 raw 檔嘅 digest/size、原始收據 safety flags、聲稱本機採集時刻/fixture kickoff 與檔案名相符，最後執行 `openssl ts -query -digest <sha256> -sha256 -cert`；輸出私人資料夾中 `0600`、不可覆寫的 `.tsq`。**該 request 只包含 tar digest，不需要將原始 raw 附在外部請求中。**
2. 操作者將 `.tsq` 傳給自行選擇、合法、信任政策已核對的 TSA，另行取得 `.tsr` 回覆及獨立配置信任根 `.pem`；此程序**尚未連接**。
3. `verify_response(archive, tsq, tsr, ca)` 再讀同一 tar，執行兩輪 OpenSSL：`ts -verify -digest <same SHA> -in <tsr> -CAfile <ca>` 及 `ts -verify -queryfile <tsq> -in <tsr> -CAfile <ca>`。必須同時驗證回覆對應 tar digest 同原始請求 nonce，再用同份回覆的 `ts -reply -text` 擷取時間，拒絕格式不明、衝突時間、過早或比聲稱本機擷取延誤兩分鐘以上的 token。
4. 即使 OpenSSL 過關，仍然輸出 `status=RESEARCH_ONLY`、`decision=HOLD`、`independently_timestamped=false`、`issuer_policy_independently_approved=false`、`production_recommendations=DISABLED`、`certified_forward_samples=0`。不曾發出任何推介、注碼或 EV。

## 外部使用流程（私人系統，將來可操作）

以**真實**合法資料在比賽進行中生成上游 #547 的私密 tar 後，在有 Python/OpenSSL 的獨立可信機器上執行：

```python
from ops.inplay_private_rfc3161_handoff import make_query, verify_response
make_query("/private/candidate-YYYYMMDDTHHMMSSZ-<sha16>.tar", "/private/request.tsq")
# 由使用者另行將 request.tsq 交予合法 TSA；不可將原始 tar 公開。
result = verify_response("/private/candidate-YYYYMMDDTHHMMSSZ-<sha16>.tar",
                         "/private/request.tsq", "/private/reply.tsr",
                         "/private/pinned-trusted-ca.pem")
assert result["decision"] == "HOLD"
```

`YYYY...` 只係佔位示例，唔係一條現存證據檔案。留意持有簽章同 CA file 仍不代表 TSA 信任政策或憑證撤銷資訊通過獨立審查；必須由具信任責任的管理員另行做 CA policy、issuer、revocation 及來源證據 review。

OpenSSL CLI 依據：<https://docs.openssl.org/master/man1/openssl-ts/>。簽章/摘要驗證使用 `-digest` / `-queryfile`，唔會將原始 bookmaker response 交俾 TSA。

## 验收、風險、限制

- `python -m compileall -q ops`
- `python -m unittest discover -s ops/tests -q`
- `ops/tests/test_inplay_private_rfc3161_handoff.py`：純合成並 mock OpenSSL runner 測試。正向測試**不是**真實 TSA/CA 憑證驗收；需在能核對有效真實 token 的隔離 CI/QA 做獨立驗證，唔可以用 mock runner 結果聲稱接通真實 TSA。
- 漏洞防護：覆寫 TSQ、archive 修改、filename digest、raw tar 成員、重複 JSON key、來源／時間錯配、缺失 CA、符號連結、replay nonce、簽章失敗、時間過早／過晚。
- 本 PR 只讀取原始證據，不會自動索取/保存 API keys、爬取第三方來源、公開圖像或發送 raw bookmaker response。
- 現存 2026-11-23 長野 vs 浦和已完成之截圖**不可以**事後獲補證為前瞻場次，即使今天為它生成 token，token 只證明今天簽發時已存在，唔可以代表 13:30 曾經封存。
- 真實即場樣本、已認證來源、可成交 HKJC 報價、真正 TSA timestamp、源資料重放、前瞻 Brier/Log Loss、成功投注/正 EV **仍然 0/未認證**。GitHub 不上傳原始 tar/token/私人商業資料。

**依賴鏈**：本 PR → #547 → #544 → main。每級保持 Draft，等完整 CI、可信外部 timestamp policy、真正兩源來源證據同獨立 reviewer 才可考慮進一步接入研究；不能以合成測試升級投注建議。

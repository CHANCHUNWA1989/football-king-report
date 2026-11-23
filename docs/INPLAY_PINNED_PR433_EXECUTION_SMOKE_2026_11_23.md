# 足球王者 VNext｜PR #433 固定原始碼實際呼叫驗證（2026-11-23）

## 研究依賴及目標

此功能疊加在 Draft PR #531（本地函式執行觀察）→ #530（聲稱同一快照配對）→ #529（剩餘時間 Poisson 基準）上，**不合併、不修改**真正 PR #433 模型。PR #433 本身仍依賴 #429→#430→#431 才能審查合併。這輪嘗試改善之前只能確認任意 callback 被呼叫的缺點：真正從已固定 commit 讀取 PR #433 的原始 Python 函式，並對合成賽事執行一次。

## 強制釘選

- 唯一允許的 PR #433 來源 HEAD：`f2e92bdfeb2c36ebf1efeb708153303a607318a6`。
- `ops/inplay_state_challenger_vnext.py` 預期 Git SHA-1 blob：`d664d7cc561426956842f54901b581e27da04fb5`。
- `ops/score_distribution_vnext.py` 預期 Git SHA-1 blob：`ef35e05e999a9a894bac25428021f350e43b4b97`。
- HEAD、兩個原始碼位元組、一般檔案非 symlink、imported module 路徑、`predict.__module__` / `inspect.getfile` 不符一律 HOLD。驗證 byte identity **唔等於**上游簽章、發布者身份認證或可信時間見證。
- 若 PR #433 後續變更任何程式，應先重新審查並獨立修改明確的固定 pin，唔可自動追最新 branch。

## 真正執行內容

1. GitHub Actions 只取目前研究 PR 及上面**固定 SHA**兩次 checkout，`permissions: contents: read`，`persist-credentials: false`。
2. 無 API key、無博彩公司、無真人實時賽事資料、無正式比賽 ID、無第三方 xG。
3. 新模組 `ops/inplay_pinned_pr433_probe.py` 首先核對 Git HEAD／固定來源 blob，繼而從第二個固定 checkout 載入真正 PR #433 `inplay_state_challenger_vnext.predict()`。
4. 人工合成半場1:1案例（時間與入球率全部是測試常數）由 PR #531 的 `observe_local()` 作**一次本地呼叫**，再透過 PR #530 的 `compare()` 核對相同賽事 ID、常規分鐘、時間截點、比分、紅牌為0、賽前入球率和已宣稱未認證的證據 digest。
5. 僅成功時提供本地計算輸入／輸出雜湊及候選與基準三向假設概率差異。永遠無真實收益、勝率、下注價、推薦。
6. 如果快照被污染、來源文件被改動、模型未執行或配對出錯，**CI 失敗**並保留 HOLD。

## 必須同時理解的限制

- 此次證明的只係「喺 GitHub Actions 裏面執行與當前固定 Git commit 指向之模型來源位元組相同的 Python `predict()` 函式，而且輸出通過形式核對」。雖然比任意 callback 強，但仍然**不證明**某次真正比賽發生時就已執行、當時來源係咪獨立及準確、亦非 TSA/Sigstore 共同見證。Git SHA-1 blob 唔係授權來源或市場證據。
- Python model invocation 在 GitHub Hosted runner 進行，**沒有聲稱容器級斷網或簽章重現性**。不應讓呢種研究 CI 無審查就接收任意外部 Python 程式，也不得將 API keys/secrets 注入。
- 現時仍然 `production_recommendations=DISABLED`、`certified_paired_samples=0`、`positive_ev_verified=false`、`formal_model_comparison_allowed=false`、`externally_witnessed=false`。本機顯示 PR #433 合成個案實際呼叫為 True，唔能夠轉化成正式前瞻績效或下注資格。
- 本輪不會直接接入 iPhone 公開網站、正式賽果資料庫、封存 A/B/C/D 或正式模型權重；相關 Draft 全部等獨立 code review。

## 驗收指令

```bash
python -m compileall -q ops
python -m unittest discover -s ops/tests -q
python ops/inplay_pinned_pr433_probe.py --candidate-root candidate-pr433
```

最後一條必須由 `.github/workflows/inplay-pr433-pinned-smoke.yml` 實際 checkout 到固定 PR #433 SHA 後執行。不能憑 mock 測試就宣稱 real PR433 已跑。

進一步要實證模型有用，依然需要合法雙來源賽事時間／事件、真實xG及盤口、外部可信前瞻見證、≥300獨立封存樣本、12星期、4聯賽各≥40場、同場同時點配對 Brier/Log Loss 和信賴區間。

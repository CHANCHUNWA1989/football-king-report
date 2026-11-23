# 足球王者 VNext｜第十關：即場私有封包本地保存與重播（2026-11-23）

## 問題與實際修補
上游 PR #535 只建立一個可重播的 **in-memory USTAR** 封包，運行完就可能消失。新增 `ops/inplay_private_local_store.py`，將該封包用 **create-only** 方式寫入操作員事先建立的本機私有目錄，再從同一個檔案系統讀出原始位元組、核對 SHA256、調用 #535 重播校驗器。命中相同位元組檔案，重試為 no-op；任意內容變更、安全權限缺失或路徑攻擊，直接拒絕。

## 依賴
研究 PR #529 → #530 → #531 → #532 → #533 → #535 → 本 PR（**全部 Draft；尚未獨立審核，不會跳過順序合併 main**）。沿用現有 `ops/private_response_capture.py` 安全檔案／目錄讀取基礎設施，不重寫 provider HTTP 收集器或遠端 GitHub 封存 API。

## 使用限制及安全設計
- 只接受 `make_private_package()` 產生並經 `replay_private_package()` 核實的 caller-supplied normalized **source-claim bytes**；**不是**官方原始 HTTP body 或已授權、已認證的實時來源。
- `save_private_package(root, package, now=...)`：root 必須由操作員先喺 Git repo 以外建立，owner 控制、權限 mode `0700`；沿用安全 traversal（防父資料夾 symlink、`.git`、權限不足），以 `O_NOFOLLOW | O_EXCL` 建立唯一名稱 `inplay-<sha256>.tar`，檔案 `0600`、`fsync`，完整 byte-readback + 重播；檔案名稱不包含球隊、比分、URL、token 等敏感資料。
- `verify_private_package(root, expected_sha256, now=...)`：只會按固定雜湊讀同名檔案；限制大小，拒絕 symlink、hardlink、遭竄改檔案、錯誤目錄權限或缺檔案。只回傳安全旗標及 digest，絕不回傳 raw bytes 或內部路徑。
- 無跨裝置、遠端或不可變 WORM 保證；其他有同機檔案權限的人可能刪改內容，這時 readback 只能檢出檔案與預期 digest 不符，不能阻止惡意刪除。若 disk/fsync 出錯，可能留下局部檔案，後續**不可默默覆蓋**。
- `ops/tests/test_inplay_private_local_store.py` 提供12項無外部網絡、無真實賽事、全 synthetic 的正反測試：模式 0700/0600、同內容 no-op、修改原檔、錯 digest、symlink、hardlink、在 `.git` 路徑內、公開可讀目錄、缺目錄、非法 payload、錯誤訊息不可洩漏。

## 需要明確聲明
- **此模組只驗證本機檔案存在及可重播**；回傳 `local_filesystem_byte_readback_verified=true` 不等於持久可用性已獨立證實、外部可信時間、來源身份、來源獨立性或前瞻封存完成。
- 該封包含未認證原文 URL／資料，唔可上載 public GitHub、公開 Pages、未設存取限制的 Action artifact，也唔可印出內容到 CI 日誌；本 PR CI 只能使用合成 payload。
- 沒有寫入私有遠端 repo，未建立加密／備份／保留期，也沒有取得任何真實 FotMob、Sofascore 等 live API 授權及來源 HTTP response。實際使用要另外審查來源許可、個人／商業資料收集與存取權。
- 永久 `production_recommendations=DISABLED`、`eligible_for_model_input=false`、`positive_ev_verified=false`、`certified_forward_samples=0`、`durable_storage_independently_verified=false`；不更新舊 A/B/C/D、無投注或實際模型入場。

## 驗收指令
```bash
python -m compileall -q ops
python -m unittest discover -s ops/tests -q
```
完整 GitHub exact-head CI 及獨立審查係合併前必要條件。下一個真正外部關口：**獲授權供應商原始位元組 + 固定 event ID + 外部 TSA / Sigstore 獨立見證 + 檢查資料授權用途**；未完成之前保持研究模式。

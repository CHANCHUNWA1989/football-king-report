# 足球王者｜賽中私人原始證據候選封存（研究，HOLD）

## 缺口及界限

PR #544 已有離線 HKJC 截圖、雙來源事件及聲稱盤口同刻配對，但並未保存**完全相同的原件 bytes**。只存人工宣稱的 json、URL 或 image SHA，會令事後重放不能核對原始證據的真實內容。本 PR 在 #544 分支上新增一個**可選、純本地、無網絡**的保存工具，僅處理操作者已合法取得及有權保存的 bytes；不自行採集第三方網站、不自動擷取賠率、更不會啟用正式投注。

本模組為 `ops/inplay_forward_private_seal.py`：

1. 呼叫 #544 的 `inplay_hkjc_evidence_binding.audit`，只有先通過「研究性格式」檢查的資料可被封存；雙來源不一致、賠率比最近實質事件更早、失效、無紅牌資料、圖片 hash 不合等，全數拒絕產生檔案。
2. 需要兩份已提供來源事件觀察、聲稱已預先封存的 fixture 原始 JSON、兩份原始比分 bytes、一份原始盤口 bytes、一份原始截圖 bytes，以及每份人手整理的 metadata。兩個比分來源的固定順序必須與被封存的 fixture 相符。
3. 輸出只在使用者指定、**已存在的私人本地資料夾**，且禁止寫進任何上層含 `.git` 的工作樹；輸出單一 `candidate-<UTC>-<SHA16>.tar`，內有 `fixture_seal.json`、`score_primary.raw`、`score_secondary.raw`、`quote.raw`、`screenshot.raw`、`receipt.json`。
4. 使用 `os.O_EXCL` 建立 `0600` 檔案；同一名稱一律拒絕覆寫。對原始檔案執行大小上限、SHA256 與固定 tar 成員名稱審核；不解壓至操作者提供的任意位置，不能透過 `../` 檔名寫出目錄。
5. 預設使用**執行當刻本機 UTC 時鐘**，單元測試可明確注入測試時鐘。輸出中 `capture_wall_clock_utc_not_attested` 僅屬電腦本地時間，不可稱作 TSA、Sigstore 或 Rekor 見證。
6. 公開 GitHub PR 只保存程式、合成測試及說明文件；**不保存任何真實用戶截圖、博彩帳戶、API key 或商業盤口原件**。

## 嚴格不能聲稱已完成的工作

- 這個工具**不會連線** WE League、FotMob、Sofascore、HKJC 或授權數據供應商；無任何真實賽中候選資料在本 PR 中自動採集或寫入。
- 現有 seal JSON 的 `expected_identity_sealed_utc` 係由操作者聲稱；即使時間檢查通過，亦無外部見證能阻止有人今日偽造昨日時鐘或整包資料。同樣，自己重新計 hash 不能證明該 bytes 就是博彩商先前發布的原件。
- 原始比分與市場檔被**保留**但不由本模組驗證 publisher 簽章、parse 內容或版權授權，亦不能證明 image 內顯示的 2.31 真係可以成交。完整的可信采集需在*當時*由獲授權來源提供來源原件、官方 event ID、獨立 clock / TSA 見證、綁定過的模型輸出及賽後獨立驗證。
- 長野 vs 浦和 2026-11-23 13:30 HKT 截圖屬歷史例子；**不得**事後使用本工具改稱為真正前瞻證據或正 EV 樣本。
- 正式狀態固定 `RESEARCH_ONLY` / `decision=HOLD`、`production_recommendations=DISABLED`、`positive_ev_verified=false`、`model_scoring_eligible=false`、`certified_forward_samples=0`。

## 驗收

```sh
python -m compileall -q ops
python -m unittest discover -s ops/tests -q
```

合成測試 `ops/tests/test_inplay_forward_private_seal.py` 包含正常保存、原始 bytes 精確一致、檔案權限、不可覆寫、圖片篡改、雙來源矛盾、過期盤口、假開賽、賽後結果注入、偽造 seal、重複 JSON key、缺 raw 檔／超限、來源順序錯、資料夾不存在、symlink、Git 儲存庫防公開與無輸入修改。PR 仍需 exact-head CI、獨立 code review。

## 下一項真正前瞻入場驗收（需外部合法資料）

在未來**尚未開賽**的一場球，先取得真實不可事後修改的外部 fixture/來源 ID 見證；進行中按授權資料源同時擷取兩份 source-native score/event 原件、一份市場 raw quote、一個獨立本地 capture 以及第三方時間見證。不能開啟自動下注；先驗證成套原件有合法使用權、時刻可證明及來源真正獨立，再入 Shadow 研究帳本。缺任何一項，正式評分樣本數仍為 0。

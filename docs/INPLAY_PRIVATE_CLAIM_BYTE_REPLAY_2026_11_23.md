# 足球王者 VNext｜第九關：私有即場原位元組封包與重播（2026-11-23）

## 真正修正嘅資料缺口

Draft PR #533 會計算兩份 normalized source **claim** 原位元組 SHA-256，但**唔保存**原位元組。SHA-256 只能對日後提供嘅位元組進行比對；如果當時輸入冇保存，根本無法驗證究竟係邊一份來源聲稱文件。因此本輪將原始**聲稱文件位元組**封成可重播、結構固定嘅記憶體封包，保證保留夠資料供日後人工或程式核對。

依賴鏈 Draft PR #529→#530→#531→#532→#533→本 PR（不應跳過獨立審查而合併）。另有已存在 OpenLigaDB / NDR 真實原始 HTTP 捕獲同 Sigstore 私有封存研究工具；呢個模組唔複製、唔取代佢哋。**未做任何實時網絡收集。**

## 新增功能

- `ops/inplay_private_claim_replay.py`：
  - `make_private_package(fixture, raw_claims, now=...)`：必須先經 #533 的 strict audit 以同比分／紅牌／分鐘、同一決策截點、無未決 VAR、無賽後資料核對成功；否則唔產生封包。
  - 將原兩份**已正規化但未認證**的 JSON bytes 原封不動存成 deterministic USTAR in-memory bundle；manifest 記錄固定順序、位元組長度、SHA256、原 audit packet digest、自報時鐘與 fixture metadata。
  - `replay_private_package(package, now=...)`：在記憶體中安全讀取固定3個成員，**不解壓到檔案系統**。嚴格拒絕額外／重複／路徑穿越／symlink、非標準 tar header、trailing bytes、manifest 非標準鍵、聲稱文件變動、SHA256 不匹配、封包與 #533 再執行核對結果不一致。
  - 重播時間可以比聲稱的收集時間遲（歷史回溯），但唔可早於聲稱收集時刻；**當時的時間本身仍然係輸入自報，並非可信時間戳。**
- `ops/tests/test_inplay_private_claim_replay.py`：12項合成正／反／私隱測試，包括 deterministic byte ordering、exact bytes inside bundle、tampered source/manifest、traversal、symlink、duplicate members、extra trailer、時間倒灌、來源分歧及錯誤時不洩漏資料。

## 儲存及授權邊界

- 模組只會返回 **private package bytes in process**；**不會寫到硬碟、GitHub、公開 repo、手機網頁或第三方。** 因而 `durable_storage_verified=false`。外層必須經獨立審核嘅**私有**儲存系統／權限策略安全保存，並建立實際下載、刪除、保留時限及用途限制後，先可談可持久保存。
- 封包內原始 bytes 可能包含供應商來源 URL path 或敏感資料。**不得上載此封包到公開 GitHub PR、CI log、公共 artifacts 或公開 dashboard。** 只有打碼摘要／digest 可以報告。
- 來源 bytes 是 **caller-supplied normalized JSON claims**，唔係真實 provider HTTP response。即使 replay byte-for-byte，依然唔證明供應商曾發出該文件、官方賽果、真正來源獨立性、xG、開賽時刻、合法 API 取得或其商用授權。冇真正實時賽事、網絡收集、或任何真實比分推介。
- GitHub CI 只用 synthetic 1:1 fixture；原始公開歷史 A/B/C/D、正式盤口、PR #433 權重及正式網站不改。

## 不可升級旗標
`production_recommendations=DISABLED`, `eligible_for_model_input=false`, `eligible_for_model_scoring=false`, `positive_ev_verified=false`, `certified_forward_samples=0`, `externally_attested=false`, `durable_storage_verified=false`, `recommendation=null`。

## 驗收
```bash
python -m compileall -q ops
python -m unittest discover -s ops/tests -q
```

此測試成功只證明可重播 **untrusted normalized claim bytes** 而非已實作真正第三方見證。獨立程式審核及合法原始資料來源的授權仍為阻塞項。

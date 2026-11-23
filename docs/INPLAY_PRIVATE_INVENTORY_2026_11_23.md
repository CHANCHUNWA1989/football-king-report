# 足球王者 VNext｜第十一關：私有封包清單一致性核對（2026-11-23）

## 目的與已知缺口
PR #537 只驗證指定的一份私有封包有冇被改動，**未檢出同一資料夾的缺失封包、異常增加的文件，或兩次讀取間的改動**。本 PR 加入只讀、全批次、**操作員先提供 expected SHA-256 清單** 的核對器。

研究鏈：#529 → #530 → #531 → #532 → #533 → #535 → #537 → 本 PR。所有 PR 保持 Draft，未經獨立審核前不得合併 main。

## 介面
`ops/inplay_private_inventory.py`：
`audit_private_inventory(root, expected_sha256: list[str], now=None)`

- root 必須係事前建立、位於 Git repo 外、擁有人私有權限 0700 的目錄；唔會自動建立或刪改任何文件。
- expected_sha256 必須係 **1 至 64 個互不重複的小寫 SHA-256**；清單必須由操作員獨立保留／核對，否則同時改動檔案及清單仍可能自洽。
- 掃描目錄必須**完全等於** `inplay-<sha256>.tar` 期望檔案集合。多一個未知檔案、少一份、符號／硬連結、權限不符、Git repo 內目錄均拒絕。
- 每份檔案經兩次有界讀取及 SHA-256 核對，第一次執行 #535 private replay，第二次檢查讀取期間有冇被替換；前後核查文件清單及原根目錄 inode。
- 只回報固定安全旗標、成功數量及未外部證明的 inventory commitment；不回傳本地路徑、文件名稱、原始來源 URL 或 private package bytes。
- 任一失敗都 `HOLD`，`all_expected_packages_replayed=false`，唔會部分成功或啟用模型。

## 合成負面測試
`ops/tests/test_inplay_private_inventory.py` 有 13 個 case：兩份封包正常重播、順序不敏感、缺檔、額外檔案、錯／重複／過大 pins、內容被改、symlink、hardlink、目錄權限及 Git checkout、兩輪讀取間篡改、私有資訊不外洩、不能聲稱獨立持久認證。**CI 不存放任何真實賽果或商業供應商數據。**

## 安全限制與下一個外部阻塞
- 本模組只證明當次本機掃描自洽；**不能防止同一機器惡意管理員同步取代檔案及 expected pins**，不是 WORM、跨機備份、Sigstore/Rekor 見證或第三方 TSA。
- `now` 與來源聲稱時間仍可由呼叫者提供，無可信取時證據；即使結果 `RESEARCH_ONLY`，**唔代表來源真實、獨立、獲授權或已建立樣本外前瞻樣本**。
- 未接入真正授權 provider HTTP response；官方紅牌、xG、live bookmaker quote、EV 完全未經此模組核實。任何模型／正式投注仍 `HOLD / DISABLED`，`certified_forward_samples=0`、`positive_ev_verified=false`。
- 下一個**非純程式**必要關卡：有證據的供應商資料使用權、原始來源收據、可信外部時間／簽名見證、獨立保留的 pins、code review。未齊就唔升級正式數據。

## 驗收
```bash
python -m unittest discover -s ops/tests -p 'test_inplay_private_inventory.py' -q
python -m compileall -q ops
python -m unittest discover -s ops/tests -q
```
要核實 **latest exact head** 安全、回歸、offline 1X2、ledger CI 全綠，且仍需獨立程式審核。
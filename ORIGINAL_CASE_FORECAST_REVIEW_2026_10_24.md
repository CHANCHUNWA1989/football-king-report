# 原案預測封存固定選取與真正重驗（2026-10-24）

## 問題與改動

`prepare_forecast_proof.py` 原本只能選最高數字的run／attempt。24日的最新封存40044235793-1有19個對照，原案32760…34266f已不在其中；原21日39531309964-1仍有該案恰好一筆。賽事過後不能拿另一批較新的預測代替首案原預測。

新增明確固定原案模式，四個參數必須一起提供：`--run-id`、`--attempt`、`--case-id`、`--paired-sha256`。它在原有有界、安全目錄掃描中選出確切run／attempt，再確認原paired解壓bytes的SHA256及原案唯一性，之後才執行當次官方Actions API核對。缺檔、錯attempt、錯摘要、缺案或重案一律拒絕，不會換另一份封存。

沒有參數時仍按原來latest模式，輸出manifest亦保持原結構。新增選擇metadata只是檔案定位，不認證簽章、來源或賽果；必須接續原有 `forecast_provenance_audit.py` 每次真正CLI驗章。每日workflow沒有更改成自動追蹤舊案；新模式可供明確個案覆盤及原有自主維護任務使用。

## 原案真正執行證據

本次00:41–00:42 UTC實際執行新模式及原有驗章程式，沒有mock、沒有讀取保存的verification JSON代替CLI。

- 原run：`39531309964/attempts/1`，官方API當次讀回main、成功、指定iPhone workflow及正確repository／head_repository。
- 原source／workflow：`99a855861d5836a85097de3271905412a632f636`。
- 原case：`32760f90f88632237a2184f309f033d1d382d992dcf62cc53c53e9a85134266f`，原封存只包含OpenLigaDB match83212；沒有事後補寫team16/87或NDR固定ID。
- 原預測：2026-10-21T02:08:27.994289Z；市場快照01:37:28.840476Z、來源市場更新01:33:24Z。
- 真正三份subject CLI全部通過；可信Rekor見證為2026-10-21T02:09:57Z，20/20原對照早於各自「記錄開波」。原案記錄開波為23日18:30Z，仍不等於獨立認證actual kickoff。
- 原paired SHA256：`666628a233176eaf22e79c69ee847793127fcd4b924ca0f4e40b2c6306409830`；三subject及bundle完整摘要見[衍生執行收據](research/first_admission/original_case_32760_reverification_2026_10_24.json)。
- 原paired加一個換行後真正CLI拒絕exit1；錯source digest真正CLI拒絕exit1。原件bytes保持原樣。
- 使用官方gh2.102.1，release archive及checksum檔對照官方API摘要，binary SHA256為`d7e919c19ad89502313325c2690bf8a8556234ec734b7a4593e39244ab3e4a87`。

衍生收據只是這次執行紀錄，不是另一張已簽封證書、可信admission輸入或保存後可跳過CLI的驗證報告。重驗時須重新取得可信run metadata及執行真正CLI，不能信本JSON自報成功。

## 重驗方式

使用支援attestation的官方gh版本，建立新的空輸出位置：

```bash
case_review_tmp=$(mktemp -d)
python ops/prepare_forecast_proof.py \
  --archives forecast_provenance --output-dir "$case_review_tmp/proof" \
  --run-id 39531309964 --attempt 1 \
  --case-id 32760f90f88632237a2184f309f033d1d382d992dcf62cc53c53e9a85134266f \
  --paired-sha256 666628a233176eaf22e79c69ee847793127fcd4b924ca0f4e40b2c6306409830 \
  > "$case_review_tmp/selection.json"
python ops/forecast_provenance_audit.py \
  --proof "$case_review_tmp/proof" \
  --source-sha 99a855861d5836a85097de3271905412a632f636 \
  --workflow-sha 99a855861d5836a85097de3271905412a632f636 \
  --run-id 39531309964 --attempt 1 --output "$case_review_tmp/audit.json"
```

上列固定版本必須與本次官方API選擇一致；錯誤metadata或CLI失敗不可改旗號繼續。此命令只取GitHub／簽章信任服務，沒有體育供應商GET或額外賠率積分。

## 測試與剩餘缺項

新增7項原案選取正負回歸，在舊程式重現1個失敗及42個例外（含子測試）；修後38項preparer測試通過。compileall、1,738 ops及145其他測試（共1,883）與diff check通過。獨立助理實際重跑83項相關測試及63組額外pins／selection對抗，確認沒有阻擋合併缺陷；同一助理另真正執行官方CLI三次：原案paired成功、篡改及錯source皆拒絕；收據、三subject與bundle摘要一致。CI、合併及發布以PR實際完成紀錄為準。

此輪完成原案「當次簽章重驗及精確case連結」組件。#274仍缺：特定feed／賽季／90分鐘資料的肯定用途許可及採集／上游原件、確實獨立第二來源、權威跨來源fixture／team映射、actual kickoff及獨立90分鐘FT。現有保存原件仍是舊時點資料，不是24日新採集；不同URL、hash或一般credit不補上述缺項。

沒有可信admission、新認證賽果、合資格週或預測改善證據。舊封存／權重／固定來源政策／ledger／原ZIP及正式門檻不改；正式推薦維持DISABLED／HOLD。

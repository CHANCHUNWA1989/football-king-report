# 原案每日定點覆核（2026-10-24）

## 問題與改動

PR314已提供固定run／attempt／case／paired摘要的原案選取，但每日及CI流程仍只重驗最新批次。最新40046584265-1不含首案32760…34266f；原39531309964-1仍有該案，因此新的完場觀察可能未連到原始賽前封存。

本輪在 `four-model-shadow-daily.yml` 及 `four-model-shadow-ci.yml` 各新增獨立 `original-case-review` job。每日job只依賴原有shadow-daily的成功輸出，CI只依賴原有live-source-smoke；下載父job已產生的artifact並重用其raw_sources／raw資料，不新增供應商GET、不改排程／免費賠率額度。

原有latest兩份輸出及既有NDR／OpenLiga簽封、永久存檔工作保持原依賴，不等候新增review。新job若遇metadata或驗章失敗會如實失敗，整體workflow可顯示failure，但不反向阻斷已成功的資料封存；沒有continue-on-error把失敗偽裝成成功。

## 精確輸入與輸出

每次使用既有CLI及四個明確pins選原件：

- 原run／attempt：39531309964／1。
- 原case：32760f90f88632237a2184f309f033d1d382d992dcf62cc53c53e9a85134266f。
- 原paired解壓SHA256：666628a233176eaf22e79c69ee847793127fcd4b924ca0f4e40b2c6306409830。
- 原source／workflow：99a855861d5836a85097de3271905412a632f636，須與當次官方Actions API一致。

然後呼叫原有raw fixed-ID linker，其內每次真正執行三份subject的gh attestation verify。新產物 `original-case-forecast-review` 僅在job成功時上傳，保留30日，包含selection.json、完整未認證raw linkage及單一原案summary.json。

summary明示derived_review_not_a_trust_input、HOLD／DISABLED，保留review_checked_utc與claimed_raw_capture_utc各自原義；不拿本次重驗時間覆蓋舊來源。缺原案raw列時為NO_MATCHING_RAW_CASE／case_linked=false／ft_candidate=false；身份矛盾或未完場亦不得假報完場連結。

來源身份、原站／時間／新鮮度、原預測teamIDs、actualKO、regulation FT真偽、scoring及promotion等11項能力旗標保持false。forecast_signature_reverified可為true，只表示原預測簽章通過，不代表比分獨立認證。新產物不接入ft_observations_input、四模型評分、舊ledger或正式推薦。

## 缺陷重現與測試

新增9項測試，從真正YAML取出整段bash執行，使用真prepare及真linker subprocess；只有gh API及驗章回應為明確mock。使用原永久檔案bytes及pins，另放一份不含原案的新批次；驗證兩份workflow都回到原案、原件／raw bytes／latest輸出不被修改。

舊workflow未有原案job，新增回歸先重現12個失敗情境（含子測試）。驗收包括：缺原run、paired bytes改動、freshAPI失敗、三份subject各自驗章失敗、錯source、raw摘要錯誤、raw缺原案或身份矛盾，以及job依賴隔離。測試亦讀取實際YAML的raw子目錄設定，不在測試另造一份正確設定。

- compileall：通過。
- 1,747項ops及145項其他測試，共1,892項通過。
- YAML實際解析及job依賴核對、diff check通過。
- 獨立助理實跑92項相關測試及10組額外對抗，確認兩個實際bash逐字相同、只有raw子目錄不同，無阻擋合併缺陷。

## 真正CLI整段執行

主助理另在兩個新工作目錄執行兩份實際YAML bash，使用官方gh2.102.1、fresh官方API及真正三subject CLI，沒有mock。兩次均exit0，原case唯一、同provider固定ID連結及2:3完場候選存在，所有認證能力旗標仍false。

- daily腳本重驗時間：2026-10-24T01:16:53.856754Z。
- CI腳本重驗時間：2026-10-24T01:17:10.018660Z。
- 兩者原資料claimed捕獲仍為00:45:00.932915Z，raw SHA010b94d867ed252047e84fa6e20a16aa9dcf04d9428e8a0a18938c21fe50e349，重用前輪CI原件，沒有新providerGET。
- 原可信Rekor見證仍為21日02:09:57Z，只早於原件記錄KO，不是actual kickoff認證。
- 官方binary SHA為d7e919c19ad89502313325c2690bf8a8556234ec734b7a4593e39244ab3e4a87。

獨立助理另對兩份原生產物逐byte及摘要核對：三subject／bundle均等於原永久gzip解壓，raw／manifest、原case及11項false能力旗標一致；該次助理只離線讀回，真正網絡CLI是主助理實測。單元mock結果與這組原生證據不能混為一談，衍生receipt亦不能成為下次信任輸入。

## 發布與剩餘限制

PR hosted CI須驗證真正artifact下載及新job，通過後按既有授權合併。每日job由原排程首次執行的結果以實際Actions紀錄為準；不為驗收額外dispatch原採集流程或把本地script成功說成每日排程已跑過。此輪沒有手機網站程式或預測模型改動；原網站健康及資料時間另行讀回。

#274仍缺特定feed／賽季／90分鐘採集及上游與用途依據、真正獨立第二來源、權威跨來源身份及actualKO／regFT認證。新增自動覆核不是可信admission，也沒有擴大來源政策、改動原封存／權重／ledger／ZIP或放寬門檻。沒有新增cert、合資格週、正式主推或預測改善證據，DISABLED／HOLD保留。

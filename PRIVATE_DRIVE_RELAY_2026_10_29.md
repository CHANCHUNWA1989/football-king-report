# 私人 Drive 原件中轉

擁有人於2026-10-29在已說明「新增公開密文附件」的選擇後授權自行設定。本次明確擴展公開附件政策：原有兩份刪敏摘要保持不變；另外只發布加密原件及獨立安全雜湊收據。可讀原件、解密 identity、私人 Drive ID／連結不加入公開 repo、附件、Pages 或日誌。不是正式推薦放行。

## 同次原件流程

1. 沿用現有私人 collector 的同一次成功 HTTP 回應、manifest pin 及 canonical ZIP；不增加足球供應商請求、不放寬配額。
2. `ops/install_age.py` 固定官方 age v1.3.2 Linux/amd64 URL、19,405,817-byte附件 SHA256及兩個 binary SHA。只安裝 age／age-keygen，沒有插件、shell、憑證或自動升級。驗證官方 HTTPS release digest，沒有驗證獨立 Sigsum proof。
3. `ops/private_response_relay.py` 使用固定 SHA／版本的 age native PQ recipient 加密。repo 只有 public recipient，檔案為 `sources/policies/private_original_recipient_v1.txt`；identity 在私人 Drive 及受控工作目錄。加密／解密的 binary 與 identity 使用 sealed Linux memfd；解密必須完整成功並通過原 ZIP、外部 manifest/context/hash 重驗，才安裝原件。晚期失敗的部分輸出一律隔離及刪除。
4. 新的 `football-private-original-ciphertext-{run_id}-{attempt}` artifact **只含** `original-response-pack.zip.age`；另一個 `football-private-original-receipt-{run_id}-{attempt}` **只含** `producer-receipt.json`。收據只允許固定 schema 的 context、大小、數量、雜湊及 false／HOLD flags。兩者保留7日，未進入永久公開 git 歷史。原 `all-market-redacted-research-summary` 仍精確只有原兩個摘要，保留1日。
5. 現有助理的 GitHub／Drive 連接負責 broker；Runner沒有Drive OAuth或identity。助理從 authenticated GitHub REST 取得 run及兩個artifact metadata與完整ZIP，並從外部已覆核私人配置驗證該run的全部ops Python程式／指定workflow及public recipient檔案SHA。先以可信stdlib bootstrap核對本機程式bytes，才執行CLI；未驗證的新程式不能靠自我檢查取得信任。`ops/private_relay_provenance.py` 嚴格綁定repo ID／full_name、非PR受信事件、source、branch、workflow path、run／attempt、artifact ID／digest／exact member、獨立收據及recipient pin。不能只從密文內自報context取得信任。
6. age保密與完整性不認證發送者，任何人持有public recipient均可加密。GitHub binding只證明這份附件來自已覆核傳輸程式／workflow的指定run，不證明publisher、實際開波、來源時刻或賽果。
7. 助理使用 `ops.private_drive_handoff prepare` 在repo外0700目錄還原、重播，再將同一canonical ZIP以私人Drive連接上傳。寫入前後核對指定folder及file為非Shared Drive、`shared=false`、只有user/owner、parent正確；authenticated raw下載相同bytes／SHA及replay成功後，才記私人保存成功。

## 首次實測與持續 broker

`.github/workflows/private-original-relay-synthetic.yml` 只產生明示合成catalog body，不讀供應商密鑰、不調collector或足球API。分支上的真實artifact中轉、私人解密、Drive上傳及讀回是合併前驗收；不增加研究或認證樣本。

沿用現有每五小時統一助理任務，不建立重複排程。足球broker先處理未保存批次，按run建立時間由舊到新，最多處理固定小批；有backlog須報數量。只接受已覆核code pins；程式／workflow變更未核准、失敗run、過期／漏artifact、重跑attempt不符、metadata或hash衝突、錯匙、ACL不符、Drive不可用，均記HOLD而不宣稱保存成功。

私人檔名固定為 `original-{source_sha}-{run_id}-{attempt}-{manifest_sha256}.zip`。上傳前按指定folder及exact filename查已有檔：無檔才建立；一檔必須先核對owner-only／parent／exactsize及authenticated讀回SHA相同才視作重複成功；多檔或內容不同屬衝突，不能覆寫或靜默跳過。保存後另建同名 `.receipt.json` 私人收據，綁定原artifact IDs/digests、context及Drive讀回SHA，從不把來源認證flag改true。每輪同時偵測最近7日已完成但缺保存收據的run；已過期且無私人原件的批次明確列漏批，不重調足球供應商補造當時原件。

排程受助理任務、連接及GitHub延誤影響，不承諾無人值守永不失敗。更換recipient時新建版本、先驗證新identity私人讀回、更新外部reviewed pins；舊identity保留到舊密文全數歸檔及保留政策允許處置。不可用新key假稱能解密舊檔。

## 驗收及限制

新增正向與錯匙／篡改／晚期截斷／錯context／manifest／archive／cipher pin／工具替換／路徑／超限負例。公開附件三份allowlist全部鎖定，沒有放寬原兩份摘要或容許raw ZIP、key、目錄／wildcard。CI先安裝pinned age才跑真實加密測試；同時保留既有配額、封存及完整性測試。

私人Drive的位置及identity ID只在私人配置／統一助理任務保存。讀取key必須使用opaque raw file reference至受控0600檔案，不能經模型文字或base64、終端／日誌輸出內容。這個版本需要Linux/amd64及memfd sealing，其他平台fail closed。

所有原件來源／時刻／正式資格flags保持false，`production_recommendations=DISABLED`、`HOLD`；保存成功不代表WORM、官方來源或獨立認證。可信正向admission、certified-only統計與校準、實際開波／法定時間賽果、可成交市場及足量前瞻樣本仍須另外完成。測試通過不代表命中率或盈利提高。

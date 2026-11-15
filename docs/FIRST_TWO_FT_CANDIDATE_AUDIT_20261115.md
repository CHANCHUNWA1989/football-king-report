# P0｜首兩場真實賽果候選交叉核對（2026-11-15 HKT）

> **唯讀研究檢查，絕不是「2場已認證」。** 公開賽果、舊封存 `y`、加密收據能夠一致，不等於來源原件、上游獨立性、實際開球或賽前資訊鏈獲認證。正式資格維持 `HOLD`／`DISABLED`，certified=0。

## 已實際核對的兩場候選

| TheSportsDB 收據 event ID（僅公開主張） | 舊研究 ledger key | 開球時間（UTC） | ledger y | 公開正規時間 FT | 公開來源 |
|---|---|---|---|---|---|
| `2508371` | `bundesliga / borussiadortmund / svwerderbremen` | 2026-10-09 18:30 | 1（和） | 多蒙特 2–2 雲達不來梅 | [德甲官方](https://www.bundesliga.com/en/bundesliga/matchday/2026-2027/5/borussia-dortmund-vs-sv-werder-bremen/liveticker/)、[Sportschau](https://www.sportschau.de/live-und-ergebnisse/die-finals/deutschland-bundesliga/ma12194071/borussia-dortmund_werder-bremen/liveticker) |
| `2508372` | `bundesliga / tsghoffenheim / hamburgersv` | 2026-10-10 13:30 | 2（客） | 賀芬咸 2–3 漢堡 | [德甲官方](https://www.bundesliga.com/en/bundesliga/matchday/2026-2027/5/tsg-hoffenheim-vs-hamburger-sv/liveticker)、[Sportschau](https://www.sportschau.de/live-und-ergebnisse/die-finals/deutschland-bundesliga/ma12194095/tsg-hoffenheim_hamburger-sv/liveticker) |

- `main/evidence/settled.json` 截至 2026-11-12 17:44:06Z：104場未獨立認證研究；兩場都在列、舊研究賽果標籤與上列公開 FT 方向一致。
- #464 實驗分支嘅舊 `evidence/settled.json` 仍為82場；兩個樣本亦在列，不應把舊分支82當作主分支最新總數。
- #464 實驗分支 [公開加密原件收據](../evidence/encrypted_result_sources/v1/42406458039-1/) 含兩個 TheSportsDB event ID、加密 SHA，且明示 `independently_verified=false`／`actual_kickoff_authenticated=false`／`upstream_independence_authenticated=false`。
- 本次對外部網站只做人為公開頁面核對；GitHub CI **沒有拉取或封存外部網站原始 bytes**，不能證明來源時戳、授權、真正獨立上游或者其內容不可被更改。

## 新增 fail-closed 檢查

`ops/public_result_candidate_join.py` 用作**兩場固定候選**的公開聲明交叉檢查，根據完整原始 ledger key、先後時戳、研究 `y` 及公開收據欄位作唯讀核對。

- 同一 ledger key 若重複、時間相反、結果標籤不符，或收據夾帶假 `independently_verified=true`，**整個事件隔離**，不會 first-match-wins。
- 收據 SHA-256 雖然格式正確，但只要同 `sportsdb_public_cipher_audit.py` 中固定的公開原件／密文雜湊、密文大小或 recipient SHA 不一致，**亦必須隔離**。先以 `5315d045dd57` 的回歸測試重現 5 個失敗反例，再由 `55c18ed335a0` 的最小補丁修正。呢一步只係比對固定公開 metadata；**不會重新計算密文 SHA 或解密原文**，須另行執行已存在的公開密文完整性檢查。
- 報告 `candidate_count` 只係「候選資料一致」數量；**`certified_case_count=0`、`eligible_for_model_scoring=false`、`production_recommendations=DISABLED` 不變**。
- 固定網址係手動研究線索，CI 不會連線核證內容。本模組不讀解密私匙／明文、不得調用外部 API、不得改寫原A/B/C或 `evidence/settled.json`，更不產出下注 EV。

## 真正認證仍欠缺

1. 獲授權原件持有人喺受控私人環境，使用 PR #464 `sportsdb_private_keyholder_replay` 真正核對**原本私匙**、原始 bytes、原始來源 fixture ID、舊存取時戳，並提供安全可重播覆核決定；唔可以將金鑰或明文放入 GitHub／聊天。
2. 取得並驗證 **另一個真正上游獨立**的賽果來源原件；德甲官方、Sportschau 網頁顯示相同比分係有用佐證，但本工單未證實其底層來源彼此獨立。
3. 對應官方實際 KO 與正規 90分鐘 FT，並把賽事固定 ID、真正原始賽前模型/市場決策檔案 bytes 及簽封收據綁定。只靠正規化球隊名、日期／聲稱 digest 不得升格。
4. 經真正獨立審核及來源政策正向 admission，另立 certified-only ledger。即使第一場達成，亦需有最低300場、12週、4聯賽各40場等長期樣本驗證，並保留人工發布閘門。

### 測試與回滾

```bash
python -m unittest discover -s ops/tests -p 'test_public_result_candidate_join.py' -v
python -m compileall -q ops
python -m unittest discover -s ops/tests -q
```

若測試失敗，保留 #464 Draft，不可合併；今次只新增獨立研究模組與測試，既有認證 gate 不受影響。

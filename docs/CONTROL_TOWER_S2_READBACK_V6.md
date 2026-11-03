# 足球王者控制塔第六階段：S2 公開網站回讀（只讀）

**範圍：開發及驗證核對工具；不是網站部署、不是正式下注、不是授權發佈。**

## 上游和版本綁定

- 上游 Draft PR #405：只讀監察、來源時間與 CI 驗證；HEAD `66035d2ffd9938f1a529d2b2cc33f5c6fb5dd2e1`。
- 上游 Draft PR #409：嚴格核實 #405 獨立審核、分支規則及完整 CI；HEAD `bc300ef5d2ebf9a84e5828e08dc0d59197672e95`。
- S2 於新研究 Draft 分支，base 接 #409，不與 `main` 直接合併。
- 固定預期 `main` SHA：`151c734490ef37f273cffcd01d499907ace0aa28`。若 `main` 更新，現有檢查會報版本不一致；更新此 SHA 需要獨立驗證，不可自動視為放行。

## S2 審計分層

1. **公開網站資料讀取**：固定 HTTPS `status.json`、`quality.json`、`production_gate.json`。拒絕 HTTP 轉址、重複 JSON 欄、非有限數字、大於 1MB 嘅回應。
2. **資料一致性**：status / quality UTC 上游時鐘不得相差超過 5 分鐘；資料超過 10 小時、無可信時區、時間在未來超過 5 分鐘，必須 HOLD。比分人口、精確開賽、研究候選數量要符合基礎上界。
3. **研究安全**：三份公開文件必須禁用 `production_recommendations`；production gate 維持 `HOLD`、無自動發布、無模型正式升格；任何缺漏均 HOLD。
4. **GitHub Pages 程式發布證據**：核對固定 SHA 嘅 `main`、正式站發布 workflow `Football King V4.1 iPhone Daily Report`、publish job 和 `Deploy mobile site` step 都成功。使用執行來源確切識別，拒絕不完整分頁、其他分支或版本。
5. **公開頁面版本證據**：要求三份網站 JSON 都顯式持有相同 `source_commit_sha`。現有網站可能冇此欄位；缺少時明確報 `PUBLIC_SITE_RELEASE_SHA_NOT_ATTESTED`，**唔會錯誤聲稱新程式已上線**。即使三個欄位一致，都只係網站自報 + GitHub 工作流程交叉佐證，並非第三方不可竄改簽署。
6. **明確界線**：無論任何測試結果，`release_authorized=false`、`pages_deployment_authorized=false`、`live_execution_allowed=false`，正式推薦 `DISABLED`。離線成功不等於上游資料、模型準確率、經紀盤口或盈利被認證。

## 操作

```bash
python -m unittest discover -s ops/tests -p test_control_tower_site_readback.py -v
python ops/control_tower_site_readback.py --expected-main-sha 151c734490ef37f273cffcd01d499907ace0aa28 --offline --output /tmp/s2-offline.json
```

GitHub Actions: `Control Tower S2 Public Site Readback (read-only)`，僅 PR 或手動觸發；無六小時排程、無 GitHub Pages 寫入權限、無市場 API 權限、無交易指令。輸出只讀 `control-tower-s2-readback-evidence` Artifact，7 日保留。

## 真正發布前仲欠缺

- 獨立 GitHub 審核批准 #405 / #409 及本階段 exact HEAD；作者本人提交冇資格冒充。
- 管理員啟用並證實分支保護同必要審批及 CI 規則。
- 補充經審查嘅網站版本來源綁定，驗證實際部署後 GitHub Pages 回應；任何頁面缺資料／版本不符維持 HOLD。
- 發布係獨立授權行動，本階段唔會合併、部署或操作任何交易。

# 2026-11-06 足球王者：市場收據時間閘門修補（研究版）

## 實際缺陷

`ops/all_market_screen.py:evaluate` 原先僅比較 `observed_utc` 與檢查時間、開波時間；收到 `captured_utc` 時只原樣複製，未驗證內容或先後次序。於是來源更新時間看似有效，但收據卻比來源更新早、晚於開波、晚於檢查時間、格式無效，仍可輸出研究 EV。原先也容忍最多 60 秒的「未來」來源更新時間。

## 修補

1. 若有 `captured_utc`，要求有效、有時區的 ISO 8601；不得早於 `observed_utc`，不得晚於目前檢查時間或等於／晚於開波；拒絕接收時已過期的來源更新。
2. 移除 `observed_utc` 允許提前 60 秒的寬限。
3. 保留原始來源及擷取時間、原有 20 分鐘過期門檻及市場風險分級。
4. 全部輸出保持 `RESEARCH_ONLY`／`HOLD`；任何模型自稱已校準、來源自稱授權，都不構成正 EV 認證。

## 測試範圍

`tests/test_all_market_screen.py` 新增：反向時間、未來擷取、開波後擷取、缺失／無效／沒有時區的擷取時間、未來來源更新，以及正常有效收據下的半贏半輸研究 EV。現有舊報價、無法認證情境及市場種類測試保持原狀。

建議驗收指令：

```bash
python -m compileall -q ops
python -m unittest tests.test_all_market_screen -v
python -m unittest discover -s tests -q
python -m unittest discover -s ops/tests -q
```

## 未修復及無法宣稱的項目

- 無法由這項修補取得新博彩公司原始授權報價；目前公開 `market/latest.json` 只有 `h2h` 去水共識。
- 亞洲四分之一盤精確結算、離線歷史報價、前瞻凍結模型及樣本外統計仍在 Draft PR #451／#453；此項變更不替代兩者。
- 尚未認證實際可成交價、資料權利、獨立 OOS 表現或盈利。正式 `production_recommendations` 必須維持 `DISABLED`；不得自行跳過 Issue #439 的主分支保護及獨立人手審核。

狀態：待精確 HEAD CI 與獨立審核；**不可當成已部署或正式投注推薦**。

# 足球王者｜通用免費來源 URL 及認證 Header 邊界硬化

**日期：2026-11-23（香港時間）｜獨立 Draft PR #578 → main，Issue #577。**

## Source-level defect

Before this patch, `ops/secondary_sources.py:read_json(url, headers, opener=urlopen)` checked only `url.startswith("https://")` before constructing a request with potentially sensitive caller-supplied `Authorization`, `X-Auth-Token` or `x-apisports-key` headers. The helper could therefore send them to **any caller-supplied HTTPS host**. Its default opener was `urlopen`, whose normal redirect handling is not suitable for arbitrary credentialed requests. The *existing* collector and research-extension callers mostly constructed known fixed URLs and supplied `NoRedirect`, so this is defense-in-depth at a generic reusable function boundary; no claim of leaked real secrets or a confirmed production exploit.

## Test-first RED

**Test-only SHA `de484bc85898be5ef33745d1cd5bb81440c93116`.** New `ops/tests/test_secondary_source_exact_url_allowlist.py`, 15 methods, all HTTP mocked. Both GitHub regression jobs **each showed 12 failing methods** (2,354 tests run at RED HEAD). Examples include: unapproved HTTPS host with fake bearer header; substring/suffix domains; userinfo host confusion; nonstandard port; URL fragments; encoded/traversal paths; unknown API routes; unsupported or duplicate query parameters; rejecting direct helper's old redirect-following default. Positive controls also cover allowed six-league endpoints, StatsBomb/OpenFoot extensions, and the existing 48-call free-source fixture coverage loop.

No genuine API keys, external requests, odds or quota were involved. [RED GitHub test job](https://github.com/CHANCHUNWA1989/football-king-report/actions/runs/45167218161/job/137667187921).

## Proposed GREEN entry guard

`ops/secondary_sources.py` now uses `urlsplit` and `parse_qsl` to verify **exact** source identities, no authentication by substring. Before constructing a credentialed request, require all of:
- Explicit `https`, exact approved host, expected route path and bounded endpoint query keys/values.
- No username/password in the URL, explicit port, fragment, encoded/traversal path, unexpected extra/double key, or malformed date/league/season.
- Allowed request shapes only:
  - TheSportsDB: the three documented `/api/v1/json/123/{eventsday,eventsnextleague,eventspastleague}.php` endpoints, fixed league IDs, valid day or league ID;
  - API-Football: `/fixtures?league=...&season=...&next=3`, `/odds?league=...&season=...&bet=1&page=1` (research **presence probe only**, never executable odds);
  - Football-data.org: `/v4/competitions/{PL,ELC,BL1,PD,SA,FL1}/matches` with bounded date params;
  - Sportmonks: `/v3/football/leagues/{271,501}`, no query;
  - StatsBomb catalogue: the exact `raw.githubusercontent.com/hudl/open-data/master/data/competitions.json` path;
  - OpenFoot: `/v1/competitions` or `/v1/matches?date=YYYY-MM-DD`.
- `read_json` direct calls now default to `NoRedirect()` instead of redirect-following `urlopen`. Fake injected requesters remain usable, so no paid API/test network calls are required.

This does not prove every source data schema or licence; the gate protects **destination identity and credential routing**. Caller-supplied opener is intentionally injectible for tests, so it is not an authentication or sandbox mechanism on arbitrary Python callbacks.

## Boundaries and required review

- This PR is **independent of** the J1 Draft #560/#562/#564/#566/#572 chain. Issue #575 has 8 CodeQL URL-string rule results **in test suites**, not the source helper; do not conflate those findings with this source-level defect.
- No edits to main until CI, review and appropriate sign-off; no production or betting permissions.
- Keep exactly the same fixed collector requests, 48 TheSportsDB query cap and all paid/free quotas. No API keys in commits or logs; no market prices, forecast weights, archived snapshots or model calibration changes.
- `production_recommendations=DISABLED`, `HOLD`. No verified forward EV / accuracy uplift.
- Full verification: `python -m compileall -q ops` and `python -m unittest discover -s ops/tests -q`, all seven GitHub checks at final exact SHA.

### Human security review checklist
- [ ] Confirm each URL host/path/query identity is exact (no host suffix, userinfo, port, traversal, encoded or redirected credential leaks).
- [ ] Check all actual caller endpoint formats against allowlist, especially OpenFoot/StatsBomb and API-Football research odds presence probe.
- [ ] Compare test-only RED job with GREEN final exact-head CI, identify any scope regressions.
- [ ] Confirm no external URL/credential data or secrets reach public logs/artifacts; confirm no live API calls in CI.
- [ ] Reviewer records independent approval and exact SHA; research HOLD stays on.

## 第二輪安全覆核：即使 URL 合法，認證 Header 都必須屬於同一來源

起初修補只核對 URL；仍可能發生另一個低層風險：呼叫者向**合法但錯誤的另一個供應商**傳送 `Authorization`、`x-apisports-key` 或 `X-Auth-Token`，又或者用自訂 `Host`、`Proxy-Authorization`、`Cookie` 覆蓋 HTTP Request 設定。正常 collector 使用固定 request tuple，未證實現有生產流程曾這樣做；此修正將 **通用請求函式嘅授權邊界** 收緊為 host+credential-name 組合。

- **RED test-only `7d976088012b5d9b3ae4c78c26ffe6620b2c7d26`**：在既有測試增 5 項方法，兩組 regression 各確認10個失敗案例（包含單一方法多個 subtests），2,359 全倉測試執行。[RED 日誌](https://github.com/CHANCHUNWA1989/football-king-report/actions/runs/45168506741/job/137671606904)。
- **GREEN 修補**：`_approved_source_headers(url, headers)` 以先前已解析和核准的主機名稱選取固定可用認證 Header：
  - `v3.football.api-sports.io` 只接收 `x-apisports-key`；
  - `api.football-data.org` 只接收 `X-Auth-Token`；
  - `api.sportmonks.com` 只接收 `Authorization`；
  - `openfootapi.com` 只接收 `Authorization: Bearer ...`；
  - TheSportsDB 及 StatsBomb 歷史公開目錄唔接收任何外來自訂 Header。
- 不准 `Host`、`Proxy-Authorization`、`Cookie`、自訂 `User-Agent`、未知 Header、大小寫不同但重複嘅 Header、非字串、控制字元、過長值。容許同來源、非空、格式合格的測試用認證 Header，全部使用 mock requester，**零真實 HTTP 或憑證**。
- 不會因此聲稱供應商獨立、官方認證、付費盤可成交、模型準確率有升幅，亦不會停用原本 `DISABLED/HOLD`。

本報告記錄低層安全測試行為，不能用嚟替代對供應商官方協議、真實免費接駁相容性、獨立程式審核。新程式仍在 Draft PR #578，所有主程式變更均未合併 main。

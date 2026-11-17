"""Fail-closed, read-only Cantonese research-card renderer.

The card is a presentation layer, NOT a forecasting engine, an independent
source authenticator, an EV certifier or a production betting recommender.
All output retains HOLD/DISABLED regardless of self-attested input flags.
"""

import argparse
from datetime import datetime, timedelta, timezone
import json
import math
from pathlib import Path
from zoneinfo import ZoneInfo

HK = ZoneInfo("Asia/Hong_Kong")


def _text(value, default="未核實", limit=130):
    if not isinstance(value, str):
        return default
    # Input notes are untrusted. Restrict line breaks and Markdown control chars.
    value = " ".join(value.split()).replace("|", "／")
    for marker in ("<", ">", "[", "]", "*", "`", "#"):
        value = value.replace(marker, "")
    return value[:limit] if value.strip() else default


def _datetime(value):
    if not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt.astimezone(timezone.utc) if dt.tzinfo is not None else None


def _safe_dict(value):
    return value if isinstance(value, dict) else {}


def _is_probability(value):
    return type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 1


def _valid_odds(value):
    return type(value) in (int, float) and math.isfinite(value) and 1 < value <= 1000


def render_card(payload, *, now=None):
    """Produce a transparent, HK-time research report from an untrusted dict.

    Any apparently good quote/model is shown as *unverified research*.
    Never claim certified positive EV, place a stake or activate production.
    """
    if not isinstance(payload, dict):
        raise ValueError("INVALID_REPORT_INPUT")
    now = datetime.now(timezone.utc) if now is None else now
    if now.tzinfo is None:
        raise ValueError("NAIVE_NOW")
    now = now.astimezone(timezone.utc)
    fixture = _safe_dict(payload.get("fixture"))
    quote = _safe_dict(payload.get("quote"))
    home, away = _text(fixture.get("home_zh")), _text(fixture.get("away_zh"))
    home_id, away_id = fixture.get("home_id"), fixture.get("away_id")
    identity_ok = (isinstance(home_id, str) and bool(home_id.strip())
                   and isinstance(away_id, str) and bool(away_id.strip())
                   and home_id != away_id and home != "未核實" and away != "未核實")
    kickoff = _datetime(fixture.get("kickoff_utc"))
    kickoff_hk = kickoff.astimezone(HK).strftime("%Y-%m-%d %H:%M") if kickoff else "未核實"
    lines = [
        "# 足球王者｜逐場研究報告（非正式投注推薦）",
        f"**賽事：{home} VS {away}**",
        f"- 賽事類別：{_text(fixture.get('competition_zh'))}",
        f"- 開賽：{kickoff_hk}（香港時間）",
        f"- 報告時間：{now.astimezone(HK).strftime('%Y-%m-%d %H:%M:%S')}（香港時間）",
        "- 系統狀態：**HOLD｜RESEARCH_ONLY**",
        "- 正式投注推薦：停用（production_recommendations=DISABLED）",
    ]
    if not identity_ok:
        lines.append("- 賽事身份：**身份未能確認**，禁止發佈合資格模型比較")
    else:
        lines.append("- 賽事身份：來源識別碼已提供，**仍未獲獨立認證**")

    lines += ["", "## 1. 即時盤口與實際賠率"]
    odds = quote.get("decimal_odds")
    updated, captured = _datetime(quote.get("updated_utc")), _datetime(quote.get("captured_utc"))
    url = quote.get("source_url")
    source_ok = (isinstance(url, str) and url.startswith("https://") and " " not in url)
    structural_quote_ok = (
        identity_ok and kickoff is not None and now < kickoff
        and _valid_odds(odds) and updated is not None and captured is not None
        and updated <= captured <= now and updated < kickoff
        and (now - updated) <= timedelta(seconds=120)
        and _text(quote.get("bookmaker")) != "未核實"
        and _text(quote.get("market_zh")) != "未核實"
        and _text(quote.get("selection_zh")) != "未核實"
        and source_ok
    )
    if _valid_odds(odds):
        lines.append(f"- 歷史研究報價：{_text(quote.get('bookmaker'))}｜"
                     f"{_text(quote.get('market_zh'))}｜{_text(quote.get('selection_zh'))} "
                     f"@{odds:.2f}")
    else:
        lines.append("- 盤口：未提供可核查資料")
    if structural_quote_ok:
        lines.append("- 報價時間結構：120秒內、賽前擷取（**未獨立認證可成交性**）")
        if odds < 1.80:
            lines.append("- 價格門檻：低於1.80，研究篩選不通過")
        else:
            lines.append("- 價格門檻：達1.80（只係數值門檻，**唔代表正EV**）")
    else:
        lines.append("- 報價狀態：**過時／未通過**身份、來源、時間或盤口結構檢查；不可當即時盤口")
    lines.append(f"- 來源連結（輸入資料聲稱）：{_text(url, '未提供', 250) if source_ok else '未提供有效HTTPS來源'}")

    lines += ["", "## 2. 模型數據（研究用途）"]
    models = payload.get("models")
    any_model = False
    if isinstance(models, list) and identity_ok and kickoff and now < kickoff:
        for entry in models[:5]:
            model = _safe_dict(entry)
            cutoff = _datetime(model.get("forecast_cutoff_utc"))
            p = model.get("probability")
            if (cutoff is not None and cutoff < kickoff and cutoff <= now
                    and _is_probability(p) and _text(model.get("name")) != "未核實"):
                lines.append(f"- {_text(model.get('name'))}：{100*p:.1f}%"
                             "（輸入的未認證研究機率，未核實校準及資料來源）")
                any_model = True
    if not any_model:
        lines.append("- 未提供合資格賽前封存模型機率；不會補造概率")
    lines += ["", "## 3. 戰術、戰意及風險"]
    lines.append(f"- 戰術研究假設（未核實）：{_text(payload.get('tactical_note'), '待查證')}")
    lines.append(f"- 戰意與陣容（未核實）：{_text(payload.get('motivation_note'), '待查證')}")
    lines += ["", "## 4. EV與最終結論",
              "- 正EV：未獲認證（未有獨立校準機率下界、經認證可成交價格與時間證據）",
              "- 推薦方向：**HOLD／不發出正式投注建議**",
              "- 風險：表面模型與盤口同向不證明有優勢；不可由市場賠率反推獨立優勢。"]
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description="Football King research-only HK report")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.input.stat().st_size > 2_000_000:
        raise ValueError("INPUT_TOO_LARGE")
    payload = json.loads(args.input.read_text(encoding="utf-8"))
    result = render_card(payload)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(result, encoding="utf-8")


if __name__ == "__main__":
    main()

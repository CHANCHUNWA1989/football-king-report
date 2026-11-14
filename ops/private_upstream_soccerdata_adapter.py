"""Opt-in upstream soccerdata MatchHistory adapter for settled matches only.

Historical match data is never proof of a pre-match captured prediction or odds.
No network calls occur in this adapter; callers explicitly supply a DataFrame.
"""
from datetime import datetime
from numbers import Real
import math


def adapt_matchhistory_frame(frame, *, source="soccerdata.MatchHistory", max_rows=5000):
    if source != "soccerdata.MatchHistory":
        raise ValueError("UNRECOGNIZED_DATA_SOURCE")
    if type(max_rows) is not int or not 1 <= max_rows <= 50000:
        raise ValueError("INVALID_ROW_LIMIT")
    if not hasattr(frame, "columns") or not hasattr(frame, "iterrows"):
        raise ValueError("EXPECTED_DATAFRAME")
    required = {"date", "home_team", "away_team", "FTHG", "FTAG"}
    if not required.issubset(set(frame.columns)):
        raise ValueError("MISSING_MATCHHISTORY_FIELDS")
    if not 0 < len(frame) <= max_rows:
        raise ValueError("INVALID_DATAFRAME_SIZE")
    records = []
    for idx, row in frame.iterrows():
        home, away = row["home_team"], row["away_team"]
        if not isinstance(home, str) or not home.strip() or not isinstance(away, str) or not away.strip() or home == away:
            raise ValueError("INVALID_TEAM")
        hg, ag = row["FTHG"], row["FTAG"]
        if isinstance(hg, bool) or isinstance(ag, bool) or not isinstance(hg, Real) or not isinstance(ag, Real) or not math.isfinite(hg) or not math.isfinite(ag) or int(hg) != hg or int(ag) != ag or not (0 <= hg <= 30 and 0 <= ag <= 30):
            raise ValueError("INVALID_FINAL_SCORE")
        date = row["date"]
        if not isinstance(date, datetime) or date.tzinfo is not None:
            raise ValueError("DATE_MUST_BE_NAIVE_SOURCE_LOCAL")
        # MatchHistory dates are not guaranteed timezone-aware or exact kickoff.
        # Never silently label a source-local datetime as UTC kickoff.
        records.append({"source": source, "source_index": str(idx),
                        "source_local_match_datetime": date.isoformat(),
                        "kickoff_utc": None, "kickoff_time_verified": False,
                        "home_team": home.strip(), "away_team": away.strip(),
                        "home_goals": int(hg), "away_goals": int(ag),
                        "outcome": "H" if hg > ag else "A" if hg < ag else "D",
                        "odds_capture_verified": False, "pre_match_features_verified": False,
                        "production_recommendations": "DISABLED"})
    return {"status": "RESEARCH_ONLY", "provider": source, "count": len(records),
            "records": records, "production_recommendations": "DISABLED",
            "point_in_time_backtest_ready": False}


def read_upstream_matchhistory(*, leagues, seasons, data_dir=None):
    if not isinstance(leagues, (list, tuple)) or not leagues or not all(isinstance(x, str) and x for x in leagues):
        raise ValueError("INVALID_LEAGUES")
    if not isinstance(seasons, (list, tuple)) or not seasons:
        raise ValueError("INVALID_SEASONS")
    try:
        from soccerdata import MatchHistory
    except ImportError as exc:
        raise ValueError("OPTIONAL_SOCCERDATA_NOT_INSTALLED") from exc
    kwargs = {"leagues": list(leagues), "seasons": list(seasons)}
    if data_dir is not None:
        kwargs["data_dir"] = data_dir
    # Network access is initiated by upstream read_games(); call only with
    # source rights and permission. No call to read_games is made here.
    return MatchHistory(**kwargs)

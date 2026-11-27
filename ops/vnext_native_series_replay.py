"""Offline contiguous native-archive replay; no live collector or authentication."""
import json
from live_snapshot_adapter import hold
from inplay_state_challenger_vnext import _clock
from vnext_native_prematch_bridge import build_prematch
from vnext_live_evidence_cut import audit_cut

MAX_CUTS = 120

def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)

def replay_series(raw, archive_sha256, *, fixture_id, home_native_id,
                  away_native_id, kickoff_utc, cuts):
    """Require one fixed archive and contiguous per-source states.
    Caller-supplied historical decision clocks and digests are not attested.
    Never return partial diagnostics after a rejected cut.
    """
    try:
        if type(cuts) is not list or not 1 <= len(cuts) <= MAX_CUTS:
            return hold("INVALID_SERIES")
        prematch = build_prematch(raw, archive_sha256, fixture_id=fixture_id,
            home_native_id=home_native_id, away_native_id=away_native_id,
            kickoff_utc=kickoff_utc)
        kickoff = _clock(kickoff_utc)
        frozen = _canonical(prematch)
        previous = None
        diagnostics = []
        for cut in cuts:
            if type(cut) is not dict or set(cut) != {"envelope","snapshot","expected_digest","decision_epoch"}:
                return hold("INVALID_SERIES_CUT")
            e = cut["envelope"]
            now = cut["decision_epoch"]
            if type(now) is not int or type(e) is not dict:
                return hold("INVALID_SERIES_CUT")
            if _clock(e["model"]["kickoff_utc"]) != kickoff:
                return hold("SERIES_KICKOFF_MISMATCH")
            if _canonical(e["model"]["prematch"]) != frozen:
                return hold("PREMATCH_ARCHIVE_MISMATCH")
            if previous is not None:
                if now <= previous["decision_epoch"]:
                    return hold("SERIES_CLOCK_ORDER")
                for key in ("a","b"):
                    if _canonical(e["previous_"+key]) != _canonical(previous[key]):
                        return hold("SERIES_HISTORY_DISCONTINUITY")
            out = audit_cut(e, cut["snapshot"], cut["expected_digest"], now)
            if out.get("cut_status") != "STRUCTURAL_RESEARCH_ONLY":
                return hold("SERIES_EVIDENCE_REJECTED")
            diagnostics.append({"decision_epoch":now,
                "minute":e["a"]["minute"],
                "score":[e["a"]["home"],e["a"]["away"]],
                "red_cards":[e["a"]["red_home"],e["a"]["red_away"]],
                "cut_sha256_unattested":out["cut_sha256_unattested"],
                "research_diagnostics":out["research_diagnostics"]})
            previous = e
        return {**hold("UNAUTHENTICATED_HISTORICAL_SERIES"),
                "series_status":"STRUCTURAL_RESEARCH_ONLY",
                "archive_sha256_unattested":archive_sha256,
                "fixture_id":fixture_id,"cut_count":len(diagnostics),
                "cuts":diagnostics,"model_edge":None,"actual_xg":None,
                "actual_quote_verified":False,"historical_clock_attested":False,
                "verified_forward_sample_credit":0}
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError,
            OSError, RecursionError):
        return hold("INVALID_SERIES")

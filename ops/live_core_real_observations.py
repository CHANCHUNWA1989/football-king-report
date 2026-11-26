"""Real-fixture observation research adapter; no provider authentication or release.

Caller supplies normalized, timestamped publisher evidence. Never infer missing
red cards, substitute zero xG, or label a quote executable. No network/secrets.
Uses the existing fixed-coefficient challenger and unified score matrix.
"""
import hashlib
import json
import math
from datetime import datetime, timezone
from urllib.parse import urlsplit

from live_snapshot_adapter import check, hold, research_predict, valid
from inplay_state_challenger_vnext import remaining_matrix
from score_distribution_vnext import market_distribution, one_x_two, MAX_MARKETS


def digest(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, allow_nan=False,
                                    separators=(",", ":")).encode()).hexdigest()


def epoch_iso(epoch):
    return datetime.fromtimestamp(epoch, timezone.utc).isoformat()


def evidence(item, now):
    if type(item) is not dict or set(item) != {"state", "url", "payload_sha256"}:
        raise ValueError("INVALID_EVIDENCE")
    s = item["state"]
    if not valid(s) or s["fixture_id"].startswith("synthetic-"):
        raise ValueError("REAL_FIXTURE_STATE_REQUIRED")
    url, sha = item["url"], item["payload_sha256"]
    if type(url) is not str or len(url) > 2048:
        raise ValueError("INVALID_SOURCE_URL")
    u = urlsplit(url)
    if u.scheme != "https" or not u.hostname or u.username or u.password or u.query or u.fragment:
        raise ValueError("INVALID_SOURCE_URL")
    if type(sha) is not str or len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha):
        raise ValueError("INVALID_PAYLOAD_DIGEST")
    if not 0 <= now - s["observed"] <= 90 or s["received"] > now:
        raise ValueError("STALE_OR_FUTURE")
    return s, u.hostname.lower().removeprefix("www.")


def research(a, b, *, kickoff_utc, prematch, now, markets, xg=None, previous=None):
    """Offline structural validation of externally captured, real-fixture claims.

    xG is an optional same-cut diagnostic (not a fitted model input).
    Markets describe regulation full-time lines only, not executable prices.
    No attested source, independently verified sample or positive EV is claimed.
    """
    try:
        if type(now) is not int or not 0 < now < 4102444800:
            raise ValueError("INVALID_DECISION_CLOCK")
        left, lh = evidence(a, now)
        right, rh = evidence(b, now)
        if lh == rh or a["payload_sha256"] == b["payload_sha256"]:
            raise ValueError("DUPLICATE_PUBLISHER_OR_PAYLOAD")
        state = left
        model = dict(fixture_id=state["fixture_id"], kickoff_utc=kickoff_utc,
                     decision_utc=epoch_iso(now), minute_elapsed=state["minute"],
                     score_home=state["home"], score_away=state["away"],
                     red_home=state["red_home"], red_away=state["red_away"],
                     prematch=prematch, event_consensus=dict(
                         status="RESEARCH_ONLY", fixture_id=state["fixture_id"],
                         decision_utc=epoch_iso(now), score_home=state["home"],
                         score_away=state["away"], active_red_cards={
                             "HOME":state["red_home"], "AWAY":state["red_away"]},
                         evidence_input_sha256=digest([a,b]),
                         production_recommendations="DISABLED",
                         model_scoring_eligible=False, source_authenticated=False,
                         source_independence_verified=False))
        reason = check(left, right, model, now, previous)
        if reason != "CONSISTENT":
            return hold(reason)
        if type(markets) is not list or not 1 <= len(markets) <= MAX_MARKETS:
            raise ValueError("INVALID_MARKETS")
        for m in markets:
            if type(m) is not dict or set(m) != {"market", "side", "line"}:
                raise ValueError("INVALID_MARKET")
        if len({digest(m) for m in markets}) != len(markets):
            raise ValueError("DUPLICATE_MARKET")
        if xg is not None:
            if type(xg) is not dict or set(xg) != {"fixture_id","observed","minute","home","away","source_url"}:
                raise ValueError("INVALID_XG")
            if (xg["fixture_id"] != state["fixture_id"] or type(xg["minute"]) is not int
                    or xg["minute"] != state["minute"] or type(xg["observed"]) is not int
                    or not 0 <= now-xg["observed"] <= 90
                    or any(abs(xg["observed"]-s["observed"]) > 30 for s in (left,right))
                    or any(type(xg[k]) not in (int,float) or not math.isfinite(xg[k])
                           or not 0 <= xg[k] <= 30 for k in ("home","away"))):
                raise ValueError("XG_NOT_SAME_CUT")
            if type(xg["source_url"]) is not str or len(xg["source_url"]) > 2048:
                raise ValueError("INVALID_XG_URL")
            xu = urlsplit(xg["source_url"])
            if xu.scheme != "https" or not xu.hostname or xu.username or xu.password or xu.query or xu.fragment:
                raise ValueError("INVALID_XG_URL")
        out = research_predict(left, right, model, now, previous)
        if out.get("status") != "RESEARCH_ONLY":
            return hold("CHALLENGER_REJECTED")
        grid = remaining_matrix(out["remaining_expected_home_goals"],
                                out["remaining_expected_away_goals"],
                                state["home"],state["away"])
        probs = one_x_two(grid)
        if any(not math.isclose(probs[k],out["fulltime_probabilities"][k],
                                rel_tol=0,abs_tol=1e-12) for k in probs):
            return hold("MATRIX_MISMATCH")
        distributions = [market_distribution(grid, **m) for m in markets]
        return {**hold("UNATTESTED_REAL_OBSERVATION_RESEARCH"),
                "research_status":"RESEARCH_ONLY", "fixture_id":state["fixture_id"],
                "decision_utc":epoch_iso(now), "input_sha256_unattested":digest(
                    [a,b,kickoff_utc,prematch,markets,xg,previous,now]),
                "model_id":out["model_id"], "probabilities_1x2":probs,
                "top_fulltime_scores":out["top_fulltime_scores"],
                "market_distributions":distributions,
                "xg_claim_same_cut":xg, "xg_used_by_model":False,
                "actual_xg_verified":False, "actual_live_odds_verified":False,
                "model_edge":None, "real_requests":0, "verified_forward_sample_credit":0}
    except (ValueError,TypeError,KeyError,AttributeError,OverflowError,OSError,RecursionError):
        return hold("INVALID_RESEARCH_OBSERVATIONS")


def main():
    import argparse
    from pathlib import Path
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("input", type=Path)
    args = p.parse_args()
    def unique(pairs):
        obj = {}
        for k,v in pairs:
            if k in obj:
                raise ValueError("DUPLICATE_JSON_KEY")
            obj[k] = v
        return obj
    def reject(value):
        raise ValueError("NONFINITE_JSON")
    try:
        with args.input.open("rb") as f:
            raw = f.read(1000001)
        if len(raw) > 1000000:
            raise ValueError("INPUT_TOO_LARGE")
        obj = json.loads(raw,object_pairs_hook=unique,parse_constant=reject)
        out = research(**obj)
    except (ValueError,TypeError,OSError,RecursionError):
        out = hold("INVALID_INPUT_FILE")
    print(json.dumps(out,allow_nan=False,sort_keys=True))


if __name__ == "__main__":
    main()

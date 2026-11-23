"""Read-only policy preflight for a prospective women's WE League in-play pilot.

This is a pinned legal/capability *blocking* registry, not a permission grant.
Terms and catalogue evidence current as researched 2026-11-23 (HKT).
No network calls, credential inspection, scraping, TSA requests, live prices,
model evaluation or approval. No JSON caller flag may promote eligibility.
"""
import argparse
import json

SCHEMA = "football-king-inplay-source-rights-preflight-v1"
POLICY_REVIEWED = "2026-11-23"
ROLES = ("fixture", "score_primary", "score_secondary", "market", "timestamp")
MARKETS = frozenset(("HKJC_THREE_WAY_HANDICAP", "H2H_1X2", "ASIAN_HANDICAP", "TOTALS"))
LEAGUES = frozenset(("japan_we_league", "japan_j_league"))
PROVIDERS = {
    "we_league_official": {
        "roles": frozenset(("fixture", "score_primary", "score_secondary")),
        "rights_status": "NO_AUTOMATED_REUSE_PERMISSION_ON_RECORD",
        "evidence": "https://weleague.jp/legal/",
    },
    "fotmob": {
        "roles": frozenset(("score_primary", "score_secondary")),
        "rights_status": "WRITTEN_CONSENT_REQUIRED_FOR_AUTOMATED_EXTRACTION",
        "evidence": "https://www.fotmob.com/tos.txt",
    },
    "hkjc": {
        "roles": frozenset(("market",)),
        "rights_status": "NO_HKJC_PROGRAMMATIC_ODDS_GRANT_ON_RECORD",
        "evidence": "https://www.hkjc.com/en-us/disclaimer",
    },
    "the_odds_api_v4": {
        "roles": frozenset(("market",)),
        "rights_status": "GENERAL_API_RESEARCH_TERMS_PERMIT_NOT_EVENT_ENTITLEMENT",
        "evidence": "https://the-odds-api.com/terms-and-conditions.html",
        "catalogue": "https://the-odds-api.com/sports-odds-data/sports-apis.html",
    },
    "freetsa": {
        "roles": frozenset(("timestamp",)),
        "rights_status": "PUBLIC_TSA_CANDIDATE_NOT_REVIEWED_AS_TRUST_ANCHOR",
        "evidence": "https://www.freetsa.org/freetsa.html",
        "certificate": "https://freetsa.org/index_en.php",
    },
}

DEFAULT_WE_LEAGUE_PLAN = {
    "fixture": "we_league_official",
    "score_primary": "we_league_official",
    "score_secondary": "fotmob",
    "market": "hkjc",
    "timestamp": "freetsa",
}


def _hold(reasons, roles=None):
    return {
        "schema": SCHEMA,
        "policy_reviewed_hkt_date": POLICY_REVIEWED,
        "status": "HOLD",
        "decision": "HOLD",
        "production_recommendations": "DISABLED",
        "allow_network_collection": False,
        "allow_automatic_scraping": False,
        "allow_raw_data_publication": False,
        "allow_betting": False,
        "manual_legal_approval_record_verified": False,
        "two_independent_live_scores_authenticated": False,
        "market_inplay_coverage_verified": False,
        "market_executable_verified": False,
        "trusted_tsa_identity_and_revocation_verified": False,
        "positive_ev_verified": False,
        "model_scoring_eligible": False,
        "certified_forward_samples": 0,
        "role_review": [] if roles is None else roles,
        "blockers": sorted(set(reasons)),
    }


def audit(plan, *, league="japan_we_league", market="HKJC_THREE_WAY_HANDICAP"):
    """Produce an untrusted policy gap assessment, never a rights approval.

    The source IDs come from the fixed policy, not a supplied licence claim.
    To change the policy requires a reviewed code change and separately
    verified source-native licence/contract and entitlement evidence.
    """
    if (type(plan) is not dict or set(plan) != set(ROLES)
            or type(league) is not str or league not in LEAGUES
            or type(market) is not str or market not in MARKETS):
        return _hold(["INVALID_PILOT_SCOPE_OR_PLAN"])
    if any(type(v) is not str or v not in PROVIDERS for v in plan.values()):
        return _hold(["UNKNOWN_OR_UNTRUSTED_PROVIDER"])
    roles, blockers = [], []
    for role in ROLES:
        name = plan[role]
        provider = PROVIDERS[name]
        reasons = []
        if role not in provider["roles"]:
            reasons.append("PROVIDER_NOT_APPROVED_FOR_ROLE")
        if name == "fotmob":
            reasons.append("WRITTEN_FOTMOB_CONSENT_MISSING")
        elif name == "we_league_official":
            reasons.append("WE_LEAGUE_BULK_OR_API_REUSE_RIGHTS_MISSING")
        elif name == "hkjc":
            reasons.append("HKJC_AUTHORIZED_PROGRAMMATIC_MARKET_ACCESS_MISSING")
        elif name == "the_odds_api_v4":
            # Public API T&Cs allow analytics; no account entitlement,
            # bookmaker or league/market coverage is established here.
            reasons.append("API_PLAN_AND_MARKET_ENTITLEMENT_UNVERIFIED")
            if league == "japan_we_league":
                reasons.append("WE_LEAGUE_NOT_DOCUMENTED_IN_PUBLIC_SPORTS_LIST")
            if market == "HKJC_THREE_WAY_HANDICAP":
                reasons.append("HKJC_THREE_WAY_CONTRACT_NOT_DOCUMENTED_IN_API")
        elif name == "freetsa":
            reasons.extend(("EXTERNAL_TSA_TOKEN_NOT_REQUESTED",
                            "TSA_CA_POLICY_REVOCATION_NOT_REVIEWED",
                            "BEST_EFFORT_TSA_NO_SLA"))
        role_info = {
            "role": role, "source": name,
            "policy_status": provider["rights_status"],
            "source_terms": provider["evidence"],
            "status": "BLOCKED",
            "reasons": sorted(set(reasons)),
        }
        roles.append(role_info)
        blockers.extend(role_info["reasons"])
    if plan["score_primary"] == plan["score_secondary"]:
        blockers.append("DUPLICATE_SCORE_PUBLISHER")
    # Two *names* cannot establish independence of underlying feeds.
    blockers.extend((
        "INDEPENDENT_SCORE_COLLECTION_NOT_ATTESTED",
        "PRESEALED_NATIVE_FIXTURE_IDS_NOT_EXTERNALLY_VERIFIED",
        "LIVE_SOURCE_UPDATE_TIMES_NOT_AUTHENTICATED",
        "QUOTE_EXECUTION_NOT_ATTESTED",
        "NO_TRUSTED_PROSPECTIVE_TSA_CAPTURE",
    ))
    return _hold(blockers, roles)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--league", default="japan_we_league", choices=sorted(LEAGUES))
    parser.add_argument("--market", default="HKJC_THREE_WAY_HANDICAP", choices=sorted(MARKETS))
    args = parser.parse_args(argv)
    result = audit(DEFAULT_WE_LEAGUE_PLAN, league=args.league, market=args.market)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 2  # Not permitted to run a source collector, regardless of plan.


if __name__ == "__main__":
    raise SystemExit(main())

"""Same-cohort four-way descriptive calibration and paired uncertainty.

Never fits a calibration map, fills missing challengers, certifies outcomes,
or derives executable prices/EV from de-vigged consensus probabilities.
"""
import math
import random
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from model_ab import matches_sealed as valid_b
from model_market_challenger import matches_sealed as valid_c
from model_market_bias_audit import audit as validate_pairs

FIELDS = {"A":"p", "B":"ab", "C":"c", "market":"m"}
OUTCOMES = ("home","draw","away")
HK = ZoneInfo("Asia/Hong_Kong")
REPEATS = 1000

def clock(value):
    if not isinstance(value,str):
        raise ValueError("INVALID_CLOCK")
    t=datetime.fromisoformat(value.replace("Z","+00:00"))
    if t.tzinfo is None:
        raise ValueError("NAIVE_CLOCK")
    return t.astimezone(timezone.utc)

def score(p,y):
    return (-math.log(max(p[y],1e-15)),
            math.fsum((v-int(i==y))**2 for i,v in enumerate(p)))

def calibration(rows,field):
    bins=[[{"n":0,"sum":0.,"hits":0} for _ in range(5)] for _ in OUTCOMES]
    for r in rows:
        for i,v in enumerate(r[field]):
            b=bins[i][min(4,int(v*5))]
            b["n"]+=1
            b["sum"]+=v
            b["hits"]+=int(r["y"]==i)
    out={}
    for label,group in zip(OUTCOMES,bins):
        cells=[]
        for j,b in enumerate(group):
            n=b["n"]
            cells.append({"lower":j/5,"upper":(j+1)/5,"n":n,
                "mean_probability":b["sum"]/n if n else None,
                "observed_frequency":b["hits"]/n if n else None})
        out[label]={"bins":cells,"class_ece":(
            math.fsum(abs(b["sum"]-b["hits"]) for b in group)/len(rows)
            if rows else None)}
    return out

def _interval(blocks):
    # Resample complete calendar-week blocks, not individual fixtures.
    # Sum/count weighting preserves unequal block sizes.
    rng=random.Random(20261126)
    n=len(blocks)
    values=[]
    for _ in range(REPEATS):
        picks=[blocks[rng.randrange(n)] for _ in range(n)]
        values.append(math.fsum(x[0] for x in picks)/sum(x[1] for x in picks))
    values.sort()
    return [values[int(.025*(REPEATS-1))],values[int(.975*(REPEATS-1))]]

def build(rows, *, checked_utc):
    report={"schema":"football-king-fourway-calibration-diagnostic-v1",
            "status":"HOLD","production_recommendations":"DISABLED",
            "outcomes_independently_authenticated":False,
            "authenticated_forward_samples":0,"calibration_verified":False,
            "model_advantage_vs_market_proven":False,"positive_ev_verified":False,
            "executable_market_prices_available":False,
            "promotion_allowed":False,"recommendations":[],
            "descriptive_only":True,"cohort_count":0,"excluded_count":0,
            "models":{},"paired_market_differences":{}}
    if not isinstance(rows,list) or len(rows)>30000:
        raise ValueError("INVALID_ROWS")
    report["input_count"]=len(rows)
    if not rows:
        return report
    validate_pairs(rows,archived_at_utc=checked_utc)
    checked=clock(checked_utc)
    cohort=[]
    for r in rows:
        if clock(r["kickoff_utc"])+timedelta(minutes=120)>checked:
            raise ValueError("IMMATURE_SETTLEMENT")
        if r.get("fixture_result_source_independently_verified") is not False:
            raise ValueError("UNSAFE_RESULT_PROVENANCE")
        b_present="ab" in r or r.get("ab_model") is not None
        c_present="c" in r or "c_model" in r
        b=valid_b(r["p"],r.get("ab"),r.get("ab_model"))
        c=valid_c(r["p"],r["m"],r.get("c"),r.get("c_model"))
        if (b_present and not b) or (c_present and not c):
            raise ValueError("INVALID_SEALED_CHALLENGER")
        if not (b and c):
            continue
        # Normalize for diagnostic comparability only; input vectors untouched.
        cohort.append({**r,**{f:[v/math.fsum(r[f]) for v in r[f]]
                              for f in FIELDS.values()}})
    report["cohort_count"]=len(cohort)
    report["excluded_count"]=len(rows)-len(cohort)
    if not cohort:
        return report
    n=len(cohort)
    leagues=Counter(r["league"] for r in cohort)
    def week(r):
        return clock(r["kickoff_utc"]).astimezone(HK).strftime("%G-W%V")
    weeks=set(map(week,cohort))
    enough=n>=300 and len(weeks)>=12 and sum(v>=40 for v in leagues.values())>=4
    report.update(status="RESEARCH_ONLY",hk_week_blocks=len(weeks),
                  league_counts=dict(leagues),descriptive_coverage_met=enough,
                  interval_method="HK_CALENDAR_WEEK_PAIRED_BLOCK_BOOTSTRAP_PERCENTILE",
                  bootstrap_repeats=REPEATS,
                  interval_is_not_authentication_or_simultaneous_inference=True)
    for label,field in FIELDS.items():
        scores=[score(r[field],r["y"]) for r in cohort]
        report["models"][label]={"n":n,
            "log_loss":math.fsum(x[0] for x in scores)/n,
            "brier":math.fsum(x[1] for x in scores)/n,
            "class_calibration":calibration(cohort,field)}
        if label=="market":
            continue
        grouped=defaultdict(list)
        for r,(ll,bs) in zip(cohort,scores):
            ml,mb=score(r["m"],r["y"])
            grouped[week(r)].append((ml-ll,mb-bs))
        sums=[[(math.fsum(x[j] for x in grouped[k]),len(grouped[k]))
                for k in sorted(grouped)] for j in (0,1)]
        report["paired_market_differences"][label]={
            "market_minus_model_log_loss":math.fsum(x[0] for x in sums[0])/n,
            "market_minus_model_brier":math.fsum(x[0] for x in sums[1])/n,
            "log_loss_ci95":_interval(sums[0]) if enough else None,
            "brier_ci95":_interval(sums[1]) if enough else None}
    return report


def report_diagnostic(rows, *, checked_utc):
    """Isolate optional diagnostic rejection from the existing legacy report."""
    try:
        return build(rows, checked_utc=checked_utc)
    except (ValueError, KeyError, TypeError, OverflowError):
        # Do not repair or re-label missing provenance; reject the entire cohort.
        out = build([], checked_utc=checked_utc)
        out.update(reason="DIAGNOSTIC_INPUT_REJECTED",
                   input_count=len(rows) if isinstance(rows,list) else None,
                   excluded_count=len(rows) if isinstance(rows,list) else None)
        return out

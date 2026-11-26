"""Prospective read-only market projections from one bounded Poisson grid.

Not a bookmaker line, calibrated probability, sealed original prediction or EV.
Original 1X2 is preserved separately; no half-time/live inference from FT rates.
"""
import math
from collections import Counter
from datetime import datetime, timedelta, timezone
from ops.asian_handicap_research import TYPES, MAX_GOALS, _poisson, split_lines
from ops.shadow_forecast import poisson_1x2

MODEL = "poisson-shrinkage-unvalidated-v4.1"
MAX_ROWS = 3000
AH = range(-20, 21)
TOTALS = range(0, 21)
DISABLED = "DISABLED"

def clock(value):
    if not isinstance(value, str):
        raise ValueError("MISSING_CLOCK")
    d = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if d.tzinfo is None:
        raise ValueError("NAIVE_CLOCK")
    return d.astimezone(timezone.utc)

def projection(mass, side, units):
    line = units / 4
    left, right = split_lines(line)
    out = dict.fromkeys(TYPES, 0.0)
    reverse = side in ("AWAY", "UNDER")
    for value, p in mass.items():
        v = -value if reverse else value
        # Handicap adds its line; over subtracts it; under adds it.
        legs = (-left, -right) if side == "OVER" else (left, right)
        net = sum((4*v+k > 0)-(4*v+k < 0) for k in legs)
        out[{2:"FULL_WIN", 1:"HALF_WIN", 0:"PUSH",
             -1:"HALF_LOSS", -2:"FULL_LOSS"}[net]] += p
    if abs(math.fsum(out.values())-1) > 1e-8:
        raise ValueError("BAD_PROJECTION_MASS")
    return {"side":side, "hypothetical_line":line, "probabilities":out}

def distribution(hg, ag):
    h, a = _poisson(hg), _poisson(ag)
    margins = dict.fromkeys(range(-MAX_GOALS, MAX_GOALS+1), 0.0)
    totals = dict.fromkeys(range(2*MAX_GOALS+1), 0.0)
    for i, ph in enumerate(h):
        for j, pa in enumerate(a):
            p = ph*pa
            margins[i-j] += p
            totals[i+j] += p
    one = [math.fsum(v for k,v in margins.items() if k>0), margins[0],
           math.fsum(v for k,v in margins.items() if k<0)]
    if abs(math.fsum(one)-1) > 1e-8:
        raise ValueError("BAD_GRID_MASS")
    return {"grid_max_goals_each":MAX_GOALS,
            "conditioned_on_truncation":True,
            "derived_1x2":one, "margin_distribution":margins,
            "total_distribution":totals,
            "asian_handicap":[projection(margins, side, u)
                              for side in ("HOME","AWAY") for u in AH],
            "totals":[projection(totals, side, u)
                      for side in ("OVER","UNDER") for u in TOTALS]}

def build(core, worldwide, *, now=None):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("NAIVE_NOW")
    report = {"schema":"football-king-unified-market-grid-v1",
              "generated_utc":now.isoformat(), "status":"HOLD",
              "production_recommendations":DISABLED, "recommendations":[],
              "actual_bookmaker_quotes":False, "positive_ev_verified":False,
              "model_calibrated":False, "original_forecasts_rewritten":False,
              "half_time_model":"HOLD_NO_SEPARATE_DISTRIBUTION",
              "live_model":"HOLD_NO_SEPARATE_DISTRIBUTION",
              "hypothetical_lines_only":True, "sources":{}, "rows":[],
              "exclusions":{}, "qualified_research_rows":0}
    reasons = Counter()
    for source, doc in (("core",core),("worldwide",worldwide)):
        try:
            if (not isinstance(doc,dict) or doc.get("status")!="SHADOW_ONLY"
                    or doc.get("production_recommendations")!=DISABLED
                    or doc.get("model_calibrated") is not False
                    or not isinstance(doc.get("predictions"),list)
                    or len(doc["predictions"])>MAX_ROWS):
                raise ValueError("MISSING_OR_UNSAFE_SOURCE")
            stamp=clock(doc["as_of_utc"])
            if not now-timedelta(hours=10)<=stamp<=now:
                raise ValueError("STALE_OR_FUTURE_SOURCE")
        except (KeyError,ValueError,TypeError,OverflowError) as exc:
            report["sources"][source]="HOLD"
            reasons[str(exc) if isinstance(exc,ValueError) else "INVALID_SOURCE"]+=1
            continue
        report["sources"][source]="RESEARCH_ONLY"
        native_ids=Counter(p.get("event_id") for p in doc["predictions"]
                           if isinstance(p,dict) and isinstance(p.get("event_id"),str))
        for item in doc["predictions"]:
            try:
                if (not isinstance(item,dict) or item.get("model")!=MODEL
                        or item.get("production_recommendations")!=DISABLED
                        or item.get("calibrated") is not False
                        or item.get("verified_market_odds") is not False
                        or any(item.get(k) is not None for k in ("score_ft","result","y","historical_outcome"))):
                    raise ValueError("UNSAFE_FORECAST")
                event, league, home, away = (item[k] for k in ("event_id","league","home","away"))
                if (not all(isinstance(x,str) and 0<len(x)<=200 for x in (event,league,home,away))
                        or home==away or native_ids[event]!=1):
                    raise ValueError("AMBIGUOUS_IDENTITY")
                ko,pred=clock(item["kickoff_utc"]),clock(item["prediction_utc"])
                if not stamp-timedelta(minutes=10)<=pred<=stamp<=now<ko<=now+timedelta(days=7):
                    raise ValueError("NOT_CURRENT_PREMATCH")
                hg,ag=item["expected_home_goals"],item["expected_away_goals"]
                original=[item[k] for k in ("p_home","p_draw","p_away")]
                if not all(type(v) in (int,float) and math.isfinite(v) and 0<=v<=1 for v in original):
                    raise ValueError("INVALID_ORIGINAL_PROBABILITY")
                if abs(math.fsum(original)-1)>0.000001:
                    raise ValueError("INVALID_ORIGINAL_MASS")
                # Original implementation uses a 12x12 grid and rounded rates.
                # 0.00003 covers 5dp rate rounding; expanded grid is separate.
                _poisson(hg); _poisson(ag)
                replay=poisson_1x2(hg,ag)
                if max(abs(x-y) for x,y in zip(replay,original))>0.00003:
                    raise ValueError("ORIGINAL_RATE_PROBABILITY_CONFLICT")
                grid=distribution(hg,ag)
                report["rows"].append({"source":source,"event_id":event,
                    "league":league,"home":home,"away":away,
                    "kickoff_utc":ko.isoformat(),"source_prediction_utc":pred.isoformat(),
                    "expected_home_goals":hg,"expected_away_goals":ag,
                    "original_1x2":original,
                    "expanded_grid_max_original_gap":max(abs(x-y) for x,y in zip(grid["derived_1x2"],original)),
                    "derived_grid":grid,"production_recommendations":DISABLED})
            except (ValueError,KeyError,TypeError,OverflowError) as exc:
                reasons[str(exc) if isinstance(exc,ValueError) else "INVALID_FORECAST"]+=1
    report["qualified_research_rows"]=len(report["rows"])
    report["exclusions"]=dict(reasons)
    if report["rows"]:
        report["status"]="RESEARCH_ONLY"
    return report

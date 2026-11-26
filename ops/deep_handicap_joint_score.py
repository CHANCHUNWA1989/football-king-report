"""DHE joint score research projection; no market or calibration certification."""
import math
from decimal import Decimal, InvalidOperation
from collections import defaultdict
from asian_handicap_research import TYPES, quarter_units, _poisson
from asian_ev_research import asian_net

SCHEMA = "football-king-dhe-joint-score-v1"
PACE = (0.65, 0.85, 1.0)
NET_GRADE = {1.0: "FULL_WIN", .5: "HALF_WIN", 0.0: "PUSH",
             -.5: "HALF_LOSS", -1.0: "FULL_LOSS"}


def _half(rate):
    terms = [math.exp(-rate)]
    for i in range(1, 25):
        terms.append(terms[-1]*rate/i)
    mass = math.fsum(terms)
    return [v/mass for v in terms]


def _add_period(first, h, a, out):
    """Separable convolution of a possibly conditional first-half matrix."""
    intermediate = defaultdict(float)
    for (fh, fa), p in first.items():
        for sh, q in enumerate(h):
            intermediate[fh+sh, fa] += p*q
    for (fh, fa), p in intermediate.items():
        for sa, q in enumerate(a):
            out[fh, fa+sa] += p*q


def score_distribution(home, away, side, pace=1.0):
    """Full-time score PMF; two halves, slowing only the selected favourite.

    Baseline uses the existing 0..24 normalized Poisson support. The conditional
    scenario convolves normalized 0..24 half supports, hence 0..48 per team.
    This finite-support approximation is not a fitted tactical/live model.
    """
    h, a = _poisson(home), _poisson(away)
    if side not in ("HOME", "AWAY") or type(pace) not in (int,float) or pace not in PACE:
        raise ValueError("BAD_DHE_SCENARIO")
    if pace == 1.0:
        return {(i,j): p*q for i,p in enumerate(h) for j,q in enumerate(a)}
    h, a = _half(home/2), _half(away/2)
    normal, slow = {}, {}
    for i,p in enumerate(h):
        for j,q in enumerate(a):
            margin = i-j if side == "HOME" else j-i
            (slow if margin >= 2 else normal)[i,j] = p*q
    out = defaultdict(float)
    _add_period(normal,h,a,out)
    _add_period(slow,_half(home*pace/2) if side == "HOME" else h,
                _half(away*pace/2) if side == "AWAY" else a,out)
    if abs(math.fsum(out.values())-1) > 1e-9:
        raise ValueError("INVALID_SCORE_MASS")
    return dict(out)


def _total_units(line):
    if type(line) not in (str,int,float,Decimal):
        raise ValueError("BAD_TOTAL_LINE")
    try:
        q=Decimal(str(line))
    except InvalidOperation as exc:
        raise ValueError("BAD_TOTAL_LINE") from exc
    if not q.is_finite() or not 0 <= q <= 10:
        raise ValueError("BAD_TOTAL_LINE")
    # Compare exact quarter values instead of multiplying with Decimal context.
    for units in range(41):
        if q==Decimal(units/4):
            return units
    raise ValueError("BAD_TOTAL_LINE")


def _grades(distribution, line, reverse=False):
    out=dict.fromkeys(TYPES,0.0)
    for value,p in distribution.items():
        # Existing Asian settlement at decimal 2 maps exactly to five grades.
        net=asian_net(-value if reverse else value,line,2.0)
        out[NET_GRADE[net]]+=p
    return out


def project(home, away, side, handicap, total_line, *, pace=1.0):
    """All probabilities share one PMF; joint grades are not independent."""
    ah=quarter_units(handicap)
    if ah > -6:
        raise ValueError("REQUIRES_DEEP_LINE")
    tu=_total_units(total_line)
    score=score_distribution(home,away,side,pace)
    return _project_score(score,side,ah,tu,pace)


def _project_score(score,side,ah,tu,pace):
    """Internal common projection of a validated final-score distribution."""
    if (side not in ("HOME","AWAY") or type(ah) is not int or not -20<=ah<=-6
            or type(tu) is not int or not 0<=tu<=40
            or type(pace) not in (int,float) or pace not in PACE
            or not isinstance(score,dict) or not 1<=len(score)<=2601):
        raise ValueError("INVALID_SCORE_PROJECTION")
    for k,p in score.items():
        if (not isinstance(k,tuple) or len(k)!=2 or any(type(x) is not int or not 0<=x<=64 for x in k)
                or type(p) not in (int,float) or not math.isfinite(p) or not 0<=p<=1):
            raise ValueError("INVALID_SCORE_CELL")
    if abs(math.fsum(score.values())-1)>1e-9:
        raise ValueError("INVALID_SCORE_MASS")
    margins,totals=defaultdict(float),defaultdict(float)
    joint={g:dict.fromkeys(TYPES,0.0) for g in TYPES}
    wins={"HOME":0.0,"DRAW":0.0,"AWAY":0.0}
    both=0.0
    for (h,a),p in score.items():
        wins["HOME" if h>a else "AWAY" if h<a else "DRAW"]+=p
        m=h-a if side=="HOME" else a-h
        t=h+a
        margins[m]+=p
        totals[t]+=p
        g=NET_GRADE[asian_net(m,ah/4,2.0)]
        o=NET_GRADE[asian_net(t,-tu/4,2.0)]
        joint[g][o]+=p
        if h and a:
            both+=p
    handicap_grades=_grades(margins,ah/4)
    over_grades=_grades(totals,-tu/4)
    under_grades=_grades(totals,tu/4,reverse=True)
    inverse={"FULL_WIN":"FULL_LOSS","HALF_WIN":"HALF_LOSS","PUSH":"PUSH",
             "HALF_LOSS":"HALF_WIN","FULL_LOSS":"FULL_WIN"}
    for g in TYPES:
        if (abs(math.fsum(joint[g].values())-handicap_grades[g])>1e-9
                or abs(math.fsum(joint[k][g] for k in TYPES)-over_grades[g])>1e-9
                or abs(over_grades[g]-under_grades[inverse[g]])>1e-9):
            raise ValueError("INCONSISTENT_MARKET_PROJECTION")
    top=sorted(score.items(),key=lambda item:(-item[1],item[0]))[:10]
    return {"schema":SCHEMA,"status":"HOLD","production_recommendations":"DISABLED",
            "research_only":True,"qualifies_for_betting":False,
            "positive_expected_value_verified":False,"calibrated":False,
            "actual_market_lines_verified":False,"side":side,"pace":pace,
            "hypothetical_handicap":ah/4,"hypothetical_total":tu/4,
            "one_x_two":wins,"handicap":handicap_grades,"over":over_grades,
            "under":under_grades,"handicap_and_over_joint":joint,
            "both_teams_score_probability":both,
            "score_mass":math.fsum(score.values()),
            "top_scores":[{"home":h,"away":a,"probability":p} for (h,a),p in top],
            "other_score_probability":math.fsum(score.values())-math.fsum(p for _,p in top),
            "score_support_max_per_team":24 if pace==1.0 else 48,
            "calculation_version":"dhe-joint-score-projection-v1",
            "legacy_capture_model_unchanged":True,
            "model_assumption":"FIXED_HALFTIME_PACE_SCENARIO_NOT_FITTED"}

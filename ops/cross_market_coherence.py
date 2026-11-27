"""Offline research audit of joint final-score forecasts; never release evidence."""
from datetime import datetime, timezone
from math import isfinite

GRADES = ('full_loss', 'half_loss', 'push', 'half_win', 'full_win')


def _time(value):
    if not isinstance(value, str):
        raise ValueError('timestamp')
    t = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if t.utcoffset() is None:
        raise ValueError('timezone required')
    return t.astimezone(timezone.utc)


def _pair(value, limit):
    if not isinstance(value, (tuple, list)) or len(value) != 2 or any(type(x) is not int or not 0 <= x <= limit for x in value):
        raise ValueError('invalid pair')
    return tuple(value)


def _grade(margin4, line4):
    # Quarter-line expressed in exact quarter-goal integer units.
    lines = (line4-1, line4+1) if line4 % 2 else (line4, line4)
    s = sum((margin4+x > 0)-(margin4+x < 0) for x in lines)
    return GRADES[s+2]


def audit(snapshot):
    """Return coherent derived distributions or reject inconsistent input.

    A finite grid is a model assumption, not proof omitted tails are negligible.
    Red-card state is metadata only; this function does not estimate its effect.
    """
    current = _pair(snapshot['score'], 30)
    reds = _pair(snapshot['reds'], 11)
    observed = _time(snapshot['observed_at'])
    cutoff = _time(snapshot['cutoff'])
    generated = _time(snapshot['generated_at'])
    if not observed <= cutoff <= generated:
        raise ValueError('time order')
    ah, total = snapshot['home_line4'], snapshot['over_line4']
    if type(ah) is not int or abs(ah)>40 or type(total) is not int or not 0<=total<=120:
        raise ValueError('line units')
    cells = snapshot['cells']
    if not isinstance(cells, list) or not 1<=len(cells)<=961:
        raise ValueError('grid size')
    seen = set()
    result = {'1x2': dict.fromkeys(('home','draw','away'),0.0), 'ah':dict.fromkeys(GRADES,0.0), 'total':dict.fromkeys(GRADES,0.0)}
    mass=0.0
    for h,a,p in cells:
        key=_pair((h,a),30)
        if key in seen or h<current[0] or a<current[1]:
            raise ValueError('duplicate or impossible final score')
        seen.add(key)
        if type(p) not in (float,int) or not isfinite(p) or not 0<=p<=1:
            raise ValueError('probability')
        mass+=p
        result['1x2']['home' if h>a else 'away' if h<a else 'draw']+=p
        result['ah'][_grade(4*(h-a),ah)]+=p
        result['total'][_grade(4*(h+a),-total)]+=p
    if abs(mass-1)>1e-9:
        raise ValueError('probability mass')
    declared=snapshot.get('declared',{})
    if not isinstance(declared,dict) or set(declared)-set(result):
        raise ValueError('unknown market')
    for market, probs in declared.items():
        if not isinstance(probs,dict) or set(probs)!=set(result[market]):
            raise ValueError('market categories')
        for key,p in probs.items():
            if type(p) not in (int,float) or not isfinite(p) or not 0<=p<=1 or abs(p-result[market][key])>1e-8:
                raise ValueError('incoherent market')
    return {'state':'HOLD','production_enabled':False,'certified_cases':0,'derived':result,'declared_checked':sorted(declared)}


def compare_context(baseline, challenger):
    """Require exact shared information context before comparing distributions."""
    for field in ('fixture','score','reds','home_line4','over_line4','observed_at','cutoff'):
        b,c=baseline[field],challenger[field]
        if field in ('observed_at','cutoff'):
            b,c=_time(b),_time(c)
        elif field in ('score','reds'):
            b,c=tuple(b),tuple(c)
        if b!=c:
            raise ValueError('context mismatch: '+field)
    if not isinstance(baseline['fixture'],str) or not baseline['fixture'].strip():
        raise ValueError('fixture identity')
    return {'baseline':audit(baseline),'challenger':audit(challenger),'state':'HOLD','certified_cases':0}

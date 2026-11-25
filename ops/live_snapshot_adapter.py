"""Research-only gate for claimed two-source in-play state; no authentication."""
from datetime import datetime, timezone

KEYS = {'fixture_id','origin','observed','received','minute','home','away','red_home','red_away','phase'}
STATE = ('fixture_id','minute','home','away','red_home','red_away')
MODEL = ('fixture_id','minute_elapsed','score_home','score_away','red_home','red_away')


def valid(s):
    return (type(s) is dict and set(s) == KEYS
            and all(type(s[k]) is str and 0 < len(s[k]) <= 128 and s[k].strip() == s[k] and s[k].isprintable() for k in ('fixture_id','origin'))
            and all(type(s[k]) is int for k in ('observed','received','minute','home','away','red_home','red_away'))
            and 0 <= s['observed'] <= s['received']
            and 0 <= s['minute'] < 90 and all(0 <= s[k] <= 10 for k in ('home','away'))
            and all(0 <= s[k] <= 3 for k in ('red_home','red_away'))
            and ((s['phase'] == 'FIRST_HALF' and s['minute'] < 45) or (s['phase'] == 'SECOND_HALF' and 45 <= s['minute'])))


def hold(reason):
    return dict(status='HOLD', reason=reason, production_recommendations='DISABLED',
                source_authenticated=False, source_independence_verified=False,
                model_calibrated=False, model_scoring_eligible=False,
                positive_ev_verified=False, betting_recommendation_allowed=False)


def check(a,b,model,now,previous=None):
    if type(now) is not int or not valid(a) or not valid(b) or type(model) is not dict:
        return 'INVALID'
    if a['origin'] == b['origin'] or a['fixture_id'] != b['fixture_id']:
        return 'IDENTITY_OR_ORIGIN'
    if any(not 0 <= now-s['observed'] <= 90 or s['received'] > now for s in (a,b)):
        return 'STALE_OR_FUTURE'
    if abs(a['observed']-b['observed']) > 30:
        return 'UNSYNCED'
    if any(a[k] != b[k] for k in (*STATE,'phase')):
        return 'STATE_CONFLICT'
    if previous is not None and (not valid(previous) or previous['fixture_id'] != a['fixture_id'] or any(s[k] < previous[k] for s in (a,b) for k in ('observed','received','minute','home','away','red_home','red_away'))):
        return 'ROLLBACK_OR_CORRECTION_REVIEW'
    try:
        raw = model['decision_utc']
        dt = datetime.fromisoformat(raw.replace('Z','+00:00'))
        if dt.tzinfo is None or dt.astimezone(timezone.utc).timestamp() != now:
            return 'DECISION_MISMATCH'
        if any(type(model[m]) is not type(a[k]) or model[m] != a[k] for k,m in zip(STATE,MODEL)):
            return 'MODEL_STATE_MISMATCH'
    except (KeyError,TypeError,ValueError,AttributeError,OverflowError,OSError):
        return 'INVALID_MODEL'
    return 'CONSISTENT'


def research_predict(a,b,model,now,previous=None):
    reason = check(a,b,model,now,previous)
    if reason != 'CONSISTENT':
        return hold(reason)
    from inplay_state_challenger_vnext import audit_predict
    result = audit_predict(model)
    # Never promote a structural match to authenticated evidence.
    result.update({k:v for k,v in hold('unused').items() if k not in ('status','reason')})
    result['snapshot_consistency_only'] = True
    return result

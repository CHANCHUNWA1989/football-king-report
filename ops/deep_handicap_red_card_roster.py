"""Private roster reconstruction for already eligible historical dismissal windows.

Roster membership is a source claim, not independently verified on-pitch
presence. Temporary exits and ambiguous same-clock changes fail closed.
"""
from deep_handicap_historical_inputs import _decode,_id,MAX_BYTES
from deep_handicap_red_card_windows import inspect,classify_window,millis,DISMISSALS

STATES=("NOT_PAIRED_WINDOW","ROSTER_SUPPORTED_CLAIM","NON_ACTIVE_ROSTER_CARD",
        "ROSTER_AMBIGUOUS","STRUCTURE_REJECTED")

def roster_status(raw,match,window):
    try:
        if classify_window(window)!="PAIRED_CLOCK_WINDOWS_PRIVATE_ONLY":
            return "NOT_PAIRED_WINDOW"
        # Never trust a caller's claimed window without reconstructing it.
        if inspect(raw,match)!=window:return "STRUCTURE_REJECTED"
        teams=(_id(match["home_team"]["home_team_id"]),_id(match["away_team"]["away_team_id"]))
        active={k:set() for k in teams};used={k:set() for k in teams}
        temporary={k:set() for k in teams};xi=set();owner={};last=None
        pending_card=None
        for e in sorted(_decode(raw,MAX_BYTES),key=lambda e:e["index"]):
            kind=e["type"]["name"]
            card=(e.get("foul_committed") if kind=="Foul Committed" else
                  e.get("bad_behaviour") if kind=="Bad Behaviour" else None) or {}
            dismissal=(card.get("card") or {}).get("name") in DISMISSALS
            if kind not in ("Starting XI","Substitution","Player Off","Player On") and not dismissal:
                continue
            t=(e["period"],millis(e["timestamp"]))
            team=_id(e["team"]["id"])
            if team not in active:return "ROSTER_AMBIGUOUS"
            if last is not None and t<last:return "ROSTER_AMBIGUOUS"
            # Starting XIs at identical zero clock are expected. Same-clock
            # substitution/card ordering cannot be independently resolved.
            if pending_card is not None:
                return "ROSTER_AMBIGUOUS" if t<=pending_card[0] else pending_card[1]
            if dismissal and t==last:return "ROSTER_AMBIGUOUS"
            last=t
            if kind=="Starting XI":
                if t!=(1,0) or team in xi:return "ROSTER_AMBIGUOUS"
                players=[_id(x["player"]["id"]) for x in e["tactics"]["lineup"]]
                if len(players)!=11 or len(set(players))!=11 or any(x in owner for x in players):
                    return "ROSTER_AMBIGUOUS"
                active[team].update(players);used[team].update(players)
                owner.update({x:team for x in players});xi.add(team)
                continue
            if xi!=set(teams):return "ROSTER_AMBIGUOUS"
            player=_id(e["player"]["id"])
            if player in owner and owner[player]!=team:return "ROSTER_AMBIGUOUS"
            if dismissal:
                state=("ROSTER_SUPPORTED_CLAIM" if player in active[team] and player not in temporary[team]
                       else "NON_ACTIVE_ROSTER_CARD")
                pending_card=(t,state)
            elif kind=="Substitution":
                new=_id(e["substitution"]["replacement"]["id"])
                if player not in active[team] or new in owner:return "ROSTER_AMBIGUOUS"
                active[team].remove(player);temporary[team].discard(player)
                active[team].add(new);used[team].add(new);owner[new]=team
            elif kind=="Player Off":
                if player not in active[team] or player in temporary[team]:return "ROSTER_AMBIGUOUS"
                temporary[team].add(player)
            elif kind=="Player On":
                if player not in temporary[team]:return "ROSTER_AMBIGUOUS"
                temporary[team].remove(player)
        return pending_card[1] if pending_card else "ROSTER_AMBIGUOUS"
    except (ValueError,TypeError,KeyError,OverflowError,AttributeError,RecursionError):
        return "STRUCTURE_REJECTED"

def reconcile(states,expected):
    from collections import Counter
    if type(expected) is not int or not 0<=expected<=48 or len(states)!=expected:
        raise ValueError("ROSTER_DENOMINATOR")
    if any(s not in STATES for s in states):raise ValueError("ROSTER_STATE")
    c=Counter(states)
    return {k:c[k] for k in STATES}

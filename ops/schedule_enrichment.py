"""Cross-check timezone-aware upcoming fixture UTC between two free observations.

Enrich existing schedules or restore a missing scheduled fixture *only* from
two independent, time-agreeing source records and previously known teams.
No market odds, market probabilities, scores or future results enter the model.
A single provider, guessed timezone, ambiguous aliases or contradictory times
cannot silently become model input. RESEARCH ONLY, not verified EV.
"""
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from team_identity import team_id

LEAGUES = ("epl", "championship", "bundesliga", "laliga", "seriea", "ligue1")
MAX_SOURCE_AGE = timedelta(hours=16)
MAX_KICKOFF_GAP = timedelta(minutes=45)


def utc(value):
    if not isinstance(value, str) or not value:
        raise ValueError("MISSING_UTC")
    stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        raise ValueError("UNZONED_TIME")
    return stamp.astimezone(timezone.utc)


def age_ok(value, now):
    try:
        age = now - utc(value)
        return timedelta(minutes=-5) <= age <= MAX_SOURCE_AGE
    except (ValueError, TypeError, OverflowError):
        return False


def enrich_free_publishers(rows, league, audit, now):
    """Repair existing date-only fixtures using two exact UTC publisher votes.

    No odds snapshot is needed. Never add a fixture, alter finished history,
    or treat a single publisher or an unzoned gateway time as corroboration.
    """
    diag={"free_publisher_time_agreements":0,"updated_existing_schedules":0,
          "added_crosschecked_schedules":0,"source_time_agreements":0,
          "source":"TWO_FREE_PUBLISHER_EXACT_UTC_ONLY"}
    try:
        from source_publish_guard import verify
        stamp=verify(audit,now=now)
        if (audit.get("status")!="RESEARCH_ONLY" or not timedelta(0)<=now-stamp<=MAX_SOURCE_AGE
                or league not in LEAGUES or not isinstance(rows,list)):
            return rows,diag
    except (ValueError,KeyError,TypeError,AttributeError,OverflowError):
        return rows,diag
    from zoneinfo import ZoneInfo
    hk=ZoneInfo("Asia/Hong_Kong")
    active={p["provider"] for p in audit["providers"] if p["configured"] is True
            and p["status"] in ("PARTIAL","PARTIAL_COVERAGE") and p["sampled_fixture_count"]>0}
    votes=defaultdict(lambda:defaultdict(list))
    for row in audit["sampled_fixtures"]:
        if (row["league"]!=league or row["provider"] not in active or
                row["status"]!="SCHEDULED" or row.get("score_ft") is not None):
            continue
        h,a=team_id(league,row["home"]),team_id(league,row["away"])
        if not h or not a or h==a:
            continue
        ko=utc(row["kickoff_utc"])
        if now+timedelta(minutes=60)<=ko<=now+timedelta(days=7):
            votes[(h,a)][row["provider"]].append(ko)
    existing=defaultdict(list)
    for i,r in enumerate(rows):
        if isinstance(r,dict) and r.get("status")=="SCHEDULED" and r.get("score_ft") is None:
            h,a=team_id(league,r.get("home")),team_id(league,r.get("away"))
            if h and a and h!=a:
                existing[(h,a)].append((i,r))
    upgraded=list(rows)
    for key,publishers in votes.items():
        if len(publishers)<2 or any(len(v)!=1 for v in publishers.values()):
            continue
        times={stamp for observations in publishers.values() for stamp in observations}
        base=existing.get(key,[])
        if len(times)!=1 or len(base)!=1:
            continue
        ko=next(iter(times))
        i,row=base[0]
        if row.get("kickoff_utc"):
            # The gateway already has precise time; never overwrite it.
            continue
        if row.get("date") not in (ko.date().isoformat(),ko.astimezone(hk).date().isoformat()):
            continue
        # Reject any other scheduled opponent involving either club on the
        # same UTC/HK date, rather than silently repair an ambiguous schedule.
        if any(other!=key and set(other).intersection(key) and any(
                r.get("date") in (ko.date().isoformat(),ko.astimezone(hk).date().isoformat())
                for _,r in entries) for other,entries in existing.items()):
            continue
        upgraded[i]={**row,"date":ko.astimezone(hk).date().isoformat(),
                     "kickoff_utc":ko.isoformat(),"schedule_utc_source":"two_free_publishers_exact_utc",
                     "schedule_independent_time_agreement_only":True}
        diag["free_publisher_time_agreements"]+=1
        diag["updated_existing_schedules"]+=1
    return upgraded,diag


def enrich(rows, league, audit, market, now):
    """Return (new_rows, diagnostics). Never mutate original fixture records."""
    diag = {"source": "SECONDARY_SCHEDULE_PLUS_MARKET_EVENT_TIME_ONLY",
            "strict_source_ready": False, "secondary_scheduled": 0,
            "source_time_agreements": 0, "free_publisher_time_agreements": 0,
            "updated_existing_schedules": 0,
            "added_crosschecked_schedules": 0,
            "gateway_scheduled_fixture_keys": 0,
            "unmatched_gateway_fixture_keys": 0,
            "unmatched_market_fixture_keys": 0,
            "calendar_date_conflicts": 0,
            "market_probabilities_used_as_model_input": False,
            "price_inputs_used": False, "single_source_dates_accepted": False,
            "training_results_augmented": False}
    if not isinstance(rows, list) or league not in LEAGUES:
        return rows, diag
    if (not isinstance(audit, dict) or not isinstance(market, dict)
            or audit.get("schema") != "football-king-extra-source-audit-v1"
            or audit.get("production_recommendations") != "DISABLED"
            or audit.get("status") != "RESEARCH_ONLY"
            or market.get("status") != "RESEARCH_ONLY"
            or market.get("production_recommendations") != "DISABLED"
            or not age_ok(audit.get("collected_utc"), now)
            or not age_ok(market.get("as_of_utc"), now)
            or not isinstance(audit.get("sampled_fixtures"), list)
            or not isinstance(audit.get("providers"), list)
            or not isinstance(market.get("events"), list)):
        repaired, free_diag=enrich_free_publishers(rows,league,audit,now)
        if free_diag["free_publisher_time_agreements"]:
            diag.update(free_diag)
        return repaired, diag
    # Only use fixtures from a provider that really supplied public samples.
    active = {p["provider"] for p in audit["providers"] if isinstance(p, dict)
              and isinstance(p.get("provider"), str)
              and p.get("status") in ("PARTIAL", "PARTIAL_COVERAGE")
              and type(p.get("sampled_fixture_count")) is int
              and p["sampled_fixture_count"] > 0}
    if not active:
        return rows, diag
    diag["strict_source_ready"] = True

    # Only original gateway finished results provide model training data.
    # A source-confirmed external fixture may repair a missing schedule, but
    # must never create or alter a training result or guess a new club identity.
    from collections import Counter
    historical_names = defaultdict(Counter)
    historical_appearances = Counter()
    for row in rows:
        if (not isinstance(row, dict) or row.get("status") != "FINISHED"
                or not isinstance(row.get("score_ft"), list)
                or len(row["score_ft"]) != 2):
            continue
        try:
            from datetime import date
            from zoneinfo import ZoneInfo
            if date.fromisoformat(row["date"]) >= now.astimezone(
                    ZoneInfo("Asia/Hong_Kong")).date():
                continue
            if not all(type(n) is int and 0 <= n <= 20 for n in row["score_ft"]):
                continue
        except (KeyError, ValueError, TypeError, OverflowError):
            continue
        for role in ("home", "away"):
            name = row.get(role)
            identity = team_id(league, name)
            if identity and isinstance(name, str) and name:
                historical_names[identity][name] += 1
                historical_appearances[identity] += 1
    fixtures = defaultdict(list)
    for i, row in enumerate(rows):
        if not isinstance(row, dict) or row.get("status") != "SCHEDULED" or row.get("score_ft") is not None:
            continue
        h, a = team_id(league, row.get("home")), team_id(league, row.get("away"))
        if h and a and h != a:
            fixtures[(h, a)].append((i, row))

    diag["gateway_scheduled_fixture_keys"] = len(fixtures)
    market_index = defaultdict(list)
    snapshot_at = utc(market["as_of_utc"])
    for price in market["events"][:400]:
        if not isinstance(price, dict) or price.get("league") != league:
            continue
        h, a = team_id(league, price.get("home")), team_id(league, price.get("away"))
        if not h or not a or h == a:
            continue
        try:
            ko = utc(price["kickoff_utc"])
            updated_at = utc(price["market_last_update_utc"])
            if not updated_at <= snapshot_at <= now + timedelta(minutes=5):
                continue
        except (KeyError, ValueError, TypeError, OverflowError):
            continue
        market_index[(h, a)].append(ko)

    observed = defaultdict(list)
    for row in audit["sampled_fixtures"][:150]:
        if (not isinstance(row, dict) or row.get("league") != league
                or row.get("provider") not in active
                or row.get("status") != "SCHEDULED" or row.get("score_ft") is not None):
            continue
        h, a = team_id(league, row.get("home")), team_id(league, row.get("away"))
        if not h or not a or h == a or not row.get("provider_event_id"):
            continue
        try:
            ko = utc(row["kickoff_utc"])
        except (ValueError, TypeError, OverflowError, KeyError):
            continue
        if not now + timedelta(minutes=60) <= ko <= now + timedelta(days=7):
            continue
        diag["secondary_scheduled"] += 1
        observed[(h, a)].append((ko, row["provider"]))

    upgraded = list(rows)
    for key, provider_times in observed.items():
        base = fixtures.get(key, [])
        candidate_prices = market_index.get(key, [])
        # An unambiguous market fixture with same UTC kickoff is an
        # independent schedule check, not a bookmaker price input.
        if len(base) > 1:
            diag["unmatched_gateway_fixture_keys"] += 1
            continue
        if len(candidate_prices) != 1:
            diag["unmatched_market_fixture_keys"] += 1
            continue
        # Distinct agreeing publishers are useful, not ambiguous duplicates.
        # Keep the existing maximum total time span; never average timestamps.
        if len({provider for _, provider in provider_times}) != len(provider_times):
            continue
        clocks = [stamp for stamp, _ in provider_times] + candidate_prices
        if max(clocks) - min(clocks) > MAX_KICKOFF_GAP:
            continue
        ko, provider = min(provider_times, key=lambda item: (
            item[1] != "thesportsdb", item[1]))
        diag["source_time_agreements"] += 1
        if not base:
            # Both providers observed the same future fixture, but the
            # original data withheld unzoned calendar fixtures. Use names
            # already seen at least three times in historical training only.
            h, a = key
            if historical_appearances[h] < 3 or historical_appearances[a] < 3:
                diag["unmatched_gateway_fixture_keys"] += 1
                continue
            home = historical_names[h].most_common(1)[0][0]
            away = historical_names[a].most_common(1)[0][0]
            if (home == away or historical_names[h][home] < 3
                    or historical_names[a][away] < 3):
                diag["unmatched_gateway_fixture_keys"] += 1
                continue
            # Never create a second fixture for a team if the gateway already
            # has a different scheduled opponent within 36 hours.
            conflict = False
            for candidates in fixtures.values():
                for _, current in candidates:
                    if (team_id(league, current.get("home")) not in key
                            and team_id(league, current.get("away")) not in key):
                        continue
                    try:
                        existing_time = utc(current["kickoff_utc"])
                        if abs(existing_time - ko) <= timedelta(hours=36):
                            conflict = True
                            break
                    except (KeyError, TypeError, ValueError, OverflowError):
                        continue
                if conflict:
                    break
            if conflict:
                continue
            upgraded.append({
                "date": ko.astimezone(__import__("zoneinfo").ZoneInfo(
                    "Asia/Hong_Kong")).date().isoformat(),
                "league": league, "home": home, "away": away,
                "status": "SCHEDULED", "score_ft": None,
                "event_id": "two-source-utc-" + league + "-" +
                            provider + "-" + str(int(ko.timestamp())) +
                            "-" + h + "-" + a,
                "kickoff_utc": ko.isoformat(),
                "schedule_utc_source": provider,
                "schedule_independent_time_agreement_only": True,
                "added_from_two_time_agreeing_fixtures": True,
                "production_recommendations": "DISABLED",
            })
            diag["added_crosschecked_schedules"] += 1
            continue
        i, original = base[0]
        try:
            # Never override an already precise, contradictory gateway time.
            old_ko = original.get("kickoff_utc")
            if old_ko and abs(utc(old_ko) - ko) > MAX_KICKOFF_GAP:
                continue
            # Original openfootball calendar dates are local/unspecified,
            # not guaranteed Hong Kong dates. The UTC and HK calendar days
            # are the only two acceptable literal dates; never infer an
            # exact kickoff hour from a date-only row.
            from zoneinfo import ZoneInfo
            original_day = str(original["date"])
            allowed_days = {
                ko.date().isoformat(),
                ko.astimezone(ZoneInfo("Asia/Hong_Kong")).date().isoformat(),
            }
            if original_day not in allowed_days:
                diag["calendar_date_conflicts"] += 1
                continue
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
        new = dict(original)
        # The gateway's date-only value may describe the UTC calendar day.
        # Once two schedule sources agree on a precise UTC kickoff, normalize
        # the derived research fixture to the Hong Kong day expected by the
        # forecast gate. Never rewrite the gateway's original row/history.
        new["date"] = ko.astimezone(ZoneInfo("Asia/Hong_Kong")).date().isoformat()
        new["kickoff_utc"] = ko.isoformat()
        new["schedule_utc_source"] = provider
        new["schedule_independent_time_agreement_only"] = True
        upgraded[i] = new
        diag["updated_existing_schedules"] += 1
    return upgraded, diag

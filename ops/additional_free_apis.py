"""Four additional free research services, five read-only API endpoints.

Open-Meteo forecast + historical reanalysis, Meteostat historical daily
(optional owner-held RapidAPI key), Wikidata stadium coordinate catalog, and
ScoreBat free highlights (optional owner-held token).
All outputs are safe COUNTS/availability, not bookmaker quotes, prediction
features, final-score truth, raw commercial feed copies or betting advice.
No credential is logged, written, or included in a public query result.
"""
import argparse
import json
import math
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, build_opener, HTTPRedirectHandler

from met_weather import CITY_POINTS

SCHEMA = "football-king-four-additional-free-apis-v1"
USER_AGENT = "FootballKingResearch/1.0 (+https://github.com/CHANCHUNWA1989/football-king-report)"
MAX_BYTES = 900_000
MAX_CALLS = 5
MODEL_DISABLED = "DISABLED"
OPEN_METEO = "https://api.open-meteo.com/v1/forecast"
ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"
METEOSTAT = "https://meteostat.p.rapidapi.com/point/daily"
WIKIDATA = "https://query.wikidata.org/sparql"
SCOREBAT = "https://www.scorebat.com/video-api/v3/free-feed/"
SITES = (OPEN_METEO, ARCHIVE, METEOSTAT, WIKIDATA, SCOREBAT)
LICENSES = {
    "open_meteo_forecast": "https://open-meteo.com/en/terms",
    "open_meteo_archive": "https://open-meteo.com/en/terms",
    "meteostat_daily": "https://dev.meteostat.net/license",
    "wikidata_stadiums": "https://www.wikidata.org/wiki/Wikidata:Data_access",
    "scorebat_free": "https://www.scorebat.com/video-api/docs/",
}


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("UNTRUSTED_PROVIDER_REDIRECT")


def utc(value):
    if not isinstance(value, str):
        raise ValueError("NOT_AN_ISO_TIME")
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("NAIVE_PROVIDER_TIME")
    return dt.astimezone(timezone.utc)


def finite(value, lower, upper):
    return (type(value) in (int, float) and math.isfinite(value)
            and lower <= value <= upper)


def read_json(base, params=None, headers=None, requester=None):
    """One bounded HTTPS request to a hardcoded endpoint, never follow redirects."""
    if base not in SITES:
        raise ValueError("UNAPPROVED_SOURCE")
    url = base + ("?" + urlencode(params) if params else "")
    req = Request(url, headers={"User-Agent": USER_AGENT,
                                "Accept": "application/json",
                                **(headers or {})})
    client = requester or build_opener(NoRedirect()).open
    try:
        with client(req, timeout=12) as response:
            payload = response.read(MAX_BYTES + 1)
        if len(payload) > MAX_BYTES:
            return None, "TOO_LARGE"
        return json.loads(payload.decode("utf-8")), "OK"
    except HTTPError as exc:
        if exc.code == 429:
            return None, "RATE_LIMITED"
        if exc.code in (401, 403):
            return None, "NOT_AUTHORIZED"
        return None, "PROVIDER_HTTP_ERROR"
    except (OSError, URLError, TimeoutError):
        return None, "NETWORK_UNAVAILABLE"
    except (ValueError, TypeError, UnicodeError, json.JSONDecodeError):
        return None, "INVALID_PROVIDER_RESPONSE"


def provider(name, configured=True):
    return {
        "provider": name,
        "status": "HOLD" if configured else "NOT_CONFIGURED",
        "reason": "NO_VERIFIED_DATA" if configured else "PRIVATE_TOKEN_REQUIRED",
        "configured": bool(configured),
        "calls_attempted": 0,
        "matched_or_valid_rows": 0,
        "attribution_required": True,
        "attribution_url": LICENSES[name],
        "source_is_not_independent_market": True,
        "model_input_enabled": False,
        "production_recommendations": MODEL_DISABLED,
    }


def forecast_summary(doc, now):
    """Batch of six fixed city centres, not stadium coordinates."""
    if not isinstance(doc, list) or len(doc) != len(CITY_POINTS):
        raise ValueError("OPEN_METEO_CITY_BATCH_MISMATCH")
    if len({x.get("location_id") for x in doc if isinstance(x, dict)}) != len(doc):
        # Arrays with no location_id are still valid from some deployments;
        # do not require an optional ID. Validate each ordered coordinate instead.
        pass
    usable = 0
    samples = 0
    for row, (_, _, lat, lon, _) in zip(doc, CITY_POINTS):
        if not isinstance(row, dict):
            continue
        if not (finite(row.get("latitude"), -90, 90) and
                finite(row.get("longitude"), -180, 180) and
                abs(row["latitude"] - lat) < .4 and
                abs(row["longitude"] - lon) < .4 and
                row.get("utc_offset_seconds") == 0):
            continue
        hourly = row.get("hourly")
        if not isinstance(hourly, dict):
            continue
        times = hourly.get("time")
        temp = hourly.get("temperature_2m")
        wind = hourly.get("wind_speed_10m")
        rain = hourly.get("precipitation")
        if not all(isinstance(v, list) for v in (times, temp, wind, rain)):
            continue
        if not 1 <= len(times) <= 100 or not len(times) == len(temp) == len(wind) == len(rain):
            continue
        accepted = 0
        for t, a, b, c in zip(times, temp, wind, rain):
            try:
                # The API returns timezone-naive ISO strings when tz=GMT.
                # Interpret only with explicit zero-offset metadata.
                if isinstance(t, str) and len(t) == 16 and t[10] == "T":
                    dt = utc(t + "+00:00")
                else:
                    dt = utc(t)
                if (now - timedelta(minutes=75) <= dt <= now + timedelta(days=3)
                        and finite(a, -70, 60) and finite(b, 0, 90)
                        and (c is None or finite(c, 0, 500))):
                    accepted += 1
            except (ValueError, TypeError, OverflowError):
                continue
        if accepted:
            usable += 1
            samples += accepted
    return usable, samples


def historical_summary(doc, start, end):
    if (not isinstance(doc, dict) or doc.get("utc_offset_seconds") != 0
            or not isinstance(doc.get("hourly"), dict)):
        raise ValueError("HISTORY_NOT_UTC")
    rows = doc["hourly"]
    dates = rows.get("time")
    variables = [rows.get(k) for k in ("temperature_2m", "wind_speed_10m", "precipitation")]
    if (not isinstance(dates, list) or not 1 <= len(dates) <= 96
            or not all(isinstance(v, list) and len(v) == len(dates) for v in variables)):
        raise ValueError("HISTORY_BAD_LENGTH")
    valid = 0
    for ts, temp, wind, rain in zip(dates, *variables):
        try:
            dt = utc(ts + "+00:00") if isinstance(ts, str) and len(ts) == 16 else utc(ts)
            if (start.date() <= dt.date() <= end.date()
                    and finite(temp, -70, 60) and finite(wind, 0, 90)
                    and (rain is None or finite(rain, 0, 500))):
                valid += 1
        except (ValueError, TypeError, OverflowError):
            continue
    return valid


def meteostat_summary(doc, start, end):
    if not isinstance(doc, dict) or not isinstance(doc.get("data"), list):
        raise ValueError("METEOSTAT_UNKNOWN_SHAPE")
    rows = doc["data"]
    if len(rows) > 16:
        raise ValueError("METEOSTAT_TOO_MANY_ROWS")
    count = 0
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            day = datetime.strptime(row["date"], "%Y-%m-%d").date()
            if (start.date() <= day <= end.date()
                    and any(finite(row.get(k), lo, hi) for k, lo, hi in (
                        ("tavg", -70, 60), ("tmin", -90, 60),
                        ("tmax", -70, 65), ("prcp", 0, 800),
                        ("wspd", 0, 300)))):
                count += 1
        except (KeyError, TypeError, ValueError):
            continue
    return count


def wikidata_summary(doc):
    if not isinstance(doc, dict) or not isinstance(doc.get("results"), dict):
        raise ValueError("WIKIDATA_SCHEMA_UNKNOWN")
    rows = doc["results"].get("bindings")
    if not isinstance(rows, list) or len(rows) > 20:
        raise ValueError("WIKIDATA_LIMIT_EXCEEDED")
    valid = set()
    for item in rows:
        if not isinstance(item, dict):
            continue
        try:
            entity = item["venue"]["value"]
            coordinate = item["coord"]["value"]
            if (isinstance(entity, str) and entity.startswith("http://www.wikidata.org/entity/Q")
                    and isinstance(coordinate, str) and coordinate.startswith("Point(")
                    and coordinate.endswith(")") and len(coordinate) <= 80):
                bits = coordinate[6:-1].split()
                if (len(bits) == 2 and finite(float(bits[0]), -180, 180)
                        and finite(float(bits[1]), -90, 90)):
                    valid.add(entity)
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
    return len(valid)


def scorebat_summary(doc):
    if not isinstance(doc, dict) or not isinstance(doc.get("response"), list):
        raise ValueError("SCOREBAT_BAD_FEED")
    entries = doc["response"]
    if len(entries) > 250:
        raise ValueError("SCOREBAT_OVERSIZED_FEED")
    valid = 0
    for row in entries:
        if not isinstance(row, dict):
            continue
        if (isinstance(row.get("date"), str)
                and isinstance(row.get("homeTeam"), dict)
                and isinstance(row.get("awayTeam"), dict)
                and isinstance(row.get("videos"), list)):
            try:
                utc(row["date"])
                if row["homeTeam"].get("name") and row["awayTeam"].get("name"):
                    valid += 1
            except (ValueError, TypeError, OverflowError):
                continue
    return valid


# SPARQL query deliberately restricted to six exact stadium-name labels.
# This is a CATALOGUE suggestion, never grounds a home stadium automatically.
STADIUM_QUERY = """SELECT ?venue ?coord WHERE {
  VALUES ?name {"Allianz Arena"@en "Signal Iduna Park"@en
                "Deutsche Bank Park"@en "Red Bull Arena"@en
                "Europa-Park Stadion"@en "RheinEnergieStadion"@en}
  ?venue <http://www.w3.org/2000/01/rdf-schema#label> ?name ;
         <http://www.wikidata.org/prop/direct/P625> ?coord .
} LIMIT 12"""


def collect(*, now=None, keys=None, requester=None, background=False):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("NAIVE_NOW")
    keys = keys if keys is not None else os.environ
    items = [provider(n, configured=n not in ("meteostat_daily", "scorebat_free")
                      or bool(keys.get("METEOSTAT_RAPIDAPI_KEY" if n == "meteostat_daily"
                                       else "SCOREBAT_FREE_TOKEN")))
             for n in LICENSES]
    state = {r["provider"]: r for r in items}
    doc = {"schema": SCHEMA, "captured_utc": now.isoformat(),
           "mode": "BACKGROUND_WEEKLY" if background else "DAILY_FORECAST",
           "source_scope": "OPTIONAL_RESEARCH_NO_MODEL_CHANGES",
           "providers": items, "calls_attempted": 0, "max_calls": MAX_CALLS,
           "raw_payload_published": False, "bookmaker_quotes_saved": False,
           "private_credentials_published": False,
           "current_2026_results_verified": False,
           "independent_provenance_confirmed": False,
           "model_training_changed": False,
           "betting_enabled": False,
           "production_recommendations": MODEL_DISABLED}

    def query(name, url, parameters=None, headers=None):
        if doc["calls_attempted"] >= MAX_CALLS:
            raise ValueError("EXTRA_PROVIDER_BUDGET_GUARD")
        entry = state[name]
        entry["calls_attempted"] += 1
        doc["calls_attempted"] += 1
        result, status = read_json(url, parameters, headers, requester=requester)
        if status != "OK":
            entry["reason"] = status
        return result, status

    coords = [(lat, lon) for _, _, lat, lon, _ in CITY_POINTS]
    params = {"latitude": ",".join(str(c[0]) for c in coords),
              "longitude": ",".join(str(c[1]) for c in coords),
              "hourly": "temperature_2m,wind_speed_10m,precipitation",
              "wind_speed_unit": "ms", "timezone": "GMT", "forecast_days": 3}
    raw, status = query("open_meteo_forecast", OPEN_METEO, params)
    if status == "OK":
        try:
            cities, points = forecast_summary(raw, now)
            v = state["open_meteo_forecast"]
            v["matched_or_valid_rows"] = cities
            v["hourly_observations"] = points
            v["location_scope"] = "SIX_GERMAN_CITY_CENTRES_NOT_VENUES"
            v["weather_inputs_used_in_model"] = False
            v["status"] = "RESEARCH_ONLY" if cities == len(CITY_POINTS) else "PARTIAL" if cities else "HOLD"
            v["reason"] = "SIX_CITY_CONTEXT_ONLY_NOT_INDEPENDENT_MODEL" if cities else "NO_VALID_FORECAST_HOURS"
        except (ValueError, KeyError, TypeError, OverflowError):
            state["open_meteo_forecast"]["reason"] = "FORECAST_SCHEMA_UNVERIFIED"

    if background:
        from_date = now - timedelta(days=12)
        until_date = now - timedelta(days=10)
        archive_params = {
            "latitude": str(CITY_POINTS[0][2]), "longitude": str(CITY_POINTS[0][3]),
            "start_date": from_date.date().isoformat(), "end_date": until_date.date().isoformat(),
            "hourly": "temperature_2m,wind_speed_10m,precipitation",
            "wind_speed_unit": "ms", "timezone": "GMT"}
        raw, status = query("open_meteo_archive", ARCHIVE, archive_params)
        if status == "OK":
            try:
                n = historical_summary(raw, from_date, until_date)
                v = state["open_meteo_archive"]
                v["matched_or_valid_rows"] = n
                v["status"] = "PARTIAL" if n else "HOLD"
                v["reason"] = "REANALYSIS_AFTER_EVENT_NOT_PREMATCH" if n else "NO_HISTORICAL_HOURS"
            except (ValueError, TypeError, OverflowError):
                state["open_meteo_archive"]["reason"] = "ARCHIVE_SCHEMA_UNVERIFIED"

        raw, status = query("wikidata_stadiums", WIKIDATA,
                            {"query": STADIUM_QUERY, "format": "json"})
        if status == "OK":
            try:
                n = wikidata_summary(raw)
                v = state["wikidata_stadiums"]
                v["matched_or_valid_rows"] = n
                v["status"] = "PARTIAL" if n else "HOLD"
                v["reason"] = "POTENTIAL_VENUE_CATALOG_NOT_TEAM_VERIFIED" if n else "NO_STADIUM_COORDINATES"
            except (ValueError, TypeError, OverflowError):
                state["wikidata_stadiums"]["reason"] = "WIKIDATA_SCHEMA_UNVERIFIED"

        if state["meteostat_daily"]["configured"]:
            raw, status = query("meteostat_daily", METEOSTAT, {
                "lat": str(CITY_POINTS[0][2]), "lon": str(CITY_POINTS[0][3]),
                "start": from_date.date().isoformat(),
                "end": until_date.date().isoformat(),
                "model": "false", "units": "metric"}, {
                    "X-RapidAPI-Key": keys["METEOSTAT_RAPIDAPI_KEY"],
                    "X-RapidAPI-Host": "meteostat.p.rapidapi.com"})
            if status == "OK":
                try:
                    n = meteostat_summary(raw, from_date, until_date)
                    v = state["meteostat_daily"]
                    v["matched_or_valid_rows"] = n
                    v["status"] = "PARTIAL" if n else "HOLD"
                    v["reason"] = "HISTORICAL_DELAYED_WEATHER_ONLY" if n else "NO_HISTORICAL_DAYS"
                except (ValueError, TypeError, OverflowError):
                    state["meteostat_daily"]["reason"] = "METEOSTAT_SCHEMA_UNVERIFIED"

        if state["scorebat_free"]["configured"]:
            raw, status = query("scorebat_free", SCOREBAT,
                                {"token": keys["SCOREBAT_FREE_TOKEN"]})
            if status == "OK":
                try:
                    n = scorebat_summary(raw)
                    v = state["scorebat_free"]
                    v["matched_or_valid_rows"] = n
                    v["status"] = "PARTIAL" if n else "HOLD"
                    v["reason"] = "HIGHLIGHTS_NOT_MATCH_ORACLE" if n else "EMPTY_FREE_VIDEO_FEED"
                except (ValueError, TypeError, OverflowError):
                    state["scorebat_free"]["reason"] = "SCOREBAT_SCHEMA_UNVERIFIED"
    else:
        for p in items:
            if p["provider"] != "open_meteo_forecast" and p["configured"]:
                p["status"] = "NOT_RUN"
                p["reason"] = "BACKGROUND_WEEKLY_ONLY"

    # Never mark the aggregate as authoritative; independent data rights and
    # predictive incremental value are not established.
    doc["valid_provider_count"] = sum(p["status"] in ("RESEARCH_ONLY", "PARTIAL") for p in items)
    doc["status"] = "RESEARCH_ONLY" if doc["valid_provider_count"] else "HOLD"
    return doc


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--background", action="store_true")
    parser.add_argument("--output", default="extra-api-research.json")
    args = parser.parse_args(argv)
    result = collect(background=args.background)
    dest = Path(args.output)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "mode": result["mode"],
                      "calls_attempted": result["calls_attempted"],
                      "providers": {p["provider"]: p["status"] for p in result["providers"]},
                      "production_recommendations": MODEL_DISABLED}, ensure_ascii=False))


if __name__ == "__main__":
    main()

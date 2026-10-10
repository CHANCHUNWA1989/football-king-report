"""Optional Asia football weather and K League partner API research sidecar.

Open-Meteo: public non-commercial/CC-BY weather at approximate city centres.
K League: partner-authenticated league catalogue ONLY, never a fixture/odds claim.
The two sources cannot change the model, main market or production gate.
"""
import argparse
import json
import math
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

SCHEMA = "football-king-asia-optional-connectors-v1"
OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
KLEAGUE_URL = "https://api.kleague.com/api/leagueInfo.do"
ATTRIBUTION = "Weather data by Open-Meteo.com (CC BY 4.0)"
LICENSE = "https://open-meteo.com/en/terms"
# Well-known approximate city-centre coordinates, NOT verified stadium sites.
CITIES = (
    ("seoul", "首爾市中心", 37.566, 126.978),
    ("busan", "釜山市中心", 35.180, 129.075),
    ("suwon", "水原市中心", 37.263, 127.029),
    ("osaka", "大阪市中心", 34.694, 135.502),
    ("yokohama", "橫濱市中心", 35.444, 139.639),
    ("nagoya", "名古屋市中心", 35.181, 136.907),
)
MAX_BYTES = 450_000
MAX_HOURS = 80
MAX_FUTURE_DAYS = 3
MAX_LEAGUES = 100

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("REDIRECT_REFUSED")

def utc(value):
    if not isinstance(value, str) or not value:
        raise ValueError("INVALID_TIME")
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("TIMEZONE_REQUIRED")
    return dt.astimezone(timezone.utc)

def fetch_json(url, headers=None, *, requester=None):
    if not (url.startswith(OPEN_METEO_URL + "?") or
            url.startswith(KLEAGUE_URL + "?")):
        raise ValueError("UNEXPECTED_ENDPOINT")
    req = Request(url, headers={"Accept": "application/json",
                   "User-Agent": "FootballKingAsiaResearch/1.0",
                   **(headers or {})})
    call = requester or build_opener(NoRedirect()).open
    with call(req, timeout=12) as resp:
        raw = resp.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("RESPONSE_TOO_LARGE")
    data = json.loads(raw.decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("EXPECTED_OBJECT")
    return data

def number(value, low, high):
    if type(value) not in (int, float) or not math.isfinite(value):
        return None
    return round(float(value), 2) if low <= value <= high else None

def weather_hourly(data, now):
    if data.get("timezone") not in ("GMT", "UTC"):
        raise ValueError("NON_UTC_WEATHER")
    hours = data.get("hourly")
    if not isinstance(hours, dict):
        raise ValueError("MISSING_HOURLY")
    names = ("time", "temperature_2m", "precipitation", "wind_speed_10m")
    values = [hours.get(name) for name in names]
    if not all(isinstance(x, list) and 1 <= len(x) <= MAX_HOURS for x in values):
        raise ValueError("MALFORMED_WEATHER")
    if len({len(x) for x in values}) != 1:
        raise ValueError("UNEQUAL_WEATHER_SERIES")
    points = []
    seen = set()
    for stamp, temp, rain, wind in zip(*values):
        try:
            # Open-Meteo returns wall-clock ISO timestamps, explicitly requested as UTC.
            at = datetime.fromisoformat(stamp).replace(tzinfo=timezone.utc)
        except (ValueError, TypeError, AttributeError):
            continue
        if not now <= at <= now + timedelta(days=MAX_FUTURE_DAYS):
            continue
        if at in seen or at.hour % 3:
            continue
        seen.add(at)
        temp = number(temp, -80, 70)
        rain = number(rain, 0, 500)
        wind = number(wind, 0, 300)
        if temp is None or rain is None or wind is None:
            continue
        points.append({"valid_utc": at.isoformat(), "temperature_c": temp,
                       "precipitation_mm": rain, "wind_speed_kmh": wind})
    if not points:
        raise ValueError("NO_VALID_FUTURE_WEATHER")
    return sorted(points, key=lambda x: x["valid_utc"])[:24]

def weather_url(lat, lon):
    return OPEN_METEO_URL + "?" + urlencode({
        "latitude": str(lat), "longitude": str(lon),
        "hourly": "temperature_2m,precipitation,wind_speed_10m",
        "timezone": "UTC", "forecast_days": "3",
    })

def _safe_error(error):
    if isinstance(error, HTTPError):
        return ("ACCESS_DENIED" if error.code in (401, 403)
                else "RATE_LIMITED" if error.code == 429 else "HTTP_UNAVAILABLE")
    if isinstance(error, (URLError, OSError, TimeoutError)):
        return "NETWORK_UNAVAILABLE"
    return "INVALID_OR_UNAVAILABLE"

def collect(*, now=None, environ=None, requester=None):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("NAIVE_NOW")
    environ = os.environ if environ is None else environ
    output = {"schema": SCHEMA, "collected_utc": now.isoformat(),
              "status": "RESEARCH_ONLY", "model_inputs_changed": False,
              "market_odds_changed": False, "verified_betting_advantage": False,
              "production_recommendations": "DISABLED",
              "open_meteo": {"status": "HOLD", "requests_attempted": 0,
                  "location_accuracy": "CITY_CENTRE_PROXY_NOT_STADIUM",
                  "upstream_issue_time_verified": False,
                  "attribution": ATTRIBUTION, "license_url": LICENSE,
                  "noncommercial_free_terms_apply": True, "cities": []},
              "kleague": {"status": "NOT_CONFIGURED", "configured": False,
                  "requests_attempted": 0, "league_count": 0,
                  "scope": "AUTHORIZED_PARTNER_LEAGUE_CATALOGUE_ONLY",
                  "current_fixtures_verified": False, "odds_available": False}}
    weather = output["open_meteo"]
    for city, display, lat, lon in CITIES:
        row = {"city": city, "display": display, "latitude": lat,
               "longitude": lon, "status": "HOLD", "samples": []}
        weather["requests_attempted"] += 1
        try:
            body = fetch_json(weather_url(lat, lon), requester=requester)
            row["samples"] = weather_hourly(body, now)
            row["status"] = "FORECAST_AVAILABLE"
        except (HTTPError, URLError, OSError, ValueError, TypeError, KeyError) as exc:
            row["status"] = _safe_error(exc)
        weather["cities"].append(row)
    good = sum(r["status"] == "FORECAST_AVAILABLE" for r in weather["cities"])
    weather["status"] = ("RESEARCH_ONLY" if good == len(CITIES)
                         else "PARTIAL_COVERAGE" if good else "HOLD")
    key = environ.get("KLEAGUE_API_KEY", "")
    if isinstance(key, str) and key.strip() and "\r" not in key and "\n" not in key:
        league = output["kleague"]
        league["configured"] = True
        league["requests_attempted"] = 1
        try:
            url = KLEAGUE_URL + "?" + urlencode({"meet_year": str(now.year)})
            body = fetch_json(url, headers={"authKey": key}, requester=requester)
            envelope = body.get("response")
            if not isinstance(envelope, dict):
                raise ValueError("INVALID_KLEAGUE_ENVELOPE")
            code = str(envelope.get("resultCode", ""))
            if code == "00":
                rows = envelope.get("list")
                if not isinstance(rows, list) or len(rows) > MAX_LEAGUES:
                    raise ValueError("INVALID_KLEAGUE_CATALOGUE")
                league["league_count"] = len(rows)
                league["status"] = "CATALOGUE_ACCESS_ONLY"
            elif code in ("01", "02", "03", "04", "06", "07", "08"):
                league["status"] = "KEY_OR_PARTNER_ACCESS_DENIED"
            elif code == "05":
                league["status"] = "QUOTA_EXHAUSTED"
            else:
                league["status"] = "PROVIDER_REJECTED"
        except (HTTPError, URLError, OSError, ValueError, TypeError, KeyError) as exc:
            status = _safe_error(exc)
            league["status"] = ("KEY_OR_PARTNER_ACCESS_DENIED"
                                if status == "ACCESS_DENIED" else status)
    return output

def validate(doc):
    if not isinstance(doc, dict) or doc.get("schema") != SCHEMA:
        raise ValueError("INVALID_CONNECTOR_REPORT")
    utc(doc.get("collected_utc"))
    if any(doc.get(k) is not False for k in
           ("model_inputs_changed", "market_odds_changed",
            "verified_betting_advantage")):
        raise ValueError("MAY_NOT_ENABLE_MODEL_OR_BETTING")
    if doc.get("production_recommendations") != "DISABLED":
        raise ValueError("PRODUCTION_MUST_BE_DISABLED")
    weather = doc.get("open_meteo", {})
    if (weather.get("location_accuracy") != "CITY_CENTRE_PROXY_NOT_STADIUM"
            or weather.get("attribution") != ATTRIBUTION
            or weather.get("license_url") != LICENSE
            or weather.get("upstream_issue_time_verified") is not False
            or weather.get("noncommercial_free_terms_apply") is not True
            or weather.get("requests_attempted") != len(CITIES)):
        raise ValueError("BAD_WEATHER_PROVENANCE")
    cities = weather.get("cities")
    if not isinstance(cities, list) or len(cities) != len(CITIES):
        raise ValueError("INVALID_CITY_COUNT")
    for item, (city, display, lat, lon) in zip(cities, CITIES):
        if not isinstance(item, dict) or any((
                item.get("city") != city, item.get("display") != display,
                item.get("latitude") != lat, item.get("longitude") != lon)):
            raise ValueError("UNVERIFIED_LOCATION")
        samples = item.get("samples")
        if not isinstance(samples, list) or len(samples) > 24:
            raise ValueError("INVALID_SAMPLES")
        if item.get("status") == "FORECAST_AVAILABLE" and not samples:
            raise ValueError("FAKE_WEATHER_COVERAGE")
        for s in samples:
            utc(s.get("valid_utc"))
            if any(number(s.get(field), low, high) is None for field, low, high in
                   (("temperature_c", -80, 70), ("precipitation_mm", 0, 500),
                    ("wind_speed_kmh", 0, 300))):
                raise ValueError("UNBOUNDED_WEATHER")
    league = doc.get("kleague", {})
    if league.get("status") not in (
        "NOT_CONFIGURED", "CATALOGUE_ACCESS_ONLY", "KEY_OR_PARTNER_ACCESS_DENIED",
        "QUOTA_EXHAUSTED", "PROVIDER_REJECTED", "INVALID_OR_UNAVAILABLE",
        "HTTP_UNAVAILABLE", "NETWORK_UNAVAILABLE", "RATE_LIMITED"):
        raise ValueError("INVALID_KLEAGUE_STATE")
    if (league.get("requests_attempted") not in (0, 1)
            or league.get("scope") != "AUTHORIZED_PARTNER_LEAGUE_CATALOGUE_ONLY"
            or league.get("current_fixtures_verified") is not False
            or league.get("odds_available") is not False
            or type(league.get("league_count")) is not int
            or not 0 <= league["league_count"] <= MAX_LEAGUES
            or (not league.get("configured") and league["requests_attempted"] != 0)):
        raise ValueError("UNSAFE_KLEAGUE_CLAIM")
    raw = json.dumps(doc)
    if any(token in raw for token in ("authKey", "Bearer ", "bookmaker_quotes")):
        raise ValueError("CREDENTIAL_OR_ODDS_LEAK")
    return True

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="sources/asia_api_latest.json")
    parser.add_argument("--validate-file", default="")
    opts = parser.parse_args()
    if opts.validate_file:
        validate(json.loads(Path(opts.validate_file).read_text(encoding="utf-8")))
        print("ASIA_CONNECTOR_REPORT_VALID")
        return
    report = collect()
    validate(report)
    target = Path(opts.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    print(json.dumps({"open_meteo": report["open_meteo"]["status"],
                      "kleague": report["kleague"]["status"],
                      "no_betting": True}))

if __name__ == "__main__":
    main()

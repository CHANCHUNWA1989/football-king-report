"""Bounded, private, raw TheSportsDB event capture for one historical audit pilot.

This module only preserves a provider observation and never certifies 90-minute
results, real kickoff, upstream independence, predictions or bets. Raw bytes are
written to a new local private folder; DO NOT commit/output them publicly.
"""
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

EVENT_ID = "2508371"
URL = "https://www.thesportsdb.com/api/v1/json/123/lookupevent.php?id=" + EVENT_ID
LEAGUE_ID = "4331"  # German Bundesliga in TheSportsDB
EXPECTED_KICKOFF_UTC = "2026-10-09T18:30:00+00:00"
EXPECTED_SEASON = "2026-2027"
EXPECTED_TEAMS = ("Borussia Dortmund", "Werder Bremen")
# Exact IDs observed in the provider's own event-2508371 API response;
# neither the IDs nor the response independently attest football truth.
EXPECTED_PROVIDER_TEAM_IDS = ("133650", "133662")
MAX_BYTES = 512_000
TIMEOUT_SECONDS = 12
SAFE_ERRORS = frozenset({
    "HTTP_NOT_200", "REDIRECT_OR_WRONG_URL", "NON_JSON_MEDIA_TYPE",
    "EMPTY_OR_OVERSIZED_BODY", "INVALID_JSON", "DUPLICATE_JSON_KEY",
    "EVENT_IDENTITY_MISMATCH", "EVENT_KICKOFF_MISMATCH",
    "EVENT_STATUS_OR_SCORE_UNSUPPORTED", "BAD_CAPTURE_CLOCK",
    "NETWORK_FAILURE", "UNEXPECTED_RESPONSE", "OUTPUT_ALREADY_EXISTS",
    "UNSAFE_OUTPUT_PATH",
})


class CaptureError(ValueError):
    def __init__(self, code):
        if code not in SAFE_ERRORS:
            raise ValueError("UNKNOWN_LOCAL_ERROR_CODE")
        super().__init__(code)
        self.code = code


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _require(check, code):
    if not check:
        raise CaptureError(code)


def _utc(value):
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            # TheSportsDB strTimestamp is documented by the existing collector
            # as UTC, even when the provider omits the timezone offset.
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (ValueError, TypeError, OverflowError, AttributeError) as exc:
        raise CaptureError("EVENT_KICKOFF_MISMATCH") from exc


def _unique_pairs(pairs):
    obj = {}
    for key, value in pairs:
        _require(key not in obj, "DUPLICATE_JSON_KEY")
        obj[key] = value
    return obj


def inspect(raw):
    """Validate one exact event before any bytes are put on disk."""
    _require(type(raw) is bytes and 0 < len(raw) <= MAX_BYTES,
             "EMPTY_OR_OVERSIZED_BODY")
    try:
        doc = json.loads(raw.decode("utf-8", "strict"), object_pairs_hook=_unique_pairs,
                         parse_constant=lambda _: (_ for _ in ()).throw(
                             CaptureError("INVALID_JSON")))
    except CaptureError:
        raise
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        raise CaptureError("INVALID_JSON") from exc
    _require(type(doc) is dict and type(doc.get("events")) is list
             and len(doc["events"]) == 1 and type(doc["events"][0]) is dict,
             "EVENT_IDENTITY_MISMATCH")
    event = doc["events"][0]
    _require(type(event.get("idEvent")) in (str, int)
             and str(event["idEvent"]) == EVENT_ID
             and str(event.get("idLeague")) == LEAGUE_ID
             and event.get("strSport") == "Soccer"
             and event.get("strSeason") == EXPECTED_SEASON
             and (event.get("strHomeTeam"), event.get("strAwayTeam")) == EXPECTED_TEAMS,
             "EVENT_IDENTITY_MISMATCH")
    for name in ("idHomeTeam", "idAwayTeam"):
        _require(type(event.get(name)) in (str, int) and
                 re.fullmatch(r"[1-9][0-9]{0,14}", str(event[name])) is not None,
                 "EVENT_IDENTITY_MISMATCH")
    _require((str(event["idHomeTeam"]), str(event["idAwayTeam"]))
             == EXPECTED_PROVIDER_TEAM_IDS, "EVENT_IDENTITY_MISMATCH")
    kickoff = _utc(event.get("strTimestamp"))
    _require(kickoff.isoformat() == EXPECTED_KICKOFF_UTC, "EVENT_KICKOFF_MISMATCH")
    # FT label is only a provider observation, not authenticated regulation FT.
    _require(event.get("strStatus") in ("Match Finished", "FT", "Finished"),
             "EVENT_STATUS_OR_SCORE_UNSUPPORTED")
    scores = []
    for field in ("intHomeScore", "intAwayScore"):
        val = event.get(field)
        _require(type(val) in (str, int) and re.fullmatch(r"[0-9]{1,2}", str(val))
                 is not None and int(val) <= 30,
                 "EVENT_STATUS_OR_SCORE_UNSUPPORTED")
        scores.append(int(val))
    # Use original provider assertions, not an invented regulator verification.
    return {"provider": "TheSportsDB", "provider_event_id": EVENT_ID,
            "home_provider_team_id": str(event["idHomeTeam"]),
            "away_provider_team_id": str(event["idAwayTeam"]),
            "scheduled_kickoff_utc_provider_claim": kickoff.isoformat(),
            "provider_status_claim": event["strStatus"],
            "provider_score_claim": scores,
            "result_period_authenticated": False, "actual_kickoff_authenticated": False,
            "upstream_independence_authenticated": False}


def _fetch():
    req = Request(URL, headers={"Accept": "application/json",
                                "User-Agent": "FootballKingSingleResultAudit/1.0"})
    requested_at = datetime.now(timezone.utc)
    try:
        with build_opener(NoRedirect()).open(req, timeout=TIMEOUT_SECONDS) as response:
            status = response.getcode()
            final_url = response.geturl()
            media = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
            _require(status == 200, "HTTP_NOT_200")
            _require(final_url == URL, "REDIRECT_OR_WRONG_URL")
            _require(media == "application/json" or media.endswith("+json"),
                     "NON_JSON_MEDIA_TYPE")
            raw = response.read(MAX_BYTES + 1)
            received_at = datetime.now(timezone.utc)
            _require(0 < len(raw) <= MAX_BYTES, "EMPTY_OR_OVERSIZED_BODY")
            # Never fabricate network provenance from a successful parser.
            return raw, {
                "http_status": status,
                "http_final_url": final_url,
                "http_content_type": media,
                "http_redirects_followed": False,
                "request_started_utc": requested_at.isoformat(),
                "response_received_utc": received_at.isoformat(),
            }
    except HTTPError as exc:
        raise CaptureError("REDIRECT_OR_WRONG_URL" if exc.code in (301, 302, 303, 307, 308)
                           else "HTTP_NOT_200") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise CaptureError("NETWORK_FAILURE") from exc


def capture(outdir, *, now=None, raw=None):
    """Make exactly one source request (or injected offline bytes); write privately.

    outdir must not exist; its parent must already be a trusted directory.
    A hash is only byte integrity, never authentication of upstream publisher truth.
    """
    # A live HTTP provenance clock cannot be supplied by the caller.
    _require(raw is not None or now is None, "BAD_CAPTURE_CLOCK")
    at = now if now is not None else datetime.now(timezone.utc)
    _require(type(at) is datetime and at.tzinfo is not None
             and at.utcoffset() is not None
             and at.utcoffset() == timedelta(0), "BAD_CAPTURE_CLOCK")
    target = Path(outdir)
    # Never overwrite research data or follow a symlink through the final parent.
    _require(target.name not in ("", ".", "..") and target.parent.is_dir()
             and not any(ancestor.is_symlink() for ancestor in
                         (target.parent, *target.parent.parents)), "OUTPUT_ALREADY_EXISTS")
    _require(not target.exists() and not target.is_symlink(), "OUTPUT_ALREADY_EXISTS")
    # An accidental capture inside the public Git checkout could later be
    # committed/published. Refuse it regardless of file permissions.
    _require(not target.resolve().is_relative_to(Path(__file__).resolve().parents[1]),
             "UNSAFE_OUTPUT_PATH")
    if raw is None:
        incoming, transport = _fetch()
        at = datetime.fromisoformat(transport["response_received_utc"])
    else:
        incoming = raw
        transport = {
            "http_status": None, "http_final_url": None,
            "http_content_type": None, "http_redirects_followed": None,
            "request_started_utc": None, "response_received_utc": None,
        }
    claim = inspect(incoming)
    manifest = {"schema": "football-king-sportsdb-single-event-capture-v1",
                "provider": "TheSportsDB", "fixed_api_url": URL,
                "api_terms_url": "https://www.thesportsdb.com/docs_terms_of_use.php",
                **transport,
                "capture_mode": "LIVE_API" if raw is None else "OFFLINE_TEST_ONLY",
                "observed_utc": at.isoformat(),
                "raw_filename": "sportsdb-event.json",
                "raw_sha256": hashlib.sha256(incoming).hexdigest(),
                "raw_bytes": len(incoming), "source_observation": claim,
                "status": "HOLD", "reason": "PROVIDER_OBSERVATION_NOT_TRUSTED_ADMISSION",
                "independently_verified": False,
                "eligible_for_model_scoring": False,
                "eligible_for_betting_promotion": False,
                "production_recommendations": "DISABLED"}
    # Both files are local-only. The default deployment must never upload or
    # put raw bytes in the public repository or public GitHub Actions artifacts.
    old_umask = os.umask(0o077)
    created = False
    try:
        os.mkdir(target, 0o700)
        created = True
        for filename, data in (("sportsdb-event.json", incoming),
                               ("manifest.json", (json.dumps(manifest, ensure_ascii=False,
                                                             sort_keys=True, indent=2,
                                                             allow_nan=False) + "\n").encode())):
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
            fd = os.open(target / filename, flags, 0o600)
            with os.fdopen(fd, "wb") as dst:
                dst.write(data)
                dst.flush()
                os.fsync(dst.fileno())
            fileinfo = os.stat(target / filename, follow_symlinks=False)
            if not stat.S_ISREG(fileinfo.st_mode) or fileinfo.st_nlink != 1:
                raise CaptureError("UNEXPECTED_RESPONSE")
    except BaseException:
        if created:
            for file in ("sportsdb-event.json", "manifest.json"):
                try:
                    (target / file).unlink()
                except FileNotFoundError:
                    pass
            target.rmdir()
        raise
    finally:
        os.umask(old_umask)
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-output-dir", type=Path, required=True,
                        help="new, local, private directory; NEVER use public repository")
    args = parser.parse_args(argv)
    try:
        result = capture(args.private_output_dir)
    except CaptureError as exc:
        print(json.dumps({"status": "HOLD", "reason": exc.code,
                          "independently_verified": False,
                          "production_recommendations": "DISABLED"}))
        return 1
    print(json.dumps({"status": result["status"], "reason": result["reason"],
                      "raw_sha256": result["raw_sha256"],
                      "provider_event_id": EVENT_ID,
                      "independently_verified": False,
                      "production_recommendations": "DISABLED"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

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

EVENT_ID = "2508371"  # Legacy default; one allowed event per capture invocation.
URL_BASE = "https://www.thesportsdb.com/api/v1/json/123/lookupevent.php?id="
URL = URL_BASE + EVENT_ID
LEAGUE_ID = "4331"  # German Bundesliga in TheSportsDB
EXPECTED_SEASON = "2026-2027"
# Fixed source-native identities observed from exact official API event responses.
# These values are provider assertions; they do not independently establish FT.
FIXED_EVENTS = {
    "2508371": {
        "kickoff": "2026-10-09T18:30:00+00:00",
        "teams": ("Borussia Dortmund", "Werder Bremen"),
        "team_ids": ("133650", "133662"),
    },
    "2508372": {
        "kickoff": "2026-10-10T13:30:00+00:00",
        "teams": ("Hoffenheim", "Hamburg"),
        "team_ids": ("133657", "133651"),
    },
}
EXPECTED_KICKOFF_UTC = FIXED_EVENTS[EVENT_ID]["kickoff"]
EXPECTED_TEAMS = FIXED_EVENTS[EVENT_ID]["teams"]
EXPECTED_PROVIDER_TEAM_IDS = FIXED_EVENTS[EVENT_ID]["team_ids"]
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


def inspect(raw, *, event_id=EVENT_ID):
    """Validate one allowlisted exact event before any bytes are put on disk."""
    _require(type(event_id) is str and event_id in FIXED_EVENTS,
             "EVENT_IDENTITY_MISMATCH")
    profile = FIXED_EVENTS[event_id]
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
             and str(event["idEvent"]) == event_id
             and str(event.get("idLeague")) == LEAGUE_ID
             and event.get("strSport") == "Soccer"
             and event.get("strSeason") == EXPECTED_SEASON
             and (event.get("strHomeTeam"), event.get("strAwayTeam")) == profile["teams"],
             "EVENT_IDENTITY_MISMATCH")
    for name in ("idHomeTeam", "idAwayTeam"):
        _require(type(event.get(name)) in (str, int) and
                 re.fullmatch(r"[1-9][0-9]{0,14}", str(event[name])) is not None,
                 "EVENT_IDENTITY_MISMATCH")
    _require((str(event["idHomeTeam"]), str(event["idAwayTeam"]))
             == profile["team_ids"], "EVENT_IDENTITY_MISMATCH")
    kickoff = _utc(event.get("strTimestamp"))
    _require(kickoff.isoformat() == profile["kickoff"], "EVENT_KICKOFF_MISMATCH")
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
    return {"provider": "TheSportsDB", "provider_event_id": event_id,
            "home_provider_team_id": str(event["idHomeTeam"]),
            "away_provider_team_id": str(event["idAwayTeam"]),
            "scheduled_kickoff_utc_provider_claim": kickoff.isoformat(),
            "provider_status_claim": event["strStatus"],
            "provider_score_claim": scores,
            "result_period_authenticated": False, "actual_kickoff_authenticated": False,
            "upstream_independence_authenticated": False}


def _fetch(event_id=EVENT_ID):
    _require(type(event_id) is str and event_id in FIXED_EVENTS,
             "EVENT_IDENTITY_MISMATCH")
    event_url = URL_BASE + event_id
    req = Request(event_url, headers={"Accept": "application/json",
                                "User-Agent": "FootballKingSingleResultAudit/1.0"})
    requested_at = datetime.now(timezone.utc)
    try:
        with build_opener(NoRedirect()).open(req, timeout=TIMEOUT_SECONDS) as response:
            status = response.getcode()
            final_url = response.geturl()
            media = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
            _require(status == 200, "HTTP_NOT_200")
            _require(final_url == event_url, "REDIRECT_OR_WRONG_URL")
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


def capture(outdir, *, now=None, raw=None, event_id=EVENT_ID):
    """Make exactly one fixed source request (or injected offline bytes); write privately.

    outdir must not exist; its parent must already be a trusted directory.
    A hash is only byte integrity, never authentication of upstream publisher truth.
    """
    # No caller-provided arbitrary URLs, names, fixture IDs or league IDs.
    _require(type(event_id) is str and event_id in FIXED_EVENTS,
             "EVENT_IDENTITY_MISMATCH")
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
        incoming, transport = _fetch(event_id)
        at = datetime.fromisoformat(transport["response_received_utc"])
    else:
        incoming = raw
        transport = {
            "http_status": None, "http_final_url": None,
            "http_content_type": None, "http_redirects_followed": None,
            "request_started_utc": None, "response_received_utc": None,
        }
    claim = inspect(incoming, event_id=event_id)
    manifest = {"schema": "football-king-sportsdb-single-event-capture-v1",
                "provider": "TheSportsDB", "fixed_api_url": URL_BASE + event_id,
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



def verify_capture_bytes(raw, manifest_raw, *, require_live=True, event_id=EVENT_ID):
    """Recheck provider raw JSON and receipt in memory, without writing plaintext.

    A complete replay does NOT establish publisher authenticity, independent
    FT sources, original source fetch timing, real kickoff, or trusted admission.
    """
    _require(type(event_id) is str and event_id in FIXED_EVENTS,
             "EVENT_IDENTITY_MISMATCH")
    _require(type(raw) is bytes and 0 < len(raw) <= MAX_BYTES
             and type(manifest_raw) is bytes and 0 < len(manifest_raw) <= 16_384,
             "EMPTY_OR_OVERSIZED_BODY")
    try:
        manifest = json.loads(manifest_raw.decode("utf-8", "strict"),
                              object_pairs_hook=_unique_pairs,
                              parse_constant=lambda _: (_ for _ in ()).throw(
                                  CaptureError("INVALID_JSON")))
    except CaptureError:
        raise
    except (ValueError, UnicodeError, TypeError, RecursionError) as exc:
        raise CaptureError("INVALID_JSON") from exc
    _require(type(manifest) is dict and manifest.get("schema")
             == "football-king-sportsdb-single-event-capture-v1"
             and manifest.get("provider") == "TheSportsDB"
             and manifest.get("fixed_api_url") == URL_BASE + event_id
             and manifest.get("raw_filename") == "sportsdb-event.json"
             and manifest.get("raw_bytes") == len(raw)
             and manifest.get("raw_sha256") == hashlib.sha256(raw).hexdigest(),
             "UNEXPECTED_RESPONSE")
    claim = inspect(raw, event_id=event_id)
    _require(manifest.get("source_observation") == claim
             and manifest.get("status") == "HOLD"
             and manifest.get("reason") == "PROVIDER_OBSERVATION_NOT_TRUSTED_ADMISSION"
             and manifest.get("independently_verified") is False
             and manifest.get("eligible_for_model_scoring") is False
             and manifest.get("eligible_for_betting_promotion") is False
             and manifest.get("production_recommendations") == "DISABLED",
             "UNEXPECTED_RESPONSE")
    if require_live:
        _require(manifest.get("capture_mode") == "LIVE_API"
                 and manifest.get("http_status") == 200
                 and manifest.get("http_final_url") == URL_BASE + event_id
                 and manifest.get("http_content_type") == "application/json"
                 and manifest.get("http_redirects_followed") is False,
                 "UNEXPECTED_RESPONSE")
        try:
            first = datetime.fromisoformat(manifest["request_started_utc"])
            last = datetime.fromisoformat(manifest["response_received_utc"])
            recorded = datetime.fromisoformat(manifest["observed_utc"])
            _require(all(v.tzinfo is not None and v.utcoffset() == timedelta(0)
                         for v in (first, last, recorded))
                     and first <= last == recorded
                     and 0 <= (last-first).total_seconds() <= TIMEOUT_SECONDS + 5,
                     "BAD_CAPTURE_CLOCK")
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            raise CaptureError("BAD_CAPTURE_CLOCK") from exc
    return {
        "status": "HOLD", "raw_integrity_replayed": True,
        "provider_event_id": event_id,
        "raw_sha256": manifest["raw_sha256"],
        "raw_bytes": len(raw),
        "capture_mode": manifest["capture_mode"],
        "independently_verified": False,
        "actual_kickoff_authenticated": False,
        "upstream_independence_authenticated": False,
        "production_recommendations": "DISABLED",
    }


def verify_capture(folder, *, require_live=True, event_id=EVENT_ID):
    """Re-read exact local raw bytes and receipt; check integrity, not source truth.

    This is intentionally not a trusted settlement admission: a manifest and
    local checksum cannot independently attest the upstream or actual kickoff.
    """
    _require(type(event_id) is str and event_id in FIXED_EVENTS,
             "EVENT_IDENTITY_MISMATCH")
    root = Path(folder)
    _require(root.is_dir() and not root.is_symlink()
             and not any(parent.is_symlink() for parent in root.parents),
             "UNSAFE_OUTPUT_PATH")
    root_info = root.stat()
    _require(stat.S_ISDIR(root_info.st_mode)
             and (root_info.st_mode & 0o077) == 0, "UNSAFE_OUTPUT_PATH")
    _require({entry.name for entry in root.iterdir()}
             == {"sportsdb-event.json", "manifest.json"}, "UNEXPECTED_RESPONSE")
    contents = {}
    for name in ("sportsdb-event.json", "manifest.json"):
        item = root / name
        info = item.lstat()
        _require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1
                 and (info.st_mode & 0o077) == 0, "UNSAFE_OUTPUT_PATH")
        limit = MAX_BYTES if name == "sportsdb-event.json" else 16_384
        with item.open("rb") as handle:
            contents[name] = handle.read(limit + 1)
        _require(0 < len(contents[name]) <= limit, "EMPTY_OR_OVERSIZED_BODY")
    return verify_capture_bytes(contents["sportsdb-event.json"], contents["manifest.json"],
                                require_live=require_live, event_id=event_id)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-output-dir", type=Path, required=True,
                        help="new, local, private directory; NEVER use public repository")
    parser.add_argument("--event-id", choices=sorted(FIXED_EVENTS),
                        default=EVENT_ID, help="one explicitly allowlisted source event")
    args = parser.parse_args(argv)
    try:
        result = capture(args.private_output_dir, event_id=args.event_id)
    except CaptureError as exc:
        print(json.dumps({"status": "HOLD", "reason": exc.code,
                          "independently_verified": False,
                          "production_recommendations": "DISABLED"}))
        return 1
    print(json.dumps({"status": result["status"], "reason": result["reason"],
                      "raw_sha256": result["raw_sha256"],
                      "provider_event_id": args.event_id,
                      "independently_verified": False,
                      "production_recommendations": "DISABLED"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

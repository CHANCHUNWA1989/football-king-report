"""Safely verify optional provider keys with at most one read-only request each.

Never print, include in URL, save to repository, or echo provider secrets.
No new registration/accounts created; owners must accept terms themselves.
"""
import argparse
import json
import os
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request
from secondary_sources import NoRedirect

PROVIDERS = (
    ("api_football", "API_FOOTBALL_KEY",
     "https://v3.football.api-sports.io/countries", "x-apisports-key"),
    ("football_data_org", "FOOTBALL_DATA_ORG_TOKEN",
     "https://api.football-data.org/v4/competitions", "X-Auth-Token"),
    ("sportmonks", "SPORTMONKS_API_TOKEN",
     "https://api.sportmonks.com/v3/football/leagues/271", "Authorization"),
)


def check_one(provider, secret_name, url, header, environ, *, requester=None):
    token = environ.get(secret_name, "")
    if not isinstance(token, str) or not token.strip():
        return {"provider":provider, "secret_present":False, "status":"NOT_CONFIGURED"}
    outcome = {"provider":provider, "secret_present":True, "status":"UNKNOWN"}
    try:
        if not url.startswith("https://"):
            raise ValueError("NON_HTTPS_PROVIDER")
        if any(x in token for x in ("\n","\r")):
            raise ValueError("INVALID_TOKEN")
        req = Request(url, headers={header:token, "Accept":"application/json",
                                     "User-Agent":"FootballKingKeyProbe/1.0"})
        with (requester or NoRedirect())(req, timeout=12) as response:
            payload = response.read(200_001)
        if len(payload) > 200_000:
            raise ValueError("TOO_MUCH_PROVIDER_DATA")
        body = json.loads(payload.decode("utf-8"))
        if not isinstance(body, dict):
            raise ValueError("INVALID_PROVIDER_RESPONSE")
        # Some providers return HTTP 200 with application-specific errors.
        if body.get("errors") and body["errors"] not in ({},[]):
            outcome["status"]="PROVIDER_REJECTED_OR_PLAN_LIMITED"
        elif "error" in body and body["error"]:
            outcome["status"]="PROVIDER_REJECTED_OR_PLAN_LIMITED"
        else:
            outcome["status"]="KEY_ACCEPTED"
    except HTTPError as e:
        outcome["status"]={
            401:"KEY_REJECTED", 403:"PLAN_OR_KEY_REJECTED",
            429:"FREE_RATE_LIMITED"}.get(e.code,"PROVIDER_HTTP_ERROR")
    except (URLError,TimeoutError,OSError):
        outcome["status"]="NETWORK_FAILURE"
    except (UnicodeError,ValueError,TypeError,json.JSONDecodeError):
        outcome["status"]="INVALID_PROVIDER_RESPONSE"
    # Never include provider error text, URLs, response body or credentials.
    return outcome


def check_all(environ=None, requester=None):
    environ = os.environ if environ is None else environ
    rows = [check_one(*definition, environ, requester=requester)
            for definition in PROVIDERS]
    return {
        "schema":"football-king-private-api-key-check-v1",
        "checked_utc":datetime.now(timezone.utc).isoformat(),
        "key_checks":rows,
        "credentials_logged":False, "requests_per_configured_provider":1,
        "charges_or_subscriptions_created":False,
        "production_recommendations":"DISABLED",
    }


if __name__=="__main__":
    cli=argparse.ArgumentParser()
    cli.add_argument("--out",default="")
    args=cli.parse_args()
    result=check_all()
    # Safe to print only aggregated *non-secret* status.
    print(json.dumps(result,ensure_ascii=False,indent=2))
    if args.out:
        from pathlib import Path
        Path(args.out).write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",
                                  encoding="utf-8")

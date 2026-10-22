"""Verify European sports catalogue using existing Odds API credentials.

Only calls the free /v4/sports/ discovery endpoint. No odds queries, and no
secret or raw provider response is logged or saved.
"""
import json
import os

from ops.european_sports_catalogue import reconcile
from ops.odds_market import APIProblem, retrieve


def verify_european_catalogue(key, *, opener=None):
    if opener is None:
        from urllib.request import urlopen
        opener = urlopen
    sports, quota = retrieve("/sports/", key, opener=opener)
    report = reconcile(sports)
    report["connected"] = True
    report["quota"] = quota
    report["source_verified_with_secret"] = True
    return report


def main():
    try:
        report = verify_european_catalogue(os.environ.get("THE_ODDS_API_KEY", ""))
        print(json.dumps(report, ensure_ascii=False))
        return 0
    except (APIProblem, ValueError, TypeError):
        print(json.dumps({"status": "HOLD", "connected": False,
                          "production_recommendations": "DISABLED",
                          "error_code": "CATALOGUE_VERIFICATION_FAILED"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

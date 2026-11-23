"""Observe GitHub's effective archive branch rules, NEVER authorize a write.

Uses only fixed unauthenticated GET requests to the public repository's
effective rules endpoint and classic branch protection endpoint.
No credentials, secrets, ruleset mutation, branch writes, or ref changes.
Even observed rules do NOT prove bypass actor scopes, enforcement behavior,
independent human approval, append-only custody, or rights to source data.
"""

import argparse
import json
from urllib import error, request

ROOT = "https://api.github.com/repos/CHANCHUNWA1989/football-king-report"
ARCHIVE_BRANCH = "research%2Fforward-provenance-archive"
RULES_URL = ROOT + "/rules/branches/" + ARCHIVE_BRANCH + "?per_page=100&page=1"
CLASSIC_URL = ROOT + "/branches/" + ARCHIVE_BRANCH + "/protection"
LIMIT = 131072
HTTP_OBSERVED = {200, 401, 403, 404, 429, 500, 502, 503}
OBSERVED_RULES = {"deletion", "non_fast_forward"}
HEADERS = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
    "User-Agent": "football-king-readonly-policy-audit",
}


class PolicyHold(ValueError):
    """Safe, bounded diagnostic failure. Never carry API bodies or secrets."""


def _pairs_unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise PolicyHold("DUPLICATE_POLICY_JSON_KEYS")
        result[key] = value
    return result


def _decode(raw):
    if not isinstance(raw, bytes) or not 0 < len(raw) <= LIMIT:
        raise PolicyHold("INVALID_POLICY_RESPONSE_SIZE")
    try:
        return json.loads(raw, object_pairs_hook=_pairs_unique,
                          parse_constant=lambda _: (_ for _ in ()).throw(
                              PolicyHold("NONFINITE_POLICY_VALUE")))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise PolicyHold("UNREADABLE_POLICY_JSON") from exc


def _summary(rule_status, raw_rules, classic_status, raw_classic):
    """Only counts/types and HTTP statuses; always HOLD for release.

    404 for classic protection can be a permissions mask. Do not claim it
    proves branch protection absent. Rule endpoint returns active rulesets'
    rules but excludes classic protection and bypass actor details.
    """
    if rule_status not in HTTP_OBSERVED or classic_status not in HTTP_OBSERVED:
        raise PolicyHold("UNEXPECTED_POLICY_HTTP_STATUS")
    active_types = set()
    complete = False
    if rule_status == 200:
        rules = _decode(raw_rules)
        if not isinstance(rules, list):
            raise PolicyHold("INVALID_EFFECTIVE_RULES_SHAPE")
        if len(rules) > 100:
            raise PolicyHold("EFFECTIVE_RULES_UNBOUNDED")
        for item in rules:
            if not isinstance(item, dict) or not isinstance(item.get("type"), str):
                raise PolicyHold("INVALID_EFFECTIVE_RULE_ITEM")
            active_types.add(item["type"])
        complete = len(rules) < 100
    if classic_status == 200 and not isinstance(_decode(raw_classic), dict):
        raise PolicyHold("INVALID_CLASSIC_PROTECTION_SHAPE")
    if rule_status == 200 and classic_status in (200, 404) and complete:
        label = "HOLD_POLICY_OBSERVATION_ONLY_NOT_AUTHORIZED"
    else:
        label = "HOLD_POLICY_NOT_COMPLETELY_OBSERVED"
    return {
        "schema": "football-king-archive-branch-policy-observation-1",
        "status": label,
        "effective_rules_http_status": rule_status,
        "classic_protection_http_status": classic_status,
        "rules_response_complete": complete,
        "effective_non_fast_forward_rule_observed":
            "non_fast_forward" in active_types,
        "effective_deletion_rule_observed": "deletion" in active_types,
        "classic_protection_fully_audited": False,
        "ruleset_bypass_actors_audited": False,
        "writer_identity_approved": False,
        "reviewer_independent_approval": False,
        "remote_synthetic_canary_write_verified": False,
        "ruleset_activation_authorized": False,
        "production_recommendations": "DISABLED",
    }


def _get(url):
    """No redirects, auth, or retry; allow only the two fixed public URLs."""
    if url not in (RULES_URL, CLASSIC_URL):
        raise PolicyHold("POLICY_URL_NOT_ALLOWLISTED")
    req = request.Request(url, headers=HEADERS, method="GET")
    try:
        # urllib may follow redirects; do not permit a redirect target in this
        # read-only security probe by installing a rejecting opener.
        class NoRedirect(request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                return None
        with request.build_opener(NoRedirect).open(req, timeout=15) as resp:
            status = resp.status
            body = resp.read(LIMIT + 1)
    except error.HTTPError as exc:
        # Only expose status, never API body/headers/tokens.
        status, body = exc.code, b""
    except (error.URLError, OSError, TimeoutError) as exc:
        raise PolicyHold("PUBLIC_POLICY_LOOKUP_UNAVAILABLE") from exc
    if status not in HTTP_OBSERVED:
        raise PolicyHold("UNEXPECTED_POLICY_HTTP_STATUS")
    if status == 200 and not 0 < len(body) <= LIMIT:
        raise PolicyHold("PUBLIC_POLICY_BODY_MISSING_OR_UNBOUNDED")
    return status, body


def observe():
    rules_status, raw_rules = _get(RULES_URL)
    classic_status, raw_classic = _get(CLASSIC_URL)
    return _summary(rules_status, raw_rules, classic_status, raw_classic)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--observe-only", action="store_true", required=True)
    parser.parse_args(argv)
    try:
        result = observe()
    except (PolicyHold, ValueError, OSError, TypeError):
        print(json.dumps({
            "status": "HOLD_REMOTE_BRANCH_POLICY_NOT_VERIFIABLE",
            "ruleset_activation_authorized": False,
            "production_recommendations": "DISABLED",
        }, sort_keys=True))
        return 1
    print(json.dumps(result, sort_keys=True))
    # A completed observational probe may be green despite "HOLD";
    # no writer/cutover workflow may use this exit status as authorization.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

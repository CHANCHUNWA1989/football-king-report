"""Read-only GH CLI HTTP-status diagnostic for a FUTURE authorized archive canary.

Do not echo GitHub API bodies, response headers, tokens or raw exception text.
This module NEVER executes gh/curl and NEVER writes or edits GitHub. It only
classifies an observed *first response status line* together with a supplied
process exit code. A 403/409/422 alone does NOT establish a root cause.
"""

import argparse
import json
import re
import sys

MAX_STATUS_LINE = 2048
STATUS = re.compile(rb"HTTP/(?:1\.[01]|2(?:\.0)?|3(?:\.0)?) ([1-5][0-9]{2})(?:[ \t][^\r\n]*)?\r?\n?\Z")
KINDS = {
    400: "REQUEST_INVALID_OR_MALFORMED",
    401: "AUTHENTICATION_REQUIRED_OR_EXPIRED",
    403: "FORBIDDEN_PERMISSIONS_OR_BRANCH_RULE_UNVERIFIED",
    404: "RESOURCE_NOT_FOUND",
    409: "CONFLICT_STALE_SHA_OR_CONCURRENT_WRITE_UNVERIFIED",
    422: "VALIDATION_OR_REPOSITORY_POLICY_UNVERIFIED",
    429: "RATE_LIMITED",
}


def inspect(first_line, exit_code):
    """Return only allowlisted numeric/classification fields, no untrusted text.

    This cannot diagnose old logs that suppressed HTTP responses. Even when
    status is present, it is an observation not authenticated root-cause proof.
    """
    if not isinstance(first_line, bytes) or not isinstance(exit_code, int):
        raise ValueError("INVALID_DIAGNOSTIC_ARGUMENTS")
    if len(first_line) > MAX_STATUS_LINE:
        first_line = b""  # fail closed; never echo the original line
    match = STATUS.fullmatch(first_line)
    observed = int(match.group(1)) if match else None
    if observed is None:
        kind = "HTTP_STATUS_NOT_CAPTURED"
    elif 200 <= observed < 300:
        kind = "HTTP_2XX_RESPONSE"
    elif observed in KINDS:
        kind = KINDS[observed]
    elif 500 <= observed <= 599:
        kind = "REMOTE_SERVER_ERROR"
    elif 400 <= observed < 500:
        kind = "OTHER_CLIENT_ERROR"
    elif 300 <= observed < 400:
        kind = "UNEXPECTED_REDIRECT"
    else:
        kind = "UNEXPECTED_HTTP_STATUS"
    request_succeeded = (exit_code == 0 and observed in (200, 201))
    if observed in (200, 201) and exit_code != 0:
        kind = "EXIT_STATUS_AND_HTTP_STATUS_DISAGREE"
    if exit_code == 0 and (observed is None or not 200 <= observed < 300):
        kind = "EXIT_STATUS_AND_HTTP_STATUS_DISAGREE"
    return {
        "status": "OBSERVED_REDACTED_NOT_ROOT_CAUSE",
        "http_status": observed,
        "classification": kind,
        "cli_exit_zero": exit_code == 0,
        "contents_write_succeeded": request_succeeded,
        "retry_root_cause_verified": False,
        "production_recommendations": "DISABLED",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exit-code", required=True, type=int,
                        help="Actual exit code of a separate authorized gh api attempt")
    args = parser.parse_args(argv)
    # Consume only the first status line from an explicit capture (e.g. gh api -i).
    # No request is issued, no body is read, and no raw line is printed.
    first_line = sys.stdin.buffer.readline(MAX_STATUS_LINE + 1)
    print(json.dumps(inspect(first_line, args.exit_code), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

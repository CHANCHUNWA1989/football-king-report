"""Bounded, read-only Pages artifact visibility gate; never deploys."""
import json
import os
import subprocess
import time


def valid_expected_id(value):
    return value is None or (type(value) is int and 0 < value < 2**63)


def classify(payload, expected_id=None):
    """Return READY, WAIT or REJECT; count all named artifacts before filtering."""
    if not valid_expected_id(expected_id):
        return "REJECT"
    if not isinstance(payload, dict):
        return "WAIT"
    rows = payload.get("artifacts")
    total = payload.get("total_count")
    if not isinstance(rows, list) or type(total) is not int or total != len(rows):
        return "WAIT"  # incomplete or malformed page
    if any(not isinstance(row, dict) or not isinstance(row.get("name"), str) for row in rows):
        return "WAIT"
    if expected_id is not None and any(
        type(row.get("id")) is int and row["id"] == expected_id
        and row["name"] != "github-pages" for row in rows
    ):
        return "REJECT"
    matches = [row for row in rows if row["name"] == "github-pages"]
    if len(matches) > 1:
        return "REJECT"
    if not matches:
        return "WAIT"
    row = matches[0]
    if expected_id is not None and type(row.get("id")) is int and row["id"] != expected_id:
        return "REJECT"
    return "READY" if (
        row.get("expired") is False
        and type(row.get("id")) is int and row["id"] > 0
        and type(row.get("size_in_bytes")) is int and row["size_in_bytes"] > 0
    ) else "WAIT"


def wait_visible(fetch, pause=time.sleep, *, expected_id=None):
    if not valid_expected_id(expected_id):
        return 2
    for attempt in range(6):
        try:
            status = classify(fetch(), expected_id)
        except (subprocess.SubprocessError, OSError, ValueError):
            status = "WAIT"
        if status == "READY":
            return 0
        if status == "REJECT":
            return 2
        if attempt < 5:
            pause(5)
    return 1


def main():
    repo = os.environ["GITHUB_REPOSITORY"]
    run = os.environ["GITHUB_RUN_ID"]
    expected = os.environ.get("EXPECTED_PAGES_ARTIFACT_ID", "")
    if not run.isascii() or not run.isdecimal() or not expected.isascii() or not expected.isdecimal() or not 0 < int(expected) < 2**63:
        return 1

    def fetch():
        result = subprocess.run(
            ["gh", "api", f"repos/{repo}/actions/runs/{run}/artifacts?name=github-pages&per_page=100"],
            check=True, capture_output=True, text=True, timeout=10,
        )
        return json.loads(result.stdout)

    code = wait_visible(fetch, expected_id=int(expected))
    print({0: "Unique nonexpired Pages artifact visible.",
           1: "Pages artifact visibility not verified.",
           2: "Ambiguous Pages artifacts; refusing deployment."}[code])
    return code


if __name__ == "__main__":
    raise SystemExit(main())

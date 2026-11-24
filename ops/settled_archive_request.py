"""Prepare a file-backed Contents API request; never pass payload via argv.

The caller remains responsible for validating and merging research evidence.
No network calls, credentials, or production authorization are involved.
"""
import argparse
import base64
import json
import re
from pathlib import Path


def request_body(raw, sha):
    if sha and not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise ValueError("INVALID_CURRENT_BLOB_SHA")
    if not raw:
        raise ValueError("EMPTY_MERGED_EVIDENCE")
    result = {
        "branch": "main",
        "message": ("Safely merge forward-only research settlements" if sha
                    else "Initialize protected forward-only research settlements"),
        "content": base64.b64encode(raw).decode("ascii"),
    }
    if sha:
        result["sha"] = sha
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--merged", required=True)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    payload = request_body(Path(args.merged).read_bytes(), args.sha)
    Path(args.output).write_text(json.dumps(payload) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

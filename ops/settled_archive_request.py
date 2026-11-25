"""Prepare a file-backed Contents API request; never pass payload via argv.

The caller remains responsible for validating and merging research evidence.
No network calls, credentials, or production authorization are involved.
"""
import argparse
import base64
import hashlib
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


def current_blob(response):
    """Bind existing evidence bytes and CAS SHA to one Contents API response."""
    if (type(response) is not dict or response.get("type") != "file"
            or response.get("path") != "evidence/settled.json"
            or response.get("encoding") != "base64"
            or type(response.get("sha")) is not str
            or not re.fullmatch(r"[0-9a-f]{40}", response["sha"])
            or type(response.get("size")) is not int
            or not 0 < response["size"] <= 8 * 1024 * 1024
            or type(response.get("content")) is not str):
        raise ValueError("INVALID_CURRENT_CONTENTS_RESPONSE")
    raw = base64.b64decode(response["content"].replace("\n", "").replace("\r", ""),
                           validate=True)
    actual = hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw).hexdigest()
    if len(raw) != response["size"] or actual != response["sha"]:
        raise ValueError("CURRENT_BLOB_BYTES_SHA_MISMATCH")
    return raw, actual


def main():
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--merged")
    mode.add_argument("--current-response")
    parser.add_argument("--sha")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    if args.current_response is not None:
        if args.sha is not None:
            parser.error("sha is read from the current response")
        raw, sha = current_blob(json.loads(Path(args.current_response).read_bytes()))
        Path(args.output).write_bytes(raw)
        print(sha)
    else:
        if args.sha is None:
            parser.error("--merged requires --sha")
        payload = request_body(Path(args.merged).read_bytes(), args.sha)
        Path(args.output).write_text(json.dumps(payload) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

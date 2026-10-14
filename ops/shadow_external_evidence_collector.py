"""Collect raw public match-result evidence without claiming score verification.

A source fetch is evidence of bytes received, not independent score attestation.
No parsed result from this collector is eligible for model scoring.
"""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

SOURCES = {
    "DFB": "https://datencenter.dfb.de/de/competitions/bundesliga/seasons/2026-2027/matchday/current",
    "NDR": "https://www.ndr.de/sport/ergebnisse/Alle-Ergebnisse-Fussball-Bundesliga-2026-2027%2Cfussballmaenner-486.html",
}
MAX_BYTES = 3_000_000

def fetch(url, opener=urlopen):
    request = Request(url, headers={"User-Agent": "football-king-shadow-research/1.0",
                                    "Accept": "text/html,application/xhtml+xml"})
    with opener(request, timeout=20) as response:
        body = response.read(MAX_BYTES + 1)
        if len(body) > MAX_BYTES:
            raise ValueError("SOURCE_TOO_LARGE")
        return body, getattr(response, "status", 200), response.headers.get("Content-Type", "")

def collect(outdir, getter=fetch, now=None):
    folder = Path(outdir)
    folder.mkdir(parents=True, exist_ok=True)
    captured = (now or datetime.now(timezone.utc)).isoformat()
    manifest = {"schema": "football-king-external-raw-evidence-v1",
                "captured_utc": captured, "status": "HOLD",
                "independently_verified": False,
                "eligible_for_model_scoring": False,
                "production_recommendations": "DISABLED", "sources": []}
    for provider, url in SOURCES.items():
        entry = {"provider": provider, "source_url": url, "status": "ERROR"}
        try:
            body, http_status, content_type = getter(url)
            if not isinstance(body, bytes) or not body:
                raise ValueError("EMPTY_OR_INVALID_BODY")
            if http_status != 200:
                raise ValueError("NON_200_RESPONSE")
            filename = provider.lower() + ".html"
            (folder / filename).write_bytes(body)
            entry.update(status="FETCHED_UNVERIFIED", raw_file=filename,
                         raw_sha256=hashlib.sha256(body).hexdigest(),
                         bytes=len(body), http_status=http_status,
                         content_type=content_type)
        except (OSError, ValueError, TypeError, TimeoutError) as exc:
            entry["error_type"] = type(exc).__name__
        manifest["sources"].append(entry)
    (folder / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    print(json.dumps(collect(args.output_dir), ensure_ascii=False))

if __name__ == "__main__":
    main()

"""Research-only multi-league OpenFootball raw snapshot collector.

Single publisher coverage is never independent FT verification or model scoring.
"""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, Request, build_opener

if __package__:
    from .shadow_raw_source_collector import (FetchValidationError, MAX_BYTES,
                                              REQUEST_TIMEOUT, validate_json_body)
else:
    from shadow_raw_source_collector import (FetchValidationError, MAX_BYTES,
                                             REQUEST_TIMEOUT, validate_json_body)

LEAGUES={
    "eng-premier":"en.1",
    "eng-championship":"en.2",
    "esp-laliga":"es.1",
    "ita-seriea":"it.1",
    "fra-ligue1":"fr.1",
    "ger-bundesliga":"de.1",
}
BASE="https://raw.githubusercontent.com/openfootball/football.json/master"


def source_urls(year):
    if type(year) is not int or not 2000 <= year <= 2100:
        raise ValueError('INVALID_SEASON')
    season = f'{year}-{str(year + 1)[-2:]}'
    return {league: f'{BASE}/{season}/{code}.json' for league, code in LEAGUES.items()}


_ENDPOINTS = frozenset(url for year in range(2000, 2101)
                       for url in source_urls(year).values())


class _NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _validated_body(raw):
    if type(raw) is not bytes or not raw:
        raise FetchValidationError('EMPTY_OR_INVALID_BODY')
    if len(raw) > MAX_BYTES:
        raise FetchValidationError('SOURCE_TOO_LARGE')
    return validate_json_body(raw, 'OpenFootball')


def fetch(url, opener=None):
    """Keep the global collector's bytes contract on its exact six endpoints.

    This is separate from the controlled OpenLigaDB collector's receipt-returning
    transport. Global snapshots remain unsigned, unverified research inputs.
    """
    if type(url) is not str or url not in _ENDPOINTS:
        raise FetchValidationError('INVALID_SOURCE_URL')
    request = Request(url, method='GET', headers={
        'User-Agent': 'football-king-shadow-research/1.0',
        'Accept': 'application/json,text/plain',
    })
    open_request = build_opener(_NoRedirects()).open if opener is None else opener
    with open_request(request, timeout=REQUEST_TIMEOUT) as response:
        status = getattr(response, 'status', None)
        if type(status) is not int or not 100 <= status <= 599:
            raise FetchValidationError('INVALID_HTTP_STATUS')
        if status != 200:
            raise FetchValidationError('NON_200_RESPONSE', status)
        final_url = response.geturl()
        if type(final_url) is not str or final_url != url:
            raise FetchValidationError('UNEXPECTED_FINAL_URL', status)
        media = response.headers.get('Content-Type', '')
        if (type(media) is not str
                or media.split(';', 1)[0].strip().lower() not in ('application/json', 'text/plain')):
            raise FetchValidationError('NON_JSON_RESPONSE', status)
        raw = response.read(MAX_BYTES + 1)
        _validated_body(raw)
        return raw

def collect(year,outdir,getter=fetch,now=None):
    urls = source_urls(year)
    captured=now or datetime.now(timezone.utc)
    if not isinstance(captured,datetime) or captured.tzinfo is None:
        raise ValueError("INVALID_CAPTURE_TIME")
    out=Path(outdir)
    out.mkdir(parents=True,exist_ok=True)
    manifest={"schema":"football-king-global-raw-research-v1",
              "season_start":year,"captured_utc":captured.astimezone(timezone.utc).isoformat(),
              "status":"HOLD","independently_verified":False,
              "production_recommendations":"DISABLED","eligible_for_model_scoring":False,
              "source_independence":"SINGLE_PUBLISHER","leagues":[]}
    for league,url in urls.items():
        row={"league":league,"provider":"OpenFootball","source_url":url,"status":"ERROR"}
        try:
            raw=getter(url)
            payload=_validated_body(raw)
            name=league+".json"
            (out/name).write_bytes(raw)
            row.update(status="FETCHED_UNVERIFIED",raw_file=name,
                       raw_sha256=hashlib.sha256(raw).hexdigest(),
                       bytes=len(raw),raw_matches=len(payload["matches"]))
        except (OSError,ValueError,TypeError,TimeoutError) as exc:
            row["error_type"]=type(exc).__name__
            status = exc.code if isinstance(exc, HTTPError) else getattr(exc, 'http_status', None)
            if type(status) is int and 100 <= status <= 599:
                row['http_status'] = status
        manifest["leagues"].append(row)
    (out/"manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return manifest

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--year",type=int,required=True)
    p.add_argument("--output-dir",required=True)
    a=p.parse_args()
    result=collect(a.year,a.output_dir)
    print("GLOBAL RESEARCH ONLY",[(x["league"],x["status"]) for x in result["leagues"]])

if __name__=="__main__":
    main()

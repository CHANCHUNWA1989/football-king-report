"""Fixed-endpoint historical source qualification, never a live trading or betting feed."""
import csv
import hashlib
import io
import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

OPENLIGA = "https://api.openligadb.de/getmatchdata/bl1/2020/1"
OPENFOOT = "https://raw.githubusercontent.com/openfootball/football.json/master/2020-21/de.1.json"
ECB = "https://data-api.ecb.europa.eu/service/data/EXR/D.USD.EUR.SP00.A?startPeriod=2020-09-18&endPeriod=2020-09-18&format=csvdata"
ALLOWED = {OPENLIGA, OPENFOOT, ECB}

def acquire(url):
    if url not in ALLOWED:
        raise ValueError("URL not allowlisted")
    from scrapling.fetchers import Fetcher
    page = Fetcher.get(url, follow_redirects=False, timeout=20, retries=1, stealthy_headers=False)
    if page.status != 200 or str(page.url) != url:
        raise ValueError("unexpected HTTP status or URL")
    body = page.body
    if not body or len(body) > 2_000_000:
        raise ValueError("invalid response length")
    return body, {"url":url, "bytes":len(body), "sha256":hashlib.sha256(body).hexdigest(),
                  "captured_utc":datetime.now(timezone.utc).isoformat()}

def score_pair(a,b):
    def valid(v):
        if not isinstance(v,(list,tuple)) or len(v)!=2 or any(type(n) is not int or n<0 for n in v):
            raise ValueError("invalid score")
        return tuple(v)
    return "HISTORICAL_MATCH" if valid(a)==valid(b) else "HOLD_CONFLICT"

def openliga_score(doc):
    rows=[x for x in doc if x["matchID"]==58577 and x["matchDateTimeUTC"]=="2020-09-18T18:30:00Z"
          and x["team1"]["teamId"]==40 and x["team2"]["teamId"]==9 and x["matchIsFinished"] is True]
    if len(rows)!=1:
        raise ValueError("match identity")
    scores=[(x["pointsTeam1"],x["pointsTeam2"]) for x in rows[0]["matchResults"] if x["resultTypeID"]==2]
    if len(scores)!=1:
        raise ValueError("ambiguous final result")
    return scores[0]

def openfoot_score(doc):
    rows=[x for x in doc["matches"] if x["date"]=="2020-09-18"
          and x["team1"] in ("Bayern München","FC Bayern München","Bayern Munich","FC Bayern Munich")
          and x["team2"] in ("Schalke 04","FC Schalke 04")]
    if len(rows)!=1:
        raise ValueError("match identity")
    return rows[0]["score"]["ft"]

def ecb_observation(body):
    rows=list(csv.DictReader(io.StringIO(body.decode("utf-8-sig"))))
    if len(rows)!=1:
        raise ValueError("expected one observation")
    row=rows[0]
    if row["TIME_PERIOD"]!="2020-09-18" or row["CURRENCY"]!="USD" or row["CURRENCY_DENOM"]!="EUR":
        raise ValueError("wrong reference series")
    value=Decimal(row["OBS_VALUE"])
    if not value.is_finite() or value<=0:
        raise ValueError("invalid reference rate")
    return str(value)

def run(domain):
    report={"domain":domain,"research_only":True,"production_recommendations":"DISABLED",
            "live_trading":"DISABLED","status":"HOLD","evidence":[],"historical_only":True,
            "independent_upstream_certified":False}
    try:
        if domain=="football":
            a,ev=acquire(OPENLIGA); report["evidence"].append(ev)
            b,ev=acquire(OPENFOOT); report["evidence"].append(ev)
            report["historical_comparison"]=score_pair(openliga_score(json.loads(a)),openfoot_score(json.loads(b)))
            report["attribution"]=["OpenLigaDB (ODbL): https://www.openligadb.de/en/license","openfootball (CC0): https://github.com/openfootball/football.json"]
        elif domain=="quant":
            a,ev=acquire(ECB); report["evidence"].append(ev)
            report["reference_observation"]=ecb_observation(a)
            report["attribution"]="Source: ECB statistics, EUR/USD daily reference rate, 2020-09-18"
            report["historical_comparison"]="HOLD_SINGLE_PUBLISHER"
        else:
            raise ValueError("unknown domain")
    except Exception as exc:
        report["error_type"]=type(exc).__name__
    return report

if __name__=="__main__":
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument("domain",choices=["football","quant"])
    parser.add_argument("output",type=Path)
    args=parser.parse_args()
    result=run(args.domain)
    args.output.write_text(json.dumps(result,indent=2))
    if "error_type" in result or result.get("historical_comparison")=="HOLD_CONFLICT":
        raise SystemExit(2)

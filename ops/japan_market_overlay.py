"""Surface J1 free API availability, not raw bookmaker quotes, to iPhone."""
import argparse
import json
from datetime import datetime,timezone
from pathlib import Path

from japan_free_market import collect
from japan_free_market_guard import check


def publish(site,source="market/japan_free_status.json",*,now=None):
    now=now or datetime.now(timezone.utc)
    root=Path(site)
    root.mkdir(parents=True,exist_ok=True)
    try:
        path=Path(source)
        if path.stat().st_size>100_000:
            raise ValueError("OVERSIZE_METADATA")
        data=json.loads(path.read_text(encoding="utf-8"))
        stamp=check(data,now=now)
        # The collector never persists sportsbook prices or authorization;
        # results require separate source and point-in-time evidence.
    except (OSError,ValueError,TypeError,KeyError,OverflowError):
        data=collect({},now=now)
        data["source_metadata_unavailable_or_stale"]=True
        data["status"]="HOLD"
    else:
        data["source_metadata_unavailable_or_stale"]=False
    data["public_market_prices_or_recommendations_available"]=False
    data["site_inplay_odds_verified"]=False
    data["production_recommendations"]="DISABLED"
    data["bet_recommendation_count"]=0
    (root/"japan_free_market.json").write_text(
        json.dumps(data,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({
        "status":data["status"],
        "provider_status":[(x["provider"],x["status"])
                           for x in data["j1_free_prematch_sources"]],
        "source_metadata_unavailable_or_stale":data["source_metadata_unavailable_or_stale"],
        "production_recommendations":"DISABLED"},ensure_ascii=False))
    return data


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--site",default="app/site")
    p.add_argument("--source",default="market/japan_free_status.json")
    args=p.parse_args()
    publish(args.site,args.source)

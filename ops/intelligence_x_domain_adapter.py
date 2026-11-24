"""Football-only summary adapter; calls existing P5 in-memory research pipeline."""
from intelligence_x_offline_batch import summarize
from shared.intelligence_x_contract import make_summary


def football_summary(captures, *, reviewed_urls, now_utc):
    result = summarize(captures, reviewed_urls=reviewed_urls, now_utc=now_utc)
    return make_summary("football", total=result["total"],
                        candidates=result["candidates"], rejected=result["rejected"])

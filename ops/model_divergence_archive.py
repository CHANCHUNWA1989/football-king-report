"""Fixed archived shadow replay for the offline mobile report.

The pinned Git blob is a repository observation, not a trusted provider
signature. No external xG projection or common cutoff is present here.
Never construct a pair, a source identity, or a new forecast from this archive.
"""
import gzip
import hashlib
import io
import json
from ops.model_divergence_evidence import _unique, _reject, _finite
from ops.model_divergence_guard import _id
from ops.model_divergence_mobile import render

ARCHIVE_PATH = "shadow/2026/11/28/46130230863-1.json.gz"
ARCHIVE_BLOB = "a249d3cfe7079f78aadf9c31019ce17ca3efeae6"
ARCHIVE_SIZE = 18726
MAX_DECOMPRESSED = 8 * 1024 * 1024


def inspect_archive(data):
    result = dict(schema="football-king-divergence-archive-replay-v1",
                  status="HOLD", reason="INVALID_PINNED_ARCHIVE",
                  archive_blob_match=False, archived_forecast_count=0,
                  qualified_pair_count=0, source_authenticated=False,
                  model_calibrated=False, model_input_derivation_verified=False,
                  external_xg_verified=False, can_recommend_bets=False,
                  production_recommendations="DISABLED")
    try:
        if type(data) is not bytes or len(data) != ARCHIVE_SIZE:
            return result
        blob = b"blob " + str(len(data)).encode("ascii") + b"\0" + data
        if hashlib.sha1(blob).hexdigest() != ARCHIVE_BLOB:
            return result
        with gzip.GzipFile(fileobj=io.BytesIO(data), mode="rb") as stream:
            payload = stream.read(MAX_DECOMPRESSED + 1)
        if len(payload) > MAX_DECOMPRESSED:
            return result
        doc = json.loads(payload.decode("utf-8"), object_pairs_hook=_unique,
                         parse_constant=_reject, parse_float=_finite)
        if (type(doc) is not dict or
                doc.get("schema") != "football-king-uncalibrated-shadow-1" or
                doc.get("status") != "SHADOW_ONLY" or
                doc.get("production_recommendations") != "DISABLED" or
                doc.get("xg_verified") is not False or
                doc.get("model_calibrated") is not False):
            return result
        rows = doc["predictions"]
        if (type(rows) is not list or len(rows) != 49 or
                type(doc.get("predictions_count")) is not int or
                doc["predictions_count"] != len(rows)):
            return result
        ids = [_id(row["event_id"]) for row in rows]
        if len(set(ids)) != len(rows):
            return result
    except (ValueError, TypeError, KeyError, OverflowError, OSError, EOFError, RecursionError):
        return result
    return {**result, "archive_blob_match": True,
            "archived_forecast_count": len(rows),
            "reason": "NO_VERIFIED_EXTERNAL_XG_PAIR"}


def render_archive(data):
    """Read-only standalone HTML candidate; no production site writes."""
    summary = inspect_archive(data)
    html = render(None)
    extra = "<p>封存檔案未通過固定版本檢查。</p>"
    if summary["archive_blob_match"]:
        extra = ("<section><h2>固定歷史封存重播</h2>"
                 "<p>原有研究預測場數：" + str(summary["archived_forecast_count"]) +
                 "</p><p>合格跨來源模型配對：0</p>"
                 "<p>缺少已核實的外部 xG 預測及共同資訊截止時間。</p>"
                 "<p>Git blob 一致不代表來源已認證；不重算原有預測。</p></section>")
    return html.replace("</main>", extra + "</main>", 1)

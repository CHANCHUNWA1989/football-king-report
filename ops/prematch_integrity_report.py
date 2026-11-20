"""Independent evidence inventory and integrity summary."""
from pathlib import Path
from prematch_evidence_chain import verify_evidence_chain


def evidence_integrity_report(directory):
    root = Path(directory)
    result = {"status": "HOLD", "archive_entries": 0,
              "unique_archive_digests": 0, "chain_verified": False,
              "unreferenced_archives": [], "rejection_reasons": [],
              "production_recommendations": "DISABLED"}
    if not root.is_dir() or root.is_symlink():
        result["rejection_reasons"].append("INVALID_ARCHIVE_DIRECTORY")
        return result
    try:
        chain = verify_evidence_chain(directory)
    except (OSError, ValueError, KeyError, TypeError):
        result["rejection_reasons"].append("EVIDENCE_CHAIN_CORRUPTED")
        return result
    referenced = {entry["archive_sha256"] for entry in chain}
    actual = set()
    for item in root.iterdir():
        if item.name.endswith(".json") and len(item.stem) == 64:
            if item.is_symlink():
                result["rejection_reasons"].append("SYMLINK_ARCHIVE_FOUND")
                continue
            actual.add(item.stem)
    result["archive_entries"] = len(chain)
    result["unique_archive_digests"] = len(referenced)
    result["unreferenced_archives"] = sorted(actual - referenced)
    result["chain_verified"] = True
    if actual - referenced:
        result["rejection_reasons"].append("UNREFERENCED_ARCHIVE_FOUND")
    if not chain:
        result["rejection_reasons"].append("EMPTY_EVIDENCE_CHAIN")
    if not result["rejection_reasons"]:
        result["status"] = "RESEARCH_ONLY"
    return result

"""Compatibility entry point for unified V48 full supplied-history replay.

Delegate to the stricter common verifier, including exact historical reference
byte checks and the shared 64 MiB archive budget. No completeness or external
authentication claim. No network or writes.
"""
from .research_private_run_store_v48 import verify_run_with_history
from .research_archive_bound_replay_v47 import MAX_TOTAL_ARCHIVE_BYTES as MAX_ARCHIVE_BYTES

def recheck(run_raw,ledger_raw,primary,secondary,*,include_supplemental):
    audit=verify_run_with_history(run_raw,ledger_raw,primary,secondary,
                                  include_supplemental=include_supplemental)
    return {**audit,"schema":"private-full-replay-v1",
            "supplied_input_roster_reproduced":True,
            "history_mode":"expanded" if include_supplemental else "ledger_only"}

"""Bound free TheSportsDB calls across separate sequential workflow programs.

Request timestamps live only in the runner's temporary directory. This file
is not uploaded to public GitHub Pages, and contains no tokens or payloads.
Respect a conservative subset of the provider's advertised free per-minute
budget. Backoff cannot grant new entitlement or recover a revoked API key.
"""
import json
import math
import os
import tempfile
import time
from pathlib import Path

LIMIT = 25
WINDOW = 62.0
MAX_SLEEP = 180.0


def reserve(ledger, *, clock=None, sleeper=None, limit=LIMIT, window=WINDOW):
    if not ledger:
        return False
    if type(limit) is not int or not 1 <= limit <= 30 or window < 30:
        raise ValueError("UNSAFE_RATE_LIMIT")
    clock = clock or time.time
    sleeper = sleeper or time.sleep
    path = Path(ledger)
    path.parent.mkdir(parents=True, exist_ok=True)
    slept = 0.0
    while True:
        current = float(clock())
        try:
            values = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(values, list) or len(values) > 2000:
                values = []
        except (ValueError, OSError, UnicodeError):
            values = []
        recent = [float(t) for t in values
                  if isinstance(t, (float, int))
                  and math.isfinite(t) and current-window < t <= current+5]
        recent.sort()
        if len(recent) < limit:
            recent.append(current)
            # Atomic persistence: single workflow runner writes sequentially.
            filename = None
            try:
                with tempfile.NamedTemporaryFile(
                        "w", encoding="utf-8", dir=path.parent,
                        prefix=".sportsdb-budget-", delete=False) as handle:
                    filename = handle.name
                    json.dump(recent, handle)
                os.replace(filename, path)
            finally:
                if filename and os.path.isfile(filename):
                    os.unlink(filename)
            return True
        delay = max(0.1, recent[0] + window - current + 0.2)
        if slept + delay > MAX_SLEEP:
            raise TimeoutError("FREE_SOURCE_QUOTA_COOLDOWN_EXCEEDED")
        sleeper(delay)
        slept += delay

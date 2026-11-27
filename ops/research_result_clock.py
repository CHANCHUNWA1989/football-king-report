"""Shared result-availability clock for research-only prequential models."""
from datetime import datetime,timedelta,timezone
from itertools import groupby
import re
from heapq import heappush,heappop

def utc(value):
    if not isinstance(value,datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("explicit timezone-aware clock required")
    return value.astimezone(timezone.utc)

def validate_result_clock(kickoff,available):
    if utc(available)<utc(kickoff)+timedelta(minutes=90):
        raise ValueError("result availability precedes earliest regulation finish")

class ResultClock:
    """Update only on strictly earlier result availability, with stable tie order."""
    def __init__(self):
        self.pending=[]
        self.sequence=0
        self.applied=0

    def schedule(self,available,payload):
        heappush(self.pending,(utc(available),self.sequence,payload))
        self.sequence+=1

    def drain_before(self,cutoff,apply):
        cutoff=utc(cutoff)
        while self.pending and self.pending[0][0]<cutoff:
            _,_,payload=heappop(self.pending)
            apply(payload)
            self.applied+=1

def ordered_batches(records, kickoff, warmup, *, teams=None):
    """Keep whole UTC kickoff groups together; stable IDs never depend on scores."""
    if type(warmup) is not int or not 1<=warmup<len(records):
        raise ValueError("insufficient observations")
    seen=set();previous=None
    for r in records:
        k=utc(kickoff(r))
        if previous is not None and k<previous:
            raise ValueError("chronological order required")
        previous=k
        fid=r.fixture_id
        if fid is not None:
            if not isinstance(fid,str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,159}",fid) or fid in seen:
                raise ValueError("invalid or duplicate fixture ID")
            seen.add(fid)
    ordered=[];effective=warmup;groups=0
    for _,items in groupby(records,key=lambda r:utc(kickoff(r))):
        group=list(items);groups+=1
        if len(group)>1:
            if any(r.fixture_id is None for r in group):
                raise ValueError("simultaneous fixtures require distinct fixed IDs")
            if teams is not None:
                names=[name for r in group for name in teams(r)]
                if len(set(names))!=len(names):
                    raise ValueError("simultaneous team collision")
            group.sort(key=lambda r:r.fixture_id)
        if len(ordered)<warmup<len(ordered)+len(group):
            effective=len(ordered)+len(group)
        ordered.extend(group)
    if effective>=len(ordered):
        raise ValueError("no whole kickoff group after warmup")
    return ordered,effective,groups

def prediction_cutoffs(records,kickoff,*,require_explicit=False):
    """Explicit original forecast times, or labeled synthetic ten-minute lead.

    Mixed clocks and nonmonotonic forecast order are rejected. The existing
    kickoff-sorted API intentionally does not support arbitrary interleaving.
    """
    if type(require_explicit) is not bool:
        raise ValueError("invalid strict forecast clock flag")
    explicit=[r.forecast_utc is not None for r in records]
    if (any(explicit) and not all(explicit)) or (require_explicit and not all(explicit)):
        raise ValueError("missing or mixed explicit forecast times")
    mode="EXPLICIT_RECORDED_FORECAST" if all(explicit) else "SYNTHETIC_FIXED_10_MINUTE_LEAD"
    cutoffs={}
    previous_ko=previous_cut=None
    for r in records:
        ko=utc(kickoff(r))
        cutoff=utc(r.forecast_utc) if mode=="EXPLICIT_RECORDED_FORECAST" else ko-timedelta(minutes=10)
        if cutoff>ko-timedelta(minutes=10):
            raise ValueError("forecast must precede kickoff by at least ten minutes")
        if previous_cut is not None and (cutoff<previous_cut or (ko==previous_ko and cutoff!=previous_cut)):
            raise ValueError("interleaved or inconsistent same-kickoff forecast clocks")
        cutoffs[ko]=cutoff
        previous_ko,previous_cut=ko,cutoff
    return cutoffs,mode

def whole_forecast_warmup(records,kickoff,cutoffs,warmup):
    """Do not split the train/test boundary across an identical forecast clock."""
    if warmup>=len(records):
        raise ValueError("no forecast group after warmup")
    boundary=cutoffs[utc(kickoff(records[warmup-1]))]
    while warmup<len(records) and cutoffs[utc(kickoff(records[warmup]))]==boundary:
        warmup+=1
    if warmup>=len(records):
        raise ValueError("no whole forecast group after warmup")
    return warmup

def event_time_batches(records,kickoff,warmup,*,teams=None):
    """Opt-in replay by explicit forecast time, with atomic warmup groups.

    Input must remain kickoff ordered. All IDs and original forecast clocks
    are required; no synthetic clock can enter this mode.
    """
    if type(warmup) is not int or not 1<=warmup<len(records):
        raise ValueError("insufficient observations")
    # Reuse the existing UTC kickoff, ID and simultaneous-team validations.
    ordered,_,groups=ordered_batches(records,kickoff,1,teams=teams)
    cutoffs={}
    for r in ordered:
        if r.fixture_id is None:
            raise ValueError("event-time replay requires fixed IDs")
        cutoff=utc(r.forecast_utc)
        if cutoff>utc(kickoff(r))-timedelta(minutes=10):
            raise ValueError("forecast must precede kickoff by at least ten minutes")
        cutoffs[r.fixture_id]=cutoff
    ordered.sort(key=lambda r:(cutoffs[r.fixture_id],utc(kickoff(r)),r.fixture_id))
    # Close the warmup prefix over BOTH kickoff groups and forecast groups.
    # Interleaved groups may force the entire roster into warmup: reject that.
    last_ko={utc(kickoff(r)):i for i,r in enumerate(ordered)}
    last_cut={cutoffs[r.fixture_id]:i for i,r in enumerate(ordered)}
    end=warmup
    i=0
    while i<end:
        r=ordered[i]
        end=max(end,last_ko[utc(kickoff(r))]+1,last_cut[cutoffs[r.fixture_id]]+1)
        i+=1
    if end>=len(ordered):
        raise ValueError("no whole event-time group after warmup")
    return ordered,end,groups,cutoffs

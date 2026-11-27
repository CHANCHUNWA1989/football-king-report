"""Shared result-availability clock for research-only prequential models."""
from datetime import datetime,timedelta
from heapq import heappush,heappop

def validate_result_clock(kickoff,available):
    if not isinstance(available,datetime) or available.tzinfo is None or available.utcoffset() is None:
        raise ValueError("explicit timezone-aware result availability required")
    if available<kickoff+timedelta(minutes=90):
        raise ValueError("result availability precedes earliest regulation finish")

class ResultClock:
    """Update only on strictly earlier result availability, with stable tie order."""
    def __init__(self):
        self.pending=[]
        self.sequence=0
        self.applied=0

    def schedule(self,available,payload):
        heappush(self.pending,(available,self.sequence,payload))
        self.sequence+=1

    def drain_before(self,cutoff,apply):
        while self.pending and self.pending[0][0]<cutoff:
            _,_,payload=heappop(self.pending)
            apply(payload)
            self.applied+=1

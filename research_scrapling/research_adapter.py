"""One-step fixture-only integration of polling and atomic cache. No live transport."""
from dataclasses import dataclass
from atomic_poll_cache import AtomicPollCache
from persistent_poll_policy import valid_revision, valid_time
from research_cache import MAX_BYTES


@dataclass(frozen=True)
class FixtureResponse:
    status: int
    revision: str | None = None
    body: bytes | None = None
    retry_after: int = 0


class FixtureTransport:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def request(self, kind):
        self.calls.append(kind)
        if not self._responses:
            return FixtureResponse(503)
        return self._responses.pop(0)


def step(store, scope, now, transport):
    if type(store) is not AtomicPollCache or type(transport) is not FixtureTransport:
        raise ValueError('fixture-only adapter')
    if not valid_time(now):
        raise ValueError('invalid time')
    result = {'status':'HOLD','live_trading':'DISABLED','production_recommendations':'DISABLED',
              'model_input_allowed':False,'fresh_evidence':False,'network_enabled':False,
              'adapter':'FIXTURE_ONLY','action':'BLOCKED'}
    lease = store.reserve(scope, now)
    if lease is None:
        return result
    kind = lease[1]
    r = transport.request(kind)
    if type(r) is FixtureResponse and type(r.status) is int and r.status in (401, 403):
        # Access denial always halts, regardless of unrelated malformed fields.
        r = FixtureResponse(r.status)
    elif type(r) is FixtureResponse and type(r.status) is int and r.status == 429:
        # Never shorten a provider delay. An invalid delay leaves the lease blocked.
        if type(r.retry_after) is not int or not 0 <= r.retry_after <= 10**12:
            raise ValueError('invalid rate-limit delay; lease retained')
        r = FixtureResponse(429, retry_after=r.retry_after)
    elif (type(r) is not FixtureResponse or type(r.status) is not int or not 100 <= r.status <= 599
        or type(r.retry_after) is not int or not 0 <= r.retry_after <= 10**12
        or not valid_revision(r.revision)
        or (r.status == 200 and (r.revision is None or
            (kind == 'payload' and (type(r.body) is not bytes or not 0 < len(r.body) <= MAX_BYTES))
            or (kind == 'revision' and r.body is not None)))):
        r = FixtureResponse(502)
    if kind == 'payload':
        outcome = store.finish_payload(scope, lease, now, r.status, r.revision, r.body, r.retry_after)
    else:
        outcome = store.finish(scope, lease, now, r.status, r.revision, r.retry_after)
    result.update(action=kind, outcome=outcome)
    return result

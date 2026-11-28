"""Single-host simulated polling and cache transaction; no network or activation."""
from persistent_poll_policy import PersistentPollPolicy, MAX_STATE_BYTES, valid_time
from research_cache import digest, MAX_BYTES, TTL


class AtomicPollCache(PersistentPollPolicy):
    @classmethod
    def initialize(cls, path, scopes):
        store = super().initialize(path, scopes)
        with store._connect() as db:
            db.execute('CREATE TABLE payload (scope TEXT PRIMARY KEY, revision TEXT NOT NULL, captured REAL NOT NULL, body BLOB NOT NULL, sha TEXT NOT NULL)')
        return store

    def _operation(self, method, *args):
        scope = args[0]
        db = self._connect()
        try:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT state FROM policy WHERE id=1 AND length(CAST(state AS BLOB))<=?', (MAX_STATE_BYTES,)).fetchone()
            if row is None:
                raise ValueError('missing policy')
            p = self._decode(row[0])
            state = p._scopes[scope]
            row = db.execute('SELECT revision,captured,CASE WHEN length(body)<=? THEN body END,sha FROM payload WHERE scope=?', (MAX_BYTES, scope)).fetchone()
            if (row is None) != (state.cached_revision is None):
                raise ValueError('cache/policy mismatch')
            if row is not None:
                revision, captured, body, sha = row
                if revision != state.cached_revision or not valid_time(captured) or captured > p._clock or type(body) is not bytes or not 0 < len(body) <= MAX_BYTES or sha != digest(scope, revision, captured, body):
                    raise ValueError('invalid cached payload')
            if method == 'finish_payload':
                _, lease, now, status, revision, body, retry_after = args
                if state.lease != lease or lease is None or lease[1] != 'payload':
                    raise ValueError('payload lease required')
                if status == 200 and (type(body) is not bytes or not 0 < len(body) <= MAX_BYTES):
                    raise ValueError('invalid payload')
                result = p.finish(scope, lease, now, status, revision, retry_after)
                if result == 'RESEARCH_CACHE_REVISION_COMMITTED':
                    captured = float(now)
                    db.execute('INSERT INTO payload VALUES (?,?,?,?,?) ON CONFLICT(scope) DO UPDATE SET revision=excluded.revision,captured=excluded.captured,body=excluded.body,sha=excluded.sha', (scope, revision, captured, body, digest(scope, revision, captured, body)))
            elif method == 'get':
                _, now = args
                p._time(now)
                result = {'status':'HOLD','live_trading':'DISABLED','production_recommendations':'DISABLED','model_input_allowed':False,'fresh_evidence':False,'body':None}
                if row is not None and now - row[1] <= TTL and state.pending_revision is None and state.lease is None and not state.halted and state.failures == 0:
                    result['body'] = row[2]
            else:
                if method == 'finish' and state.lease is not None and state.lease[1] == 'payload':
                    raise ValueError('use finish_payload')
                result = getattr(p, method)(*args)
            encoded = self._encode(p)
            self._decode(encoded)
            db.execute('UPDATE policy SET state=? WHERE id=1', (encoded,))
            db.commit()
            return result
        finally:
            db.close()

    def finish_payload(self, scope, lease, now, status, revision=None, body=None, retry_after=0):
        return self._operation('finish_payload', scope, lease, now, status, revision, body, retry_after)

    def get(self, scope, now):
        return self._operation('get', scope, now)

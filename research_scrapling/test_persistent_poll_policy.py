from contextlib import closing
import multiprocessing
import json
import sqlite3
import unittest
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from persistent_poll_policy import PersistentPollPolicy


def reserve_once(path):
    return PersistentPollPolicy(path).reserve("a", 100)


class PersistentTests(unittest.TestCase):
    def setUp(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / "poll.db"
        self.p = PersistentPollPolicy.initialize(self.path, ["a", "b"])

    def reopen(self):
        return PersistentPollPolicy(self.path)

    def test_cross_process_single_lease(self):
        with ProcessPoolExecutor(max_workers=4, mp_context=multiprocessing.get_context("spawn")) as pool:
            results = list(pool.map(reserve_once, [self.path] * 32))
        self.assertEqual(sum(x is not None for x in results), 1)
        self.assertTrue(self.reopen().snapshot("a")["in_flight"])

    def test_abandoned_lease_stays_blocked(self):
        self.p.reserve("a", 100)
        self.assertIsNone(self.reopen().reserve("a", 100000))

    def test_backoff_survives_restart(self):
        lease = self.p.reserve("a", 100)
        self.p.finish("a", lease, 101, 429, retry_after=7200)
        self.assertIsNone(self.reopen().reserve("a", 7300))
        self.assertIsNotNone(self.reopen().reserve("a", 7301))

    def test_halt_survives_restart(self):
        lease = self.p.reserve("a", 100)
        self.p.finish("a", lease, 101, 403)
        self.assertIsNone(self.reopen().reserve("a", 999999))

    def test_revision_survives_restart(self):
        lease = self.p.reserve("a", 100)
        self.p.finish("a", lease, 101, 200, "v1")
        p = self.reopen()
        lease = p.reserve("a", 161)
        self.assertEqual(lease[1], "payload")
        p.finish("a", lease, 162, 200, "v1")
        self.assertEqual(self.reopen().snapshot("a")["cached_revision"], "v1")

    def test_rollback_clock(self):
        self.p.reserve("a", 100)
        with self.assertRaises(ValueError):
            self.reopen().reserve("b", 99)

    def test_missing_db_not_recreated(self):
        self.path.unlink()
        with self.assertRaises(sqlite3.Error):
            self.reopen().reserve("a", 100)
        self.assertFalse(self.path.exists())

    def test_existing_db_not_reset(self):
        self.p.reserve("a", 100)
        with self.assertRaises(FileExistsError):
            PersistentPollPolicy.initialize(self.path, ["a"])
        self.assertTrue(self.reopen().snapshot("a")["in_flight"])

    def corrupt(self, mutate):
        with closing(sqlite3.connect(self.path)) as db, db:
            raw = db.execute("SELECT state FROM policy WHERE id=1").fetchone()[0]
            doc = json.loads(raw)
            mutate(doc)
            db.execute("UPDATE policy SET state=? WHERE id=1", (json.dumps(doc),))
        with self.assertRaises(ValueError):
            self.reopen().reserve("a", 100)

    def test_bad_halt_type(self):
        self.corrupt(lambda d: d["scopes"]["a"].update(halted=0))

    def test_nan_due(self):
        self.corrupt(lambda d: d["scopes"]["a"].update(due=float("nan")))

    def test_negative_due(self):
        self.corrupt(lambda d: d["scopes"]["a"].update(due=-1))

    def test_bad_failure_count(self):
        self.corrupt(lambda d: d["scopes"]["a"].update(failures=-100))

    def test_bad_lease(self):
        self.corrupt(lambda d: d["scopes"]["a"].update(lease=[1,"payload"]))

    def test_invalid_schema_bool(self):
        self.corrupt(lambda d: d.update(schema=True))

    def test_duplicate_state_key(self):
        with closing(sqlite3.connect(self.path)) as db, db:
            raw = db.execute("SELECT state FROM policy WHERE id=1").fetchone()[0]
            db.execute("UPDATE policy SET state=? WHERE id=1", (raw[:-1]+',"schema":1}',))
        with self.assertRaises(ValueError):
            self.reopen().reserve("a", 100)

    def test_oversized_state(self):
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("UPDATE policy SET state=? WHERE id=1", ("x"*1000001,))
        with self.assertRaises(ValueError):
            self.reopen().reserve("a", 100)

    def test_invalid_next_state_rolls_back(self):
        lease = self.p.reserve("a", 100)
        with self.assertRaises(ValueError):
            self.p.finish("a", lease, 101, 429, retry_after=1e16)
        self.assertTrue(self.reopen().snapshot("a")["in_flight"])

    def test_safety_flags(self):
        s = self.reopen().snapshot("a")
        self.assertEqual((s["status"], s["live_trading"], s["production_recommendations"]), ("HOLD", "DISABLED", "DISABLED"))
        self.assertFalse(s["model_input_allowed"])
        self.assertFalse(s["network_enabled"])


if __name__ == "__main__":
    unittest.main(verbosity=2)

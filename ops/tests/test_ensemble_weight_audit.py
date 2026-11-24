"""Synthetic, offline tests; no authenticated forecast or result evidence."""
import copy
import unittest
from datetime import datetime, timedelta, timezone
from ops.ensemble_weight_audit import audit

START = datetime(2026, 1, 1, tzinfo=timezone.utc)


def rows():
    out = []
    for i in range(140):
        kick = START + timedelta(days=i)
        y = i % 3
        strong = [.1, .1, .1]
        strong[y] = .8
        out.append(dict(event_id=f"synthetic-{i}", kickoff_utc=kick.isoformat(),
                        forecast_utc=(kick-timedelta(hours=2)).isoformat(),
                        settled_utc=(kick+timedelta(hours=3)).isoformat(),
                        market_utc=(kick-timedelta(hours=3)).isoformat(),
                        y=y, models={"market": [1/3]*3, "poisson": strong,
                                     "dc": [.4, .3, .3]},
                        production_recommendations="DISABLED"))
    return out


class EnsembleWeightAuditTests(unittest.TestCase):
    def test_fit_uses_only_training_and_never_promotes(self):
        result = audit(rows())
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["weights"]["poisson"], 1.0)
        self.assertEqual(result["validation_count"], 35)
        self.assertLess(result["validation"]["ensemble"]["log_loss"],
                        result["validation"]["market"]["log_loss"])
        self.assertFalse(result["formal_forward_eligible"])
        self.assertEqual(result["production_recommendations"], "DISABLED")

    def test_validation_outcomes_do_not_change_weights(self):
        src = rows()
        a = audit(src)
        for row in src[-35:]:
            row["y"] = (row["y"]+1)%3
        b = audit(src)
        self.assertEqual(a["weights"], b["weights"])
        self.assertFalse(b["both_scores_better_than_market"])
        self.assertEqual(b["status"], "HOLD")

    def test_incomplete_model_set_rejects_whole_cohort(self):
        src = rows()
        del src[-1]["models"]["dc"]
        self.assertEqual(audit(src)["reason"], "MODEL_SET_MISMATCH")

    def test_duplicate_and_future_market_rejected(self):
        src = rows()
        self.assertEqual(audit(src+[copy.deepcopy(src[0])])["reason"], "DUPLICATE_EVENT")
        src[-1]["market_utc"] = src[-1]["kickoff_utc"]
        self.assertEqual(audit(src)["reason"], "INVALID_CHRONOLOGY")

    def test_late_training_receipts_not_admitted(self):
        src = rows()
        for row in src[:40]:
            row["settled_utc"] = src[110]["settled_utc"]
        self.assertEqual(audit(src)["reason"], "INSUFFICIENT_PRIOR_SETTLEMENTS")

    def test_equal_kickoff_group_not_split_and_order_invariant(self):
        src = rows()
        for key in ("kickoff_utc", "forecast_utc", "settled_utc", "market_utc"):
            src[104][key] = src[105][key]
        a = audit(src)
        self.assertEqual(a["validation_count"], 36)
        self.assertEqual(a, audit(list(reversed(src))))

    def test_invalid_probabilities_and_early_result_rejected(self):
        src = rows()
        src[0]["models"]["dc"] = [True, 0, 0]
        self.assertEqual(audit(src)["reason"], "INVALID_PROBABILITIES")
        src = rows()
        src[0]["settled_utc"] = src[0]["kickoff_utc"]
        self.assertEqual(audit(src)["reason"], "INVALID_CHRONOLOGY")

    def test_reserved_model_name_is_rejected(self):
        src = rows()
        for row in src:
            row["models"]["ensemble"] = row["models"].pop("dc")
        self.assertEqual(audit(src)["reason"], "INVALID_MODEL_SET")

    def test_no_data_or_insufficient_data_does_not_fit(self):
        for src in ([], rows()[:105]):
            result = audit(src)
            self.assertEqual(result["status"], "HOLD")
            self.assertNotIn("weights", result)

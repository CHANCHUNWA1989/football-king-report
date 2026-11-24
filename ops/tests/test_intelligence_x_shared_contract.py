import unittest
from shared.intelligence_x_contract import make_summary, validate_summary


class IntelligenceXContractTests(unittest.TestCase):
    def test_round_trip(self):
        for domain in ("football", "finance"):
            row = make_summary(domain, total=2, candidates=1, rejected=1)
            self.assertEqual(validate_summary(row, expected_domain=domain), row)

    def test_cross_domain_rejected(self):
        row = make_summary("football", total=0, candidates=0, rejected=0)
        with self.assertRaises(ValueError):
            validate_summary(row, expected_domain="finance")

    def test_no_extra_fields(self):
        row = make_summary("finance", total=0, candidates=0, rejected=0)
        for extra in ("order", "price", "raw", "token", "signal", "odds"):
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                validate_summary(dict(row, **{extra: "synthetic"}), expected_domain="finance")

    def test_flags_cannot_be_promoted(self):
        row = make_summary("finance", total=1, candidates=1, rejected=0)
        for field, bad in (("status", "PASS"), ("source_authorized", True),
                           ("independently_verified", True), ("eligible_for_model_scoring", True),
                           ("production_recommendations", "ENABLED"), ("live_execution_allowed", True),
                           ("external_calls", False), ("external_calls", 1)):
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_summary(dict(row, **{field: bad}), expected_domain="finance")

    def test_invalid_counts(self):
        for total, good, bad in ((True, 1, 0), (33, 33, 0), (2, 1, 0), (-1, 0, 0), (1, 0.5, 0.5)):
            with self.subTest(total=total), self.assertRaises(ValueError):
                make_summary("football", total=total, candidates=good, rejected=bad)

    def test_missing_fields(self):
        row = make_summary("football", total=0, candidates=0, rejected=0)
        for field in row:
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_summary({k: v for k, v in row.items() if k != field},
                                 expected_domain="football")


if __name__ == "__main__":
    unittest.main()

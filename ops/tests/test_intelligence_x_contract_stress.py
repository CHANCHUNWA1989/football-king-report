import random
import unittest
from shared.intelligence_x_contract import make_summary, validate_summary


class IntelligenceXStressTests(unittest.TestCase):
    def test_exhaustive_counts_and_domain_isolation(self):
        for domain in ("football", "finance"):
            other = "finance" if domain == "football" else "football"
            for total in range(33):
                for count in range(total + 1):
                    row = make_summary(domain, total=total, candidates=count,
                                       rejected=total-count)
                    self.assertEqual(validate_summary(row, expected_domain=domain), row)
                    with self.assertRaises(ValueError):
                        validate_summary(row, expected_domain=other)

    def test_10000_mutated_summaries(self):
        rng = random.Random(59152)
        mutations = [("status", "PASS"), ("live_execution_allowed", True),
                     ("source_authorized", True), ("independently_verified", True),
                     ("eligible_for_model_scoring", True),
                     ("production_recommendations", "ENABLED"),
                     ("external_calls", False), ("order", "BUY"),
                     ("raw", "SYNTHETIC"), ("total", 33)]
        for _ in range(10000):
            total = rng.randrange(33)
            count = rng.randrange(total + 1)
            domain = rng.choice(["football", "finance"])
            row = make_summary(domain, total=total, candidates=count,
                               rejected=total-count)
            key, value = rng.choice(mutations)
            row[key] = value
            with self.assertRaises(ValueError):
                validate_summary(row, expected_domain=domain)


if __name__ == "__main__":
    unittest.main()

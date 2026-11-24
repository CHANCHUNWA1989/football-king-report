# PR 581 verification and exploratory archive audit (2026-11-24)

Verified head before this change: 994cffed446ba2dd1c8fb5ceaaf8d4a4d564b3c2.
- Five completed PR workflows: 45367628844, 45367628102, 45367628755,
  45367629461, 45367628380 (all success).
- Job 138353385800: 2351 ops tests OK including all 12 postmortem tests,
  117 legacy tests OK. Cross-engine test exercises 5248 combinations.
- Job 138353386329: 1500 synthetic corrupted payloads rejected,
  24 concurrent jobs, no network requests. Not match evidence.
- Job 138353382027: 10 independent offline 1X2 tests OK.

Archive: evidence/settled.json at the pinned head above, checked
2026-11-21T02:56:04.039201+00:00. All 105 unique rows have forecast
and market timestamps before kickoff and valid probabilities; zero
independently verified outcomes, zero red-card or in-play fields.
No eligible authenticated prospective red-card cohort.

Descriptive scores (natural-log loss; multiclass sum Brier; first argmax):
- 105 rows: model 1.040892 / 0.627789 / 50 correct;
  derived market consensus 0.970627 / 0.576674 / 62 correct.
- 92 rows with stored B and registered formula matching within 1e-6:
  original 1.064725; B 1.055833; paired B minus original -0.008892.
- 66 rows with stored C and registered formula matching within 2e-6:
  original 1.062064; C 0.982713; consensus 0.969255;
  paired C minus original -0.079351.
- Exploratory 5000-replicate kickoff-week cluster bootstrap, seed 20261124,
  LCG state=(1664525*state+1013904223) mod 2^32, draw one group per
  observed week with replacement, pooled per-fixture log-loss difference,
  sorted replicate indices 124 and 4874: B [-0.034293,0.004155] (6 weeks);
  C [-0.122867,-0.043576] (5 weeks). Week key floor((UTC Unix milliseconds
  + 3*86400000)/(7*86400000)); groups in original archive order.
  These are descriptive and unstable with so few clusters, not
  independently certified confidence intervals. No new model fitted.

Review defect: the earlier max(pre-rate)*opponent-factor gate could
reject legal scenarios when the higher pre-rate belongs to the
disadvantaged side. This change checks the actual adjusted rates instead,
separates end-of-regulation from overflow, and adds 648 hypothetical
scenario checks, source and promotion guards, and swap symmetry.
The new tests require their own CI evidence; the prior CI does not cover them.

HOLD / DISABLED. No confirmed EV, calibration, true prospective red-card
validation, or improvement against market. No production integration.

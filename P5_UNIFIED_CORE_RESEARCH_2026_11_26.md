# P5 unified core research assembly (2026-11-26)

Pinned V9 integration parent: `04d8cf0563fbf28da8f61c2b78af2825fe31ccb7` (#649). Exact code and test blobs from the five source heads, not a merge of their histories:

| Stage | PR | Head |
|---|---|---|
| P0 | #528 | 29a8884460942b8708dd5bd407a25d08a9ab67bc |
| P1 | #634 | c22ada34fcc67c302f876f8840bfed2ac9f9b8ae |
| P2 | #650 | 9ec2e23c7667288c44ca5b6c1a29e4c3192b6cf5 |
| P3 | #639 | 24fb907a67273bbbc08b034607fa520505588fe3 |
| P4 | #640 | cb1683a975e46e20c9721c917e15b8b933c2cd63 |

Eight replaced files matched the source pre-upgrade blobs byte-for-byte; two new availability files were absent. New cross-module synthetic tests check all safety flags and reject retrospective or synthetic evidence in incompatible module inputs. No automatic chaining of live, injury, or historical probabilities; no production writes, sealed forecast changes, new API calls or workflow changes.

P4 exact-head historical workflow 45747054449: 236 development, 383 assessment cases; development-only selected exclude_lightgbm, 188/383 correct, log loss 1.0381658028, Brier .6230947765. Prior 8-grid workflow 45629656264: 184/383, LL 1.0365191740, Brier .6217881886. The new grid passes its comparator gate but worsens both proper scores vs the older selected grid. Retain both candidates, do not promote. Previously inspected assessment, no independent result or market proof.

Acceptance: exact-head core CI, compileall, ops unittest discovery, full regression/stress, dependency and independent review. Separate P3/P4 specialist workflows are not imported or rerun by this assembly; rerun them against the integrated tree before release acceptance. Source-specific real-world evidence, genuine forward records and integrated performance remain unverified. HOLD/DISABLED.

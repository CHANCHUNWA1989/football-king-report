# Segmented D pilot research adapter

Stacked on PR #787 exact head 362983c52ea3a454feeef736935c51e35e334166. The existing 64-proof/192 MB
production research bounds and CLI are unchanged. This opt-in in-process
adapter experiments with up to 256 supplied capture proofs, 16 per segment,
and the same global 192 MB decoded payload ceiling. Those count limits are
engineering proposals, not a benchmark or authorization to increase traffic.

Global result-blind manifest preflight binds unique run/attempt identities,
metadata and exact bytes. Forecast cohort selection remains before reading
results. Each segment uses the original verifier, fresh signature verification,
exact bytes before and after, and a checked one-to-one reference list. All
identity/score sets, malformed flags and final observations are merged before
scoring; conflicting later evidence quarantines the case. A missing or failed
segment yields no partial scores. Final full byte recheck remains in the
original audit. No prior audit JSON enters as a trust input.

No changes to the archive preparer, scheduled workflow, provider quota or
model weights. The current preparer still cannot construct >64 proof manifests;
integration needs a separate bounded design and real 33+ proof runtime and
resource benchmarks. The extra global preflight costs additional reads.
No source authenticity, market edge, remote catalogue completeness,
independent outcomes or calibration certified. HOLD/DISABLED.

Nine tests reuse the existing real-format fixture builder with mocked
signature CLI, including 65 distinct proofs and cross-segment conflicting FT.
They are not real signature validation or an execution benchmark.

# V12 TabPFN local foundation challenger (HOLD/DISABLED)

This is an optional offline research benchmark, not a production expert. No checkpoint is included, downloaded or invoked by default CI. No user license acceptance, token or purchase is performed by this change. Review the applicable weight license and obtain permission for the intended usage: https://huggingface.co/Prior-Labs/tabpfn_3_5 and https://github.com/PriorLabs/TabPFN . Do not use the research result as production authorization. Preserve checkpoint filename and obtain a trusted SHA-256 from the authorized source independently; a caller-supplied hash is integrity checking, not authentication.

Use a separate disposable environment, install the existing research dependencies plus `tabpfn==10.2.0` after reviewing the dependency resolution, then provision the authorized checkpoint and pinned openfootball archive files described by `research/v8_history_manifest.json`. Dependencies and checkpoint compatibility have not yet been validated together. Disable network at the operating system/container boundary before running; offline environment variables alone are not a sandbox. CPU is bounded to 5,000 rows per partition; GPU optional. Never place tokens or weights in Git.

Example after license review, provisioning and environment isolation:

```sh
python -m ops.v9_tabpfn_research --input-dir /path/to/pinned/archive --manifest research/v8_history_manifest.json --checkpoint /path/to/tabpfn-v3.5-fast-20260909.safetensors --sha256 TRUSTED_SHA256 --license-reviewed --device cpu --output /tmp/v12-report.json
```

Training/context 2022-23 and 2023-24; calibration 2024-25; assessment 2025-26. Nineteen features (12 previous-day archive statistics + seven league indicators). Four existing ML baselines on identical rows; calibration alone chooses baseline and temperature/weight grid including zero foundation weight. This benchmark is not a direct V11.3 comparison and does not establish a tenth deployed expert. Unknown checkpoint pretraining overlap and previously inspected historical assessment prevent independent validation claims. Test doubles do not demonstrate model inference. Actual checkpoint run, resource benchmark, paired V11.3 comparison and prospective source verification are required before further consideration. No market, xG, executable odds, verified sample credit or automatic promotion.

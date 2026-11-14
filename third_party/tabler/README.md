# Scoped Tabler UI pattern reuse

- Upstream: https://github.com/tabler/tabler
- Pinned commit: `7ecb81656f5dead041668a0bd0296b12fb2c074f`
- Source components: `shared/ui/Progress.astro` and `core/scss/ui/_cards.scss`.
- Licence: MIT, Copyright 2018-2026 The Tabler Authors; the complete notice is retained in `LICENSE`.
- Adapted location: `ops/build_zh_hant_dashboard.py` case replay section.

The responsive metric-card layout and labelled progress-bar pattern are adapted to a dependency-free static report. Only local HTML/CSS is used; no Tabler package, external asset, script, font, or network request is added. Progress values are displayed only after validating the controlled replay schema and its HOLD/DISABLED and non-certification flags. The report calls these derived research probabilities; they are not sealed forecasts, executable odds, calibrated probabilities, independently verified outcomes, or EV.

# Provenance

- **Code and Markdown documents** in this repository were authored by William N. King and are licensed under the Apache License 2.0 (see `LICENSE`, added 2026-09-07 after an external audit found the repository carried no license).
- **`ats_application_tracking_system_auditor.pdf`** and **`ats_hidden_bias_counter_analysis.pdf`** have no recorded origin in this repository. Until their authorship is confirmed and recorded here, treat them as not licensed for redistribution and exclude them from any packaged release.
- **Third-party dependencies** (`numpy`, `scipy`, `scikit-learn`, declared in `requirements.txt`) are not vendored.

Audit context: the "Generates legal evidence" claim in `README.md` refers to `ats_counter_system.py`, which has no automated test as of 2026-09-07. Only `gov4_kernel.py` is covered by `test_gov4_kernel.py`.

# ATS

Hiring bias-detection **demonstration** for ≡TACK. It shows domain-independent governance ideas on applicant-tracking decisions. It is not a compliance tool, not legal advice, and not on the orchestrator path (observe-perceive's) or any other decision path.

Status: demo. Flat Python modules, not a package. Last checked 2026-11-19 at commit `18cc2cb`. This repo's history was rewritten after the 2026-11-15 review, which used commit `770aab9` (its twin is `bfcd03b`). License: Apache-2.0 (`LICENSE`).

## Role Within ≡TACK

- **What it is.** A specialized inlet and domain demo: governance ideas (bias auditing, hash-chained audit trail, policy kernel) shown on hiring decisions.
- **What it owns.** Its own bias measurements (geographic, employment-volatility, name-proxy, remote-work gaps), its own audit trail, and a vendored copy of a policy kernel (`gov4_kernel.py`).
- **What it contributes.** A worked example of the same governance ideas in a second domain. Parallel in concept to `interconnected_delta` fairness. No import in either direction.
- **What it does not own.** Enforcement, authorization, authentication, or any real hiring decision. HALT does not pause a real ATS. It does not share a ledger with sentinel_os.
- **Depends on.** numpy, scipy, scikit-learn. Optionally CNS v4.0.0 (`requirements-cns.txt`) for the binding connector only.
- **Depended on by.** UNKNOWN. No consumer was found or inspected.
- **Verified versus declared.** The CNS connector is optional and tested in CI with CNS installed; nothing else here imports CNS (`test_ats_cns_independence.py` checks this with CNS blocked). The ≡TACK `STACK.md` names observe-perceive as a hub; no import links them (INSPECTED). Kafka, Slack and PagerDuty appear in operations docs with zero code.
- **Governance and control design.** None of its output is authoritative. The connector only binds a finding to a CNS verdict issued elsewhere. It maps no ATS finding to a CNS outcome and invents no verdict semantics.

## Scope and exclusions

Does not sit inside Greenhouse, Lever or Workday. Does not produce court-admissible work product (`LegalEvidencePackager` emits JSON). Does not implement the four-fifths (80%) rule: a search of the code found no such ratio (INSPECTED 2026-11-15). Makes no claim of EEOC, NYC Local Law 144 or any other legal compliance.

## Core implemented capabilities

IMPLEMENTED (tests passed 2026-11-15; this is not an audit of correctness):

| File | Role |
|---|---|
| `ats_counter_system.py` | Batch audit: geographic, employment-volatility, name-proxy; falsified-audit catches |
| `ats_governor_fixed.py` | Streaming governor, `CryptoAuditTrail`, demo `ATS` class |
| `ats_statistics.py` | chi-squared and Fisher exact tests |
| `ats_embeddings.py` | TF-IDF default; abstract `embed` raises `NotImplementedError` |
| `ats_governance_kernel_bridge.py` | `CandidateSignals` to vendored GOV4 `NormalizedEvent` |
| `gov4_kernel.py` | In-tree EventStore and PolicyVM; `Verdict` is ALLOW, THROTTLE, ISOLATE or HALT |
| `ats_gsa_core.py` | Scoring core; thresholds `approve_threshold=0.75`, `reject_floor=0.20` |
| `ats_oscillation_detector.py` | Reports oscillation. Non-authoritative. |
| `ats_cns_connector.py` | Optional CNS binding (below) |

Name-proxy detection and `SafeguardVerifier.verify_independent_validation` did not carry into `ats_governor_fixed.py`. See `ats_seam_inventory.md`.

## Domain warning: automated decisions

The demo code makes decisions about example candidates. `ats_governor_fixed.py` sets "APPROVED" or "REJECTED" from a keyword score (`keyword_score >= 20`). `ats_gsa_core.py` returns a `HIRED`, `HUMAN_REVIEW` or `REJECTED` status. Do not point this at real applicants. Bias findings size the rejection-rate gap as an absolute number (`abs(...)` in `_gap` and in `rate_gap`), and each result now also says which group was rejected more often (`disadvantaged`, and `higher_rejection_cohort` on the batch event). A significant gap is called a penalty, and its safeguard proposed, only when the tested group was the one rejected more. When the other group was, the finding is reported under a neutral name such as `remote_favoured_over_local`, with that other group's rejected candidates as the affected ones (EXECUTED 2026-11-20).

## Architecture

```text
ATS demos  --copy of GOV4-->  gov4_kernel.py (in-tree)
           no link to sentinel_os, interconnected_delta, observe-perceive
```

Multiple independent hash chains start from different `GENESIS` values. They are recomputed locally. They are not a shared custody plane.

## Interfaces

- `BiasSignature{bias_type, affected_candidates, correlation_strength, hidden_factor, evidence_confidence, p_value}`; `CandidateSignals`; `NormalizedEvent`; audit events with `previous_hash`, `hash`, `hmac`.
- Consumed: nothing external by default.

### Optional CNS connection

ATS does not need CNS. Nothing imports it, no main requirements file lists it, and `test_ats_cns_independence.py` checks this with CNS blocked. `ats_cns_connector.py` is the one place that knows CNS exists, and it imports `cns.gate` only when a function that needs it is called. Install with `pip install -r requirements-cns.txt`. Without CNS those calls raise `CnsNotInstalled` and nothing else changes.

It binds the counter audit (`CounterATS.audit_adversarial_system`) and the evidence package (`ATSGovernorProduction.run_full_audit`). For each there is a `*_content` (deterministic), a `*_digest` (`cns.gate.subject_digest` of it) and an `*_binds(result, output)` that is true only for a `cns.gate.GateResult` issued against exactly that output. The content never holds applicant names, emails or resume text, and volatile fields are left out. Binding only: this is not a gate.

## Security and trust

- No default HMAC key, since commit `18cc2cb` (2026-11-16). `CryptoAuditTrail` (and so `ATS` and `ATSGovernorProduction`) raises `ValueError` unless a `signing_key` is passed or `AUDIT_KEY` is set, and refuses a blank key and the key this repo once published as its default. It also needs a log path (`log_file` or `ATS_AUDIT_LOG_PATH`); the bridge's write-ahead log needs `wal_path` or `ATS_WAL_PATH` and no longer defaults to a shared `/tmp` file. EXECUTED 2026-11-19 for the key and log-path refusals. Before that commit the default key was used and the HMAC proved nothing.
- An HMAC with a shared key is integrity checking. It is not authentication of who wrote an entry.
- No threat model is established as tested. `ats_threat_model.md` exists; its claims are not verified here (UNKNOWN).

## Install and quick start

```
pip install -r requirements.txt pytest
python -m pytest -q
```

Optional embedding backends are in `requirements-optional.txt`. Demo audit: `python3 ats_counter_system.py`.

## Testing and verification

EXECUTED 2026-11-15 (Python 3.13): 123 passed, 1 skipped. The skip is the CNS connector test, because `cns` was not installed in this run. On 2026-11-19 at `18cc2cb` (Python 3.12, the same setup): 169 passed, 1 skipped; the new tests cover the audit key and the log locations. `python3 ats_counter_system.py` runs without a key, because that demo does not write an audit trail. CI (`.github/workflows/tests.yml`) runs pytest on 3.11 and 3.12, ruff as a lint gate, and a second job with CNS installed. I did not run ruff or the CNS job. `ats_counter_system.py` has tests in `test_ats_counter_system.py`; `PROVENANCE.md` says otherwise as of 2026-09-07 and is updated.

## Known limitations and outstanding work

- `_is_vowel_heavy` is a crude check (vowel ratio above 0.4).
- `MIN_COHORT_N=30`; an older n=1 bug is documented in the seam inventory.
- Two PDF files with no recorded origin were removed from this repo, history included, after the 2026-11-15 review. `PROVENANCE.md` and `ats_seam_inventory.md` still name them.
- Several guides still claim production readiness, EEOC-format evidence and a four-fifths computation. Those claims are unsupported. Each now carries a banner; the original text is unchanged pending the owner's decision to rewrite or withdraw.
- Three more documents carry legal-style wording and have no banner (INSPECTED 2026-11-15): `ats_governor_operations_toolkit.md` ("Admissible in legal proceedings"), `ats_governance_kernel_bridge_reference.md` ("litigation-ready"), and `ats_threat_model.md` (cites employment statutes and EEOC guidance). The same caution applies to them: nothing in this repo establishes legal admissibility or compliance.
- Not commercially relevant as a product.

## Documentation

- Start at `ats_seam_inventory.md` (observed versus documented versus no evidence), not the package list.
- `ats_governor_package.md`, `ats_governor_integration_guide.md`, `ats_bias_decision_framework.md`, `ats_governor_operations_toolkit.md`, `ats_threat_model.md`, `ats_red_team_analysis.md`, `ats_governance_kernel_bridge_reference.md`, `ATS_OSCILLATION_DETECTION.md`
- `PROVENANCE.md`, `STACK.md`, `NOTICE`

Maintainer: William N. King.

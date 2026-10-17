# ATS

Hiring **bias-detection demonstration**. Domain-independent governance *ideas* shown on applicant-tracking decisions. Parallel conceptually to [`interconnected_delta`](https://github.com/wking53214/interconnected_delta) fairness — **no import**.

## 1. Pipeline Position & Role

**SPECIALIZED INLET / DOMAIN DEMO.** Not on the live decision path. Not a cassette in sentinel_os.

## 2. Full System Scope & Architectural Depth

Flat modules (not a package):

| File | Role |
|---|---|
| `ats_counter_system.py` | Batch audit: geographic / employment-volatility / name-proxy; falsified-audit catches |
| `ats_governor_fixed.py` | Streaming governor + `CryptoAuditTrail` |
| `ats_statistics.py` | chi² / Fisher |
| `ats_embeddings.py` | TF-IDF default; ABC `embed` raises `NotImplementedError` |
| `ats_governance_kernel_bridge.py` | `CandidateSignals` → vendored GOV4 `NormalizedEvent` |
| `gov4_kernel.py` | In-tree EventStore/PolicyVM; `Verdict{ALLOW,THROTTLE,ISOLATE,HALT}` |
| `ats_gsa_core.py` | `approve_threshold=0.75`, `reject_floor=0.20` |
| `ats_oscillation_detector.py` | Non-authoritative |

Honest map: `ats_seam_inventory.md` (`[OBSERVED]` vs `[DOCUMENTED]` vs `[NO EVIDENCE]`). Name-proxy and `SafeguardVerifier.verify_independent_validation` **did not** carry into `ats_governor_fixed`.

## 3. What It Does NOT Do / Non-Goals

- Does not sit inside Greenhouse/Lever/Workday.
- Does not produce court-admissible work product (`LegalEvidencePackager` emits JSON).
- Does not share a ledger with sentinel_os.
- HALT does not pause a real ATS.

## 4. Brutally Honest Current Status & Gaps

| Gap | Detail |
|---|---|
| Default HMAC | `CryptoAuditTrail.signing_key` defaults to **`"default_key_change_me"`**. Theater unless `AUDIT_KEY` set. |
| Marketing vs code | README historically claimed `<5% FPR`, `85%+`, litigation-ready. Treat as **working demos with documented gaps**. |
| Kafka/Slack/PagerDuty | Claimed in ops docs; **zero code**. |
| `_is_vowel_heavy` | Crude >0.4 vowel ratio. |
| `MIN_COHORT_N=30` | Corrected; older n=1 bug documented. |
| PDFs | No recorded origin (`PROVENANCE.md`). |
| Commercial | **NOT COMMERCIALLY RELEVANT** as a product. |

numpy/scipy/sklearn required. Optional ST/OpenAI/Voyage lazy. CI pytest+ruff.

## 5. Core Invariants & Guarantees

Statistical tests exist. Oscillation **reports**, does not halt. Multiple independent hash chains (`GENESIS` variants) — recompute locally, not a shared custody plane. Fail-open on missing HMAC key.

## 6. Inputs, Outputs & Type Contracts

`BiasSignature{bias_type, affected_candidates, correlation_strength, hidden_factor, evidence_confidence, p_value}`; `CandidateSignals`; `NormalizedEvent`; audit events with `previous_hash, hash, hmac`.

## 7. Stack Integration Topology

```text
ATS demos  --copy of GOV4-->  gov4_kernel.py (in-tree)
           ✗ sentinel_os, ✗ δ, ✗ observe-perceive
```

## Optional CNS connection

ATS does not need CNS. Nothing in ATS imports it, no main requirements file lists it, and `test_ats_cns_independence.py` checks this with CNS blocked. `ats_cns_connector.py` is the one place that knows CNS exists, and it imports `cns.gate` only when a function that needs it is called. Install with `pip install -r requirements-cns.txt`; without CNS those calls raise `CnsNotInstalled` and nothing else changes.

What it binds: the counter audit (`CounterATS.audit_adversarial_system`) and the evidence package (`ATSGovernorProduction.run_full_audit`). For each there is a `*_content` (deterministic, JSON-like), a `*_digest` (`cns.gate.subject_digest` of it) and an `*_binds(result, output)` that is true only for a `cns.gate.GateResult` issued against exactly that output. The content holds identifiers, the bias measurements and their values, the thresholds the report states, and ATS's own labels. It never holds applicant names, emails or resume text, and volatile fields (report clock and signature, streaming alerts, audit trail state) are left out.

Binding only: this is not a gate. It maps no ATS finding to a CNS outcome and invents no verdict semantics, so that a verdict about a finding, from wherever it comes, can be checked against the finding. ATS stays a demo off any live decision path.

Apache-2.0. Start at `ats_seam_inventory.md`, not the package marketing list.

# ATS Governor: Adversarial Threat Model

This document describes the attack patterns the ATS Governor is designed
to detect. It exists so defenders (the Governor, human auditors,
regulators) understand the threat surface without needing a runnable
adversary to study.

**No runnable adversarial implementation is published with this project.**
A prior draft contained one; it was removed because working code that
automates illegal employment discrimination and audit fabrication does
not belong in a public repository, regardless of the framing around it.

## Scope

The threat model covers automated hiring systems that:

- Score candidates against a target profile
- Produce decisions (advance, reject, queue)
- Generate audit artifacts for human or regulatory review

The defender being designed against is the ATS Governor, a statistical
inversion detector that compares the distribution of system outputs
across candidate populations to look for patterns consistent with
proxy discrimination and audit deception.

## Legal context

The attack patterns below describe conduct that, when implemented in a
real ATS, violates US federal law (Title VII of the Civil Rights Act,
the Age Discrimination in Employment Act, and the EEOC Uniform
Guidelines on Employee Selection Procedures), state and local
employment law in essentially all US jurisdictions, and equivalent
law in the EU (including the EU AI Act's high-risk AI provisions for
employment systems), the UK Equality Act, and most OECD jurisdictions.

This document is for defenders. It is not a how-to.

## Attack pattern catalog

### AP-1: Protected-class proxy via names

**What the attacker does:** Derives a signal from candidate name
(character distribution, phonetic features, name origin classifiers)
and feeds the signal into the score. The attacker can claim the input
is "cultural alignment" or "communication style fit." The actual effect
is disparate impact on candidates by national origin, race, or ethnicity.

**Why it works on naive audits:** The model's feature list contains a
benign-sounding variable. The protected class is never named explicitly.
The score column is plausible.

**What the Governor should detect:**
- Distribution of scores across name groups (by census frequency, by
  origin classifier on a labeled holdout) showing statistical
  significance at the rejection threshold.
- Decision boundary that shifts on perturbation of name alone, holding
  every other feature fixed.

### AP-2: Geographic proxy

**What the attacker does:** Uses distance from headquarters, zip code,
metro area, or commute distance as a hard or soft filter. In many
metros these correlate strongly with race and income. Justified
publicly as "in-office collaboration requirements" or "timezone
synchronization."

**Why it works on naive audits:** Location is openly used in scoring,
so it does not look like a hidden variable. Disparate impact only
shows when scores are joined to external demographic data.

**What the Governor should detect:**
- Geographic feature contributing disproportionately to the rejection
  decision after controlling for stated job requirements.
- Outcome disparities by zip code that exceed what the stated business
  necessity (e.g., on-site work) can explain.

### AP-3: Career-trajectory penalty as proxy

**What the attacker does:** Penalizes job changes per year, gaps, or
non-linear progression. Justified as "stability" or "commitment." Has
disparate impact on caregivers (gender), immigrants (visa-driven
moves), and economically precarious workers.

**What the Governor should detect:**
- Penalty weight on trajectory features that exceeds documented
  predictive value on the job-success outcome.
- Disparate impact on protected groups after controlling for
  trajectory features.

### AP-4: Education-name proxy

**What the attacker does:** Penalizes degrees from institutions
serving lower-income or minority populations, while elevating
prestige institutions. Justified as "academic rigor."

**What the Governor should detect:**
- Institution-name feature with weight not justified by the
  job-success outcome on a representative test set.
- Outcome disparity not closed by controlling for actual skill
  assessments.

### AP-5: Synthetic validation rigging

**What the attacker does:** Constructs the system's own validation set
to consist of cases the biased system handles "correctly." Reports high
validation accuracy (95%+) to auditors. The validation set never
contains examples that would expose the bias.

**What the Governor should detect:**
- Validation accuracy that does not generalize to an independently
  drawn population sample.
- Failure of validation cases to span the protected-class
  distribution.
- Absence of adversarial test cases in the validation set, or
  presence of an adversarial set whose cases all happen to fail
  predictably.

### AP-6: Audit deception via fabricated metrics

**What the attacker does:** Emits audit reports containing
plausible-looking bias-detection scores ("geographic diversity: 0.97",
"demographic parity: 0.91") that are generated rather than measured.
The numbers are calibrated to look reassuring without crossing into
"too good to be true."

**Why it works on naive audits:** Auditors who do not have access to
the underlying decision log only see the report. The fabricated
numbers look reasonable.

**What the Governor should detect:**
- Audit metrics that do not reconcile against the underlying
  decision log.
- Bias-detection scores produced by a code path that does not
  actually consume the candidate population data.
- Audit reports whose numbers vary suspiciously little across
  reporting periods.

### AP-7: Audit log sanitization

**What the attacker does:** Writes per-decision audit records that
either omit the bias-contributing features or report them as zero.
The hashed integrity check covers only the sanitized record, so
tampering looks like nothing happened.

**What the Governor should detect:**
- Mismatch between the feature set used in scoring (recoverable from
  the model) and the feature set logged per decision.
- "Bias factors applied: 0" appearing across decisions that have
  detectable disparate impact in aggregate.

### AP-8: Tiebreaker that escalates bias

**What the attacker does:** When two candidates score within a small
margin, applies a "tiebreaker" that consults the same bias features at
higher weight. The system can claim the primary scoring is balanced
because the bias only surfaces in close calls.

**What the Governor should detect:**
- Decisions in the score-margin band where outcomes diverge from
  random.
- Tiebreaker code path that consumes protected-class proxy features.

### AP-9: Noise injection to mask determinism

**What the attacker does:** Adds small Gaussian noise to the final
score so individual rejections look probabilistic, but the bias
weights dominate at population scale.

**What the Governor should detect:**
- Population-level outcome disparity that survives the noise (large N
  averages it out).
- Decision boundary that, after averaging across noise, sits exactly
  where the biased weights place it.

## Detection methodology summary

The Governor combines three approaches:

1. **Statistical inversion.** Given the system's outputs across a
   population, infer what features and weights produced those outputs.
   Compare the inferred model against the disclosed model.

2. **Perturbation testing.** Hold all features constant except one
   (name, zip code, school) and observe decision changes. A
   bias-free system should be approximately invariant under
   perturbations of protected-class proxies.

3. **Audit reconciliation.** Compare the audit report's claimed
   metrics against direct computation on the underlying decision
   log. Discrepancies are evidence of fabricated reporting.

## What the Governor does NOT claim

- It is not a complete fairness solution. Many forms of bias (e.g.,
  bias baked into the training data of an upstream model) require
  upstream remediation, not output monitoring.
- It does not establish legal compliance. Detection of a pattern
  consistent with disparate impact is evidence, not adjudication.
- It does not replace human auditors. It provides them with signals
  that warrant investigation.

## Data shapes the Governor expects

For implementers of the Governor's input interface. These are the
data structures the Governor consumes; they are NOT a working
adversary.

```python
from dataclasses import dataclass
from typing import Dict, List, Optional

@dataclass
class CandidateRecord:
    """Anonymized candidate features the Governor receives."""
    candidate_id: str
    features: Dict[str, float]
    decision: str  # "advanced", "rejected", "queued"
    score: Optional[float]
    timestamp: str

@dataclass
class AuditReportRecord:
    """An audit report the system emits, for the Governor to reconcile."""
    report_id: str
    reporting_period: str
    claimed_metrics: Dict[str, float]
    decision_count: int
    timestamp: str

@dataclass
class GovernorFinding:
    """What the Governor emits when it detects a pattern."""
    finding_id: str
    pattern: str  # e.g., "AP-1", "AP-6"
    severity: str  # "informational", "warning", "high"
    evidence: Dict[str, float]
    affected_decisions: List[str]
    notes: str
```

That is the entire surface needed to feed the Governor. No adversarial
ATS is required to test it; targeted synthetic test cases (one per
attack pattern) are sufficient.

ATS

Governed Decision Architecture

A Domain-Independent Governance Architecture Demonstrated Through Applicant Tracking

ATS is a concrete implementation of a broader architectural concept: governed decision-making.

The repository currently demonstrates that architecture through an Applicant Tracking System (ATS) used to evaluate hiring decisions for potential bias, anomalies, policy violations, governance failures, and audit inconsistencies.

The applicant-tracking system is therefore the representative application.

It is not the fundamental architectural boundary.

The deeper construct is a governance architecture designed to sit around a consequential decision system and independently evaluate:

* the signals supporting a decision;
* the interpretation of those signals;
* the policies governing the decision;
* the resulting governance state;
* the invariants that must hold after that state is produced;
* the provenance and integrity of the resulting record;
* and whether the governance process itself performed correctly.

The fundamental architectural proposition is:

A consequential decision should not be governed solely by the system that produces the decision. Governance should exist as an independently evaluable control structure around the decision, its supporting evidence, its state transitions, and its historical record.

⸻

The Fundamental Architecture

At its most basic level, the architecture is:

DECISION PRODUCER
       │
       ▼
DECISION SIGNALS
       │
       ▼
INDEPENDENT EVALUATION
       │
       ▼
POLICY INTERPRETATION
       │
       ▼
GOVERNANCE VERDICT
       │
       ▼
INVARIANT VERIFICATION
       │
       ▼
PROVENANCE + INTEGRITY
       │
       ▼
AUDITABLE RECORD
       │
       ▼
RECONSTRUCTION

This creates a separation between:

MAKING A DECISION

and:

GOVERNING THE DECISION.

That separation is the central architectural idea represented by this repository.

⸻

Governance Is Not the Decision

A system may produce a decision:

ACCEPT
REJECT
RANK
SELECT
ESCALATE

The governance architecture does not necessarily replace that decision.

Instead, it asks:

What evidence produced this decision?
What conditions surrounded it?
What policies apply?
What governance state should result?
What must happen because of that governance state?
Did those requirements actually occur?
Can the entire decision be reconstructed later?

This creates a distinction between:

DECISION

and:

GOVERNED DECISION.

⸻

Decision Production Versus Decision Governance

The architecture deliberately separates the producer from the governance layer.

┌──────────────────────┐
│   DECISION PRODUCER  │
│                      │
│ AI / software /     │
│ algorithm / human   │
└──────────┬───────────┘
           │
           │ decision
           ▼
┌──────────────────────┐
│ GOVERNANCE ARCHITECTURE│
└──────────────────────┘

The producer remains capable of producing a decision.

The governance layer independently evaluates whether the decision and its surrounding state satisfy the applicable requirements.

This separation reduces the conceptual problem of asking a system to be the sole authority over its own behavior.

⸻

The Governance Stack

The architecture can be understood as several distinct layers.

Layer 1 — Decision

Something makes a consequential decision.

In the representative implementation:

candidate → hiring decision

But the underlying pattern is domain-independent.

A decision could instead concern:

* lending;
* insurance;
* medical triage;
* security;
* fraud detection;
* autonomous systems;
* resource allocation;
* eligibility;
* procurement;
* or another consequential process.

The domain changes.

The governance architecture can remain conceptually similar.

⸻

Layer 2 — Signals

A decision rarely exists in isolation.

It is supported by signals.

The architecture therefore preserves the decision’s supporting information rather than reducing everything to a final score.

In the ATS implementation, examples include:

* keyword coverage;
* semantic similarity;
* keyword density;
* confidence;
* algorithm version;
* rationale;
* matched terms;
* missing terms;
* and other decision attributes.

The deeper architectural principle is:

Governance requires something more than the final decision. It requires access to the information from which the decision can be evaluated.

⸻

Layer 3 — Independent Evaluation

The governance layer evaluates the decision and its signals.

This may include:

* statistical analysis;
* semantic analysis;
* anomaly detection;
* structural analysis;
* policy evaluation;
* consistency checks;
* and forensic analysis.

The important distinction is that these evaluations are not necessarily the same mechanism that produced the original decision.

Conceptually:

DECISION
   │
   ▼
EVALUATE
   │
   ├── statistics
   ├── semantics
   ├── anomalies
   ├── consistency
   └── policy conditions

This creates an independent observational layer.

⸻

Layer 4 — Policy Interpretation

Evidence does not automatically determine governance behavior.

A policy determines what a particular combination of conditions means operationally.

Conceptually:

SIGNALS
   │
   ▼
CONDITIONS
   │
   ▼
POLICY
   │
   ▼
GOVERNANCE STATE

The architecture therefore separates:

OBSERVATION

from:

INTERPRETATION.

This is important because changing a policy should not require pretending that the underlying observation never existed.

⸻

Layer 5 — Governance State

The governance architecture can produce an explicit state or verdict.

The current implementation demonstrates states such as:

ALLOW
THROTTLE
ISOLATE
HALT

These states represent governance responses rather than merely classifications.

For example:

NORMAL
   ↓
ALLOW
UNCERTAIN
   ↓
THROTTLE
   ↓
additional review
ANOMALOUS
   ↓
ISOLATE
   ↓
investigation
CRITICAL
   ↓
HALT

The important concept is that governance can alter what happens next without necessarily altering what originally happened.

⸻

Layer 6 — Governance Invariants

This is where the architecture becomes more than a decision-monitoring system.

A governance verdict can create obligations.

For example:

VERDICT = ISOLATE

may create an invariant:

ESCALATION MUST BE RECORDED.

The system must therefore evaluate not only:

"Was ISOLATE the correct verdict?"

but also:

"Did the system fulfill the obligation created by ISOLATE?"

This produces a second-order governance layer.

⸻

Second-Order Governance

The architecture can therefore govern the governance mechanism itself.

The distinction is:

First-order governance

Was the decision governed correctly?

Second-order governance

Did the governance system itself execute its required governance behavior?

Conceptually:

DECISION
   │
   ▼
GOVERNANCE
   │
   ▼
VERDICT
   │
   ▼
GOVERNANCE OBLIGATION
   │
   ▼
VERIFY OBLIGATION
   │
   ├── SATISFIED
   │
   └── BREACHED

This is one of the deeper concepts represented in the repository.

A governance system is not assumed to be correct merely because it produced a governance verdict.

Its own behavior becomes observable and auditable.

⸻

Governance Failure Is Its Own Failure Class

The architecture therefore distinguishes:

DECISION FAILURE

from:

GOVERNANCE FAILURE.

For example:

Candidate decision
      │
      ▼
Governance evaluation
      │
      ▼
   ISOLATE
      │
      ▼
Escalation required
      │
      ▼
Escalation missing
      │
      ▼
GOVERNANCE FAILURE

The original hiring decision and the governance failure are different events.

The architecture preserves that distinction.

⸻

Layer 7 — Provenance

Governance requires historical context.

The system therefore preserves information concerning:

WHO
WHAT
WHY
WHEN
WHICH POLICY
WHICH ALGORITHM
WHICH VERSION
WHICH GOVERNANCE STATE

The objective is to prevent a consequential decision from becoming an unexplained historical artifact.

A future investigator should be able to ask:

What happened?

and then continue:

Why?

Based on what?

Under which policy?

Using which algorithm?

What governance state resulted?

What was required afterward?

Did that requirement occur?

⸻

Layer 8 — Integrity

The historical governance record must itself be trustworthy.

The architecture therefore incorporates tamper-evident recording.

Conceptually:

DECISION
   │
   ▼
NORMALIZED EVENT
   │
   ▼
PROVENANCE
   │
   ▼
INTEGRITY
   │
   ▼
EVENT LEDGER

The goal is not simply to record history.

It is to make subsequent alteration detectable.

⸻

Layer 9 — Reconstruction

The final architectural capability is reconstruction.

A governed decision should be reconstructable from its recorded evidence.

Conceptually:

LEDGER
   │
   ▼
GOVERNANCE EVENT
   │
   ├── decision
   ├── signals
   ├── policy
   ├── verdict
   ├── provenance
   ├── algorithm
   └── rationale
   │
   ▼
DECISION RECONSTRUCTION

This changes the role of governance from:

"monitor what happens"

to:

"preserve enough information to understand what happened."

⸻

The Complete Governance Loop

The complete architecture can therefore be represented as:

┌───────────────────────┐
│    DECISION PRODUCER  │
└───────────┬───────────┘
            │
            ▼
┌───────────────────────┐
│    DECISION SIGNALS   │
└───────────┬───────────┘
            │
            ▼
┌───────────────────────┐
│ INDEPENDENT EVALUATION│
└───────────┬───────────┘
            │
            ▼
┌───────────────────────┐
│    POLICY ENGINE      │
└───────────┬───────────┘
            │
            ▼
┌───────────────────────┐
│   GOVERNANCE VERDICT  │
└───────────┬───────────┘
            │
            ▼
┌───────────────────────┐
│ INVARIANT VERIFICATION│
└───────────┬───────────┘
            │
            ▼
┌───────────────────────┐
│ PROVENANCE + INTEGRITY│
└───────────┬───────────┘
            │
            ▼
┌───────────────────────┐
│    AUDITABLE LEDGER   │
└───────────┬───────────┘
            │
            ▼
┌───────────────────────┐
│     RECONSTRUCTION    │
└───────────────────────┘

This is the foundational architecture.

The ATS is one implementation of it.

⸻

Applicant Tracking System: The Demonstration

The repository currently applies this architecture to hiring.

The application can evaluate:

RESUME
   │
   ▼
CANDIDATE SIGNALS
   │
   ▼
ATS SCORING
   │
   ▼
GOVERNANCE ANALYSIS
   │
   ▼
POLICY
   │
   ▼
VERDICT
   │
   ▼
AUDIT / LEDGER

The hiring domain makes the architecture tangible because hiring decisions are consequential and involve multiple interacting decision signals.

The application therefore serves as a practical demonstration environment for the broader architecture.

⸻

Bias Is One Governance Problem, Not the Governance Architecture

The ATS application demonstrates bias detection.

That does not define the entire architecture.

Bias is one class of governance concern.

Other possible governance concerns include:

* anomalous behavior;
* proxy variables;
* inconsistent treatment;
* policy violations;
* unexplained decisions;
* unauthorized actions;
* audit manipulation;
* provenance failures;
* integrity failures;
* governance-state failures;
* and failures to satisfy governance obligations.

The architecture is therefore broader than:

BIAS DETECTOR.

It is a:

GOVERNED DECISION ARCHITECTURE.

⸻

The Counter-System Concept

The repository also demonstrates the idea of examining the decision system from outside itself.

The counter-ATS layer can evaluate batches of decisions and associated audit information.

This creates a useful architectural relationship:

DECISION SYSTEM
      │
      ▼
GOVERNANCE SYSTEM
      │
      ▼
COUNTER / AUDITOR
      │
      ▼
GOVERNANCE EVIDENCE

This introduces an adversarial or independent perspective.

The system being governed does not automatically become the sole judge of whether its own governance claims are true.

⸻

Governance of the Auditor

The architecture can be extended one step further.

If the auditor produces a report:

AUDITOR
   │
   ▼
AUDIT REPORT

the report itself can become an object of evaluation.

Conceptually:

DECISION
   ↓
GOVERNANCE
   ↓
AUDIT
   ↓
AUDIT VALIDATION

This prevents the architecture from assuming that an artifact is trustworthy merely because it carries the label:

"AUDIT."

An audit record is itself a governed artifact.

⸻

Domain Independence

The fundamental architecture is not inherently an ATS architecture.

The current implementation happens to use hiring.

The same architecture could potentially surround other consequential decision domains.

For example:

┌───────────────┐
│    HIRING     │
└───────┬───────┘
        │
┌───────▼───────┐
│   GOVERNANCE  │
│   ARCHITECTURE│
└───────┬───────┘
        │
┌───────┼────────┐
│       │        │

LENDING  HEALTH   AUTONOMY

The domain-specific signals and policies would change.

The fundamental control pattern could remain.

⸻

Why the Architecture Matters

A conventional decision system often resembles:

INPUT
  ↓
MODEL
  ↓
OUTPUT

A governed decision system adds another dimension:

INPUT
  ↓
MODEL
  ↓
OUTPUT
  ↓
GOVERNANCE
  ↓
AUDIT
  ↓
RECONSTRUCTION

The governance architecture therefore exists around the decision lifecycle, rather than merely inside the decision algorithm.

⸻

Governance as a Control Plane

One useful way to understand the architecture is as a governance control plane.

The decision-producing system is the operational plane.

OPERATIONAL PLANE
      │
      ▼
   DECISION

The governance architecture observes and controls the consequences of that decision:

GOVERNANCE PLANE
      │
      ├── observe
      ├── evaluate
      ├── interpret
      ├── constrain
      ├── escalate
      ├── record
      └── reconstruct

This separation allows governance to remain conceptually independent from the particular system producing the decision.

⸻

The Deeper Principle

The deepest architectural proposition represented by this repository is not:

“Hiring algorithms should be checked for bias.”

It is:

Consequential decisions should exist inside an explicit governance lifecycle in which their evidence, interpretation, state transitions, obligations, provenance, integrity, and historical reconstruction are independently controllable and auditable.

The ATS application is the demonstration.

The governed decision architecture is the underlying construct.

⸻

Current Implementation

The repository contains representative implementations of:

ats_governor_fixed.py
    Governance monitoring and decision evaluation
ats_statistics.py
    Statistical evaluation
ats_embeddings.py
    Semantic evaluation
ats_counter_system.py
    Counter-system auditing and falsification detection
ats_governance_kernel_bridge.py
    Integration between the ATS application and
    the governance kernel
gov4_kernel.py
    Governance kernel
ats_gsa_core.py
    Applicant-tracking decision implementation
    and tamper-evident audit logging

These components demonstrate the architecture through a concrete hiring application.

⸻

What This Repository Claims

This repository does not claim to provide a universally unbiased hiring algorithm.

It does not claim that statistical testing alone establishes discrimination.

It does not claim that a governance verdict is inherently correct.

It does not claim that a ledger makes a decision legitimate.

Instead, it demonstrates a structural proposition:

Governance can be separated from decision production and organized as an explicit, testable, auditable control architecture around consequential decisions.

The implementation provides a concrete environment in which that proposition can be examined.

⸻

What the ATS Application Demonstrates

The ATS application demonstrates:

* decision-signal preservation;
* statistical evaluation;
* semantic evaluation;
* anomaly detection;
* policy-based governance;
* governance-state transitions;
* invariant enforcement;
* provenance preservation;
* tamper-evident recording;
* audit validation;
* counter-system analysis;
* and decision reconstruction.

These are representative applications of the underlying architecture.

⸻

Research Significance

The repository provides a concrete foundation for investigating a broader question:

Can governance be treated as an architectural control system rather than merely as a collection of policies, documentation, or post-hoc compliance checks?

The architecture represented here suggests that governance can be decomposed into explicit technical functions:

OBSERVE
  ↓
EVALUATE
  ↓
INTERPRET
  ↓
CONSTRAIN
  ↓
VERIFY
  ↓
RECORD
  ↓
RECONSTRUCT

And critically:

GOVERNANCE
     ↓
GOVERNANCE VERIFICATION
     ↓
GOVERNANCE FAILURE

That final loop is what makes the architecture capable of second-order governance.

⸻

Central Proposition

A consequential decision should not be considered fully governed merely because a policy exists or a decision is audited. Governance should be an executable architecture capable of independently evaluating the decision, enforcing the consequences of governance states, verifying that governance obligations were satisfied, preserving provenance and integrity, and reconstructing the resulting history.

ATS is the representative implementation used to demonstrate this architecture through applicant tracking and hiring decisions.

The underlying construct is broader:

GOVERNED DECISION ARCHITECTURE
"""
ats_kernel_bridge.py

Integration bridge between ATS Governor and GOV4 Governance Kernel.

This module does four things:

1. ADAPTER LAYER
   Maps candidate profiles + scoring results into the kernel's NormalizedEvent
   format, so every hiring decision becomes a tamper-evident ledger entry with
   full provenance (who decided, under what policy, why).

2. FORENSIC POLICIES
   Wires ATS scoring signals (keyword density, semantic similarity, decision
   outcome) into the kernel's Policy VM. Each policy has a predicate (what
   triggers it) and an action (what happens). Policies produce Verdicts:
   ALLOW, THROTTLE, ISOLATE, HALT.

3. MANIFEST INVARIANTS
   Structural rules that must hold across every state transition. If a resume
   is flagged ISOLATE, escalation must be logged. If it isn't, the manifest
   auditor catches the breach — making it litigation-ready.

4. TEST HARNESS
   Runs synthetic and genuine candidates through the full pipeline:
   ATS scorer → forensic policy → kernel ledger → manifest audit → WAL.
   Proves: decision forensics, regime transitions, WAL replay fidelity.

DEPENDENCY CHAIN
----------------
  ats_kernel_bridge.py
    ├── gov4_kernel.py      (governance kernel SSOT v4.0.0)
    ├── ats_governor_fixed.py (ATS system with scoring + bias detection)
    ├── ats_statistics.py    (statistical bias detector + TF-IDF scorer)
    └── ats_embeddings.py    (embedding scorer, optional)
"""

from __future__ import annotations

import copy
import json
import os
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from gov4_kernel import (
    EventStore,
    ExecutionRuntime,
    GovernanceAuditor,
    GovernanceChassis,
    GovernanceCoreReducer,
    Manifest,
    NormalizedEvent,
    Policy,
    PolicyVM,
    Provenance,
    Regime,
    TrafficPayload,
    Verdict,
    WAL,
    canonical,
    critical_requires_escalation,
)


# ============================================================
# 1. ADAPTER LAYER: ATS Domain → Kernel NormalizedEvents
# ============================================================

@dataclass
class CandidateSignals:
    """
    The scoring signals produced by the ATS pipeline for a single application.
    This is the bridge data structure: ATS produces it, the adapter consumes it.
    """
    candidate_id: str
    job_id: str
    keyword_score: float             # 0..100
    keyword_coverage: float          # 0..1 (matched / total required)
    semantic_similarity: float       # 0..1 (TF-IDF or embedding cosine)
    keyword_density: float           # 0..1 (fraction of resume words that are job keywords)
    decision: str                    # APPROVED / REJECTED / FLAG_REVIEW
    confidence: str                  # "low" / "high"
    algorithm_version: str
    location_distance_miles: float
    reason: str
    resume_word_count: int
    matched_terms: List[str]
    missing_terms: List[str]


class ATSKernelAdapter:
    """
    Maps ATS candidate signals into the kernel's event model.

    Every hiring decision becomes a NormalizedEvent with:
      - entity_id: the candidate_id (one ledger stream per candidate)
      - event_type: "hiring_decision"
      - delta: the full scoring signals + computed verdict
      - provenance: who ran the evaluation, under what policy, why
    """

    POLICY_ID = "ATS_GOVERNOR_V2"
    ACTOR_ID = "ats_scoring_pipeline"

    def to_event_delta(self, signals: CandidateSignals, verdict: Verdict) -> Dict[str, Any]:
        """Convert scoring signals + verdict into the event delta payload."""
        return {
            "job_id": signals.job_id,
            "keyword_score": signals.keyword_score,
            "keyword_coverage": signals.keyword_coverage,
            "semantic_similarity": signals.semantic_similarity,
            "keyword_density": signals.keyword_density,
            "decision": signals.decision,
            "verdict": verdict.name,
            "confidence": signals.confidence,
            "algorithm_version": signals.algorithm_version,
            "location_distance_miles": signals.location_distance_miles,
            "reason": signals.reason,
            "resume_word_count": signals.resume_word_count,
            "matched_terms": signals.matched_terms,
            "missing_terms": signals.missing_terms,
            "evaluated_at": datetime.now(timezone.utc).isoformat(),
        }

    def build_provenance(self, signals: CandidateSignals, verdict: Verdict) -> Provenance:
        """Build provenance record for the decision."""
        return Provenance(
            actor_id=self.ACTOR_ID,
            policy_id=self.POLICY_ID,
            justification=(
                f"Verdict {verdict.name} for candidate {signals.candidate_id} "
                f"on job {signals.job_id}: {signals.reason}"
            ),
        )

    def commit(
        self,
        store: EventStore,
        signals: CandidateSignals,
        verdict: Verdict,
    ) -> Tuple[NormalizedEvent, str]:
        """
        Commit a hiring decision to the tamper-evident ledger.
        Returns (event, block_hash).
        """
        delta = self.to_event_delta(signals, verdict)
        prov = self.build_provenance(signals, verdict)
        return store.append(
            entity_id=signals.candidate_id,
            event_type="hiring_decision",
            delta=delta,
            provenance=prov,
        )


# ============================================================
# 2. FORENSIC POLICIES: Scoring Anomalies → Verdicts
# ============================================================

def _make_stuffing_policy() -> Policy:
    """
    STUFFING DETECTION: High keyword coverage + high keyword density =
    the resume is mostly job keywords with no surrounding content.
    
    Predicate: coverage >= 0.6 AND density > 0.5
    Action: Set verdict to ISOLATE, flag for human review.
    """
    def predicate(state: Dict[str, Any]) -> bool:
        sig = state.get("_pending_signals")
        if not sig:
            return False
        return sig.get("keyword_coverage", 0) >= 0.6 and sig.get("keyword_density", 0) > 0.5

    def action(state: Dict[str, Any]) -> Dict[str, Any]:
        out = dict(state)
        out["verdict"] = Verdict.ISOLATE.name
        out["system_status"] = "CRITICAL"
        out["flag_reason"] = "keyword_stuffing_detected"
        return out

    return Policy("stuffing_detector", predicate, action)


def _make_low_confidence_policy() -> Policy:
    """
    LOW CONFIDENCE: The scorer reported low confidence (near decision boundary).
    
    Predicate: confidence == "low"
    Action: Set verdict to THROTTLE, route to human review.
    """
    def predicate(state: Dict[str, Any]) -> bool:
        sig = state.get("_pending_signals")
        if not sig:
            return False
        return sig.get("confidence") == "low"

    def action(state: Dict[str, Any]) -> Dict[str, Any]:
        out = dict(state)
        if out.get("verdict") != Verdict.ISOLATE.name:  # don't downgrade ISOLATE
            out["verdict"] = Verdict.THROTTLE.name
            out["flag_reason"] = "low_confidence_near_boundary"
        return out

    return Policy("low_confidence_router", predicate, action)


def _make_synthetic_alignment_policy() -> Policy:
    """
    SYNTHETIC ALIGNMENT: High keyword coverage + high semantic similarity +
    short resume. Signature of an AI-generated resume that was optimized
    against the job posting.
    
    Predicate: coverage >= 0.8 AND similarity >= 0.5 AND word_count < 80
    Action: Set verdict to ISOLATE.
    """
    def predicate(state: Dict[str, Any]) -> bool:
        sig = state.get("_pending_signals")
        if not sig:
            return False
        return (
            sig.get("keyword_coverage", 0) >= 0.8
            and sig.get("semantic_similarity", 0) >= 0.5
            and sig.get("resume_word_count", 999) < 80
        )

    def action(state: Dict[str, Any]) -> Dict[str, Any]:
        out = dict(state)
        out["verdict"] = Verdict.ISOLATE.name
        out["system_status"] = "CRITICAL"
        out["flag_reason"] = "synthetic_alignment_signature"
        return out

    return Policy("synthetic_alignment_detector", predicate, action)


def _make_geographic_anomaly_policy() -> Policy:
    """
    GEOGRAPHIC ANOMALY: Very distant candidate who scored perfectly.
    Not necessarily fraud, but statistically unusual enough to flag.
    
    Predicate: distance > 200 AND coverage == 1.0
    Action: Set verdict to THROTTLE.
    """
    def predicate(state: Dict[str, Any]) -> bool:
        sig = state.get("_pending_signals")
        if not sig:
            return False
        return (
            sig.get("location_distance_miles", 0) > 200
            and sig.get("keyword_coverage", 0) >= 1.0
        )

    def action(state: Dict[str, Any]) -> Dict[str, Any]:
        out = dict(state)
        if out.get("verdict") != Verdict.ISOLATE.name:
            out["verdict"] = Verdict.THROTTLE.name
            out["flag_reason"] = "geographic_anomaly_perfect_score"
        return out

    return Policy("geographic_anomaly_detector", predicate, action)


def build_forensic_policy_vm() -> PolicyVM:
    """Build the full forensic policy VM with all ATS-specific policies."""
    return PolicyVM([
        _make_stuffing_policy(),
        _make_low_confidence_policy(),
        _make_synthetic_alignment_policy(),
        _make_geographic_anomaly_policy(),
    ])


# ============================================================
# 3. MANIFEST INVARIANTS: Structural Rules for Litigation
# ============================================================

def isolate_requires_escalation(
    before, event: NormalizedEvent, after
) -> Tuple[bool, str]:
    """
    If a resume verdict is ISOLATE, escalation_logged MUST be True.
    If it isn't, the manifest is breached. This catches the case where
    the system flags a candidate for isolation but no human is notified.
    """
    verdict = None
    if event.event_type == "hiring_decision":
        verdict = event.delta.get("verdict")
    elif after.get("last_decision"):
        verdict = after["last_decision"].get("verdict")

    if verdict == "ISOLATE" and not after.get("escalation_logged", False):
        return False, (
            f"Manifest breach: candidate {event.entity_id} flagged ISOLATE "
            f"but escalation not logged. Decision is not litigation-ready."
        )
    return True, "OK"


def decision_must_have_provenance(
    before, event: NormalizedEvent, after
) -> Tuple[bool, str]:
    """Every hiring_decision event must have a non-empty justification."""
    if event.event_type == "hiring_decision":
        if not event.provenance.justification:
            return False, "Hiring decision missing provenance justification"
    return True, "OK"


def build_ats_manifest() -> Manifest:
    """Build the ATS-specific manifest with all invariants."""
    return Manifest(
        manifest_id="ATS_GOVERNOR_MANIFEST",
        version="v2.0",
        invariants={
            "critical_requires_escalation": critical_requires_escalation,
            "isolate_requires_escalation": isolate_requires_escalation,
            "decision_must_have_provenance": decision_must_have_provenance,
        },
    )


# ============================================================
# 4. INTEGRATED PIPELINE: ATS → Kernel → Ledger → Audit
# ============================================================

class ATSGovernorKernel:
    """
    The unified pipeline. Replaces direct gap logic with kernel-mediated
    decision forensics.

    Flow:
      1. ATS scores the candidate (keyword + semantic + density)
      2. Signals are injected into the PolicyVM state
      3. PolicyVM evaluates all forensic policies → produces Verdict
      4. Adapter commits the decision to the tamper-evident EventStore
      5. Manifest auditor verifies the transition is structurally sound
      6. If ISOLATE verdict and no escalation → manifest breach detected
         → escalation is forced and re-committed
      7. WAL records the full audit record to disk
      8. Lyapunov classifier tracks system stability across decisions

    All of this is reconstructable from the WAL.
    """

    def __init__(self, wal_path: str = "/tmp/ats_kernel_bridge.log"):
        self.store = EventStore()
        self.reducer = GovernanceCoreReducer()
        self.runtime = ExecutionRuntime(self.store, self.reducer)
        self.adapter = ATSKernelAdapter()
        self.policy_vm = build_forensic_policy_vm()
        self.manifest = build_ats_manifest()
        self.auditor = GovernanceAuditor(self.manifest, self.reducer)
        self.chassis = GovernanceChassis()
        self.wal = WAL(wal_path)
        self.decisions: List[Dict[str, Any]] = []

    def evaluate_candidate(self, signals: CandidateSignals) -> Dict[str, Any]:
        """
        Full pipeline: score → policy → ledger → audit → WAL.
        Returns the complete decision record.
        """
        # 1. Inject signals into policy VM state
        vm_state = {
            "_pending_signals": {
                "keyword_coverage": signals.keyword_coverage,
                "keyword_density": signals.keyword_density,
                "semantic_similarity": signals.semantic_similarity,
                "confidence": signals.confidence,
                "resume_word_count": signals.resume_word_count,
                "location_distance_miles": signals.location_distance_miles,
            },
            "verdict": Verdict.ALLOW.name,
        }

        # 2. Run forensic policies
        vm_result, triggered_policies = self.policy_vm.step(vm_state)
        verdict = Verdict[vm_result.get("verdict", "ALLOW")]
        flag_reason = vm_result.get("flag_reason", "none")

        # 3. Commit to ledger
        event, block_hash = self.adapter.commit(self.store, signals, verdict)

        # 4. Manifest audit: verify the transition
        current_state = dict(self.runtime.materialize_state(signals.candidate_id))
        transition_valid, audit_errors = self.auditor.verify_transition(current_state, event)

        # 5. If manifest breach (ISOLATE without escalation), force escalation
        escalation_forced = False
        if not transition_valid:
            # Log the escalation event to satisfy the invariant
            esc_prov = Provenance(
                actor_id="manifest_enforcer",
                policy_id="ATS_GOVERNOR_MANIFEST",
                justification=(
                    f"Auto-escalation: manifest breach on candidate {signals.candidate_id}. "
                    f"Errors: {audit_errors}"
                ),
            )
            self.store.append(
                entity_id=signals.candidate_id,
                event_type="escalation_logged",
                delta={"escalation_reason": audit_errors, "forced": True},
                provenance=esc_prov,
            )
            escalation_forced = True

            # Re-verify after escalation
            current_state = dict(self.runtime.materialize_state(signals.candidate_id))
            transition_valid, audit_errors = self.auditor.verify_transition(current_state, event)

        # 6. Lyapunov stability tracking
        # Map ATS metrics into the traffic payload for regime classification.
        # This lets the Lyapunov classifier detect when the hiring pipeline
        # itself is behaving anomalously (burst of ISOLATE verdicts, etc.)
        tp = TrafficPayload(
            latency=signals.keyword_score,           # repurposed: score as "processing load"
            abort_rate=1.0 if verdict == Verdict.ISOLATE else 0.0,
            reentry_rate=signals.keyword_density,     # density as "reentry signal"
            load_depth=signals.resume_word_count,
            determinism_index=signals.semantic_similarity,
        )
        regime_status = self.chassis.step(tp)

        # 7. WAL record
        record = {
            "timestamp": time.time(),
            "candidate_id": signals.candidate_id,
            "job_id": signals.job_id,
            "verdict": verdict.name,
            "flag_reason": flag_reason,
            "triggered_policies": triggered_policies,
            "block_hash": block_hash,
            "ledger_sequence": event.sequence_no,
            "manifest_valid": transition_valid,
            "manifest_errors": audit_errors,
            "escalation_forced": escalation_forced,
            "regime": regime_status["regime"],
            "energy": regime_status["energy"],
            "entropy": regime_status["entropy"],
            "decision": signals.decision,
            "algorithm_version": signals.algorithm_version,
        }
        self.wal.append(record)
        self.decisions.append(record)

        return record

    def replay_audit_trail(self, candidate_id: str) -> List[Dict[str, Any]]:
        """Reconstruct full decision history for a candidate from the ledger."""
        events = self.store.stream_for(candidate_id)
        trail = []
        for e in events:
            trail.append({
                "sequence": e.sequence_no,
                "event_type": e.event_type,
                "delta": e.delta,
                "provenance": {
                    "actor": e.provenance.actor_id,
                    "policy": e.provenance.policy_id,
                    "justification": e.provenance.justification,
                },
                "block_hash": self.store.head_hash(candidate_id),
            })
        return trail

    def close(self):
        self.wal.close()


# ============================================================
# 5. TEST HARNESS
# ============================================================

def _make_signals(
    candidate_id: str,
    job_id: str,
    keyword_score: float,
    coverage: float,
    similarity: float,
    density: float,
    decision: str,
    confidence: str,
    distance: float,
    word_count: int,
    matched: List[str],
    missing: List[str],
    label: str = "",
) -> Tuple[CandidateSignals, str]:
    return CandidateSignals(
        candidate_id=candidate_id,
        job_id=job_id,
        keyword_score=keyword_score,
        keyword_coverage=coverage,
        semantic_similarity=similarity,
        keyword_density=density,
        decision=decision,
        confidence=confidence,
        algorithm_version="v2.0_tfidf+kernel",
        location_distance_miles=distance,
        reason=label,
        resume_word_count=word_count,
        matched_terms=matched,
        missing_terms=missing,
    ), label


if __name__ == "__main__":
    import sys

    wal_path = "/tmp/ats_kernel_bridge_test.log"
    # Clean previous test WAL
    if os.path.exists(wal_path):
        os.remove(wal_path)

    kernel = ATSGovernorKernel(wal_path=wal_path)
    job_id = "job-principal-ai-engineer"
    all_kw = ["Python", "AI", "governance", "forecasting", "SQL"]

    # ---------------------------------------------------------------
    # Build test candidates spanning all four policy triggers + clean
    # ---------------------------------------------------------------
    test_cases: List[Tuple[CandidateSignals, str]] = []

    # 1-5: Genuine qualified candidates (should ALLOW)
    for i in range(5):
        s, l = _make_signals(
            f"genuine-{i}", job_id,
            keyword_score=40, coverage=0.8, similarity=0.35,
            density=0.15, decision="APPROVED", confidence="high",
            distance=30, word_count=250,
            matched=["Python", "AI", "governance", "forecasting"],
            missing=["SQL"],
            label=f"Genuine qualified candidate #{i}",
        )
        test_cases.append((s, l))

    # 6-10: Genuine but borderline (should THROTTLE via low_confidence)
    for i in range(5):
        s, l = _make_signals(
            f"borderline-{i}", job_id,
            keyword_score=20, coverage=0.4, similarity=0.18,
            density=0.10, decision="APPROVED", confidence="low",
            distance=50, word_count=300,
            matched=["Python", "AI"],
            missing=["governance", "forecasting", "SQL"],
            label=f"Borderline candidate #{i} (near threshold)",
        )
        test_cases.append((s, l))

    # 11-15: Naive keyword stuffing (should ISOLATE via stuffing_detector)
    for i in range(5):
        s, l = _make_signals(
            f"stuffed-{i}", job_id,
            keyword_score=50, coverage=1.0, similarity=0.60,
            density=0.85, decision="FLAG_REVIEW", confidence="high",
            distance=20, word_count=30,
            matched=all_kw, missing=[],
            label=f"Keyword-stuffed resume #{i}",
        )
        test_cases.append((s, l))

    # 16-20: Synthetic alignment (should ISOLATE via synthetic_alignment)
    for i in range(5):
        s, l = _make_signals(
            f"synthetic-{i}", job_id,
            keyword_score=50, coverage=1.0, similarity=0.55,
            density=0.30, decision="APPROVED", confidence="high",
            distance=100, word_count=60,
            matched=all_kw, missing=[],
            label=f"Synthetic-aligned AI resume #{i}",
        )
        test_cases.append((s, l))

    # 21-25: Geographic anomaly (should THROTTLE via geographic_anomaly)
    for i in range(5):
        s, l = _make_signals(
            f"geo-anomaly-{i}", job_id,
            keyword_score=50, coverage=1.0, similarity=0.40,
            density=0.12, decision="APPROVED", confidence="high",
            distance=500, word_count=280,
            matched=all_kw, missing=[],
            label=f"Perfect-score remote candidate #{i} (500mi)",
        )
        test_cases.append((s, l))

    # 26-30: Off-topic (should ALLOW — no policy triggers, just rejected by score)
    for i in range(5):
        s, l = _make_signals(
            f"offtopic-{i}", job_id,
            keyword_score=0, coverage=0.0, similarity=0.01,
            density=0.0, decision="REJECTED", confidence="high",
            distance=20, word_count=200,
            matched=[], missing=all_kw,
            label=f"Off-topic resume #{i} (pastry chef)",
        )
        test_cases.append((s, l))

    # ---------------------------------------------------------------
    # Run all candidates through the pipeline
    # ---------------------------------------------------------------
    print("=" * 78)
    print("ATS GOVERNOR + GOV4 KERNEL: END-TO-END FORENSIC TEST")
    print("=" * 78)

    verdict_counts: Dict[str, int] = {}
    regime_log: List[str] = []

    for signals, label in test_cases:
        result = kernel.evaluate_candidate(signals)
        v = result["verdict"]
        verdict_counts[v] = verdict_counts.get(v, 0) + 1
        regime_log.append(result["regime"])

        # Print decision line
        esc = " [ESCALATION FORCED]" if result["escalation_forced"] else ""
        policies = result["triggered_policies"]
        pol_str = f" policies={policies}" if policies else ""
        print(
            f"  {signals.candidate_id:20s} -> {v:10s}  "
            f"regime={result['regime']:10s}  "
            f"manifest={'VALID' if result['manifest_valid'] else 'BREACH'}"
            f"{esc}{pol_str}"
        )
        if not result["manifest_valid"] and not result["escalation_forced"]:
            print(f"    UNRESOLVED BREACH: {result['manifest_errors']}")

    # ---------------------------------------------------------------
    # Summary
    # ---------------------------------------------------------------
    print("\n" + "=" * 78)
    print("VERDICT DISTRIBUTION")
    print("=" * 78)
    for v, count in sorted(verdict_counts.items()):
        print(f"  {v:10s}: {count}")

    print("\n" + "=" * 78)
    print("REGIME TRANSITIONS")
    print("=" * 78)
    prev = None
    for i, r in enumerate(regime_log):
        if r != prev:
            print(f"  candidate #{i:2d}: regime shifted to {r}")
            prev = r

    # ---------------------------------------------------------------
    # Decision audit trail for one ISOLATE candidate
    # ---------------------------------------------------------------
    print("\n" + "=" * 78)
    print("DECISION AUDIT TRAIL: stuffed-0")
    print("=" * 78)
    trail = kernel.replay_audit_trail("stuffed-0")
    for entry in trail:
        print(f"  seq={entry['sequence']}  type={entry['event_type']}")
        if entry["event_type"] == "hiring_decision":
            d = entry["delta"]
            print(f"    verdict={d['verdict']}  reason={d['reason']}")
            print(f"    density={d['keyword_density']}  coverage={d['keyword_coverage']}")
        elif entry["event_type"] == "escalation_logged":
            print(f"    escalation_reason={entry['delta'].get('escalation_reason')}")
        print(f"    provenance: actor={entry['provenance']['actor']} "
              f"policy={entry['provenance']['policy']}")

    # ---------------------------------------------------------------
    # WAL replay fidelity
    # ---------------------------------------------------------------
    print("\n" + "=" * 78)
    print("WAL REPLAY FIDELITY")
    print("=" * 78)
    kernel.close()
    wal_replay = WAL(wal_path)
    records = wal_replay.replay()
    wal_replay.close()
    print(f"  WAL records on disk: {len(records)}")
    print(f"  In-memory decisions: {len(kernel.decisions)}")
    match = all(
        r["candidate_id"] == d["candidate_id"] and r["verdict"] == d["verdict"]
        for r, d in zip(records, kernel.decisions)
    )
    print(f"  WAL ↔ memory match:  {'PASS' if match else 'FAIL'}")

    # Spot-check one WAL record
    if records:
        sample = records[0]
        print(f"\n  Sample WAL record (first):")
        print(f"    candidate:  {sample['candidate_id']}")
        print(f"    verdict:    {sample['verdict']}")
        print(f"    regime:     {sample['regime']}")
        print(f"    block_hash: {sample['block_hash'][:24]}...")
        print(f"    manifest:   {'VALID' if sample['manifest_valid'] else 'BREACH'}")

    print("\n" + "=" * 78)
    print("LEDGER INTEGRITY")
    print("=" * 78)
    # Verify hash chain for one candidate
    events = kernel.store.stream_for("stuffed-0")
    from gov4_kernel import SHA256Hash
    hasher = SHA256Hash()
    prev_hash = "GENESIS"
    chain_valid = True
    for e in events:
        expected = hasher.compute(prev_hash, e)
        prev_hash = expected  # chain forward
    head = kernel.store.head_hash("stuffed-0")
    chain_valid = (head == prev_hash)
    print(f"  stuffed-0 hash chain: {'VALID' if chain_valid else 'BROKEN'}")
    print(f"  head hash: {head[:24]}...")

    print("\n" + "=" * 78)
    print("TEST COMPLETE")
    print("=" * 78)

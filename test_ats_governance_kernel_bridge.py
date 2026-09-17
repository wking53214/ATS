"""Tests for the bridge's handling of verdicts it does not itself produce.

Every site here asked "is this decision severe?" by comparing a verdict
against the single name `ISOLATE`. That is right only while ISOLATE is the
most severe verdict in the vocabulary, and `Verdict.HALT` has been declared
above it from the start. No policy in this module emits HALT, so no test
ever put one through, and four independent places agreed that the most
severe verdict available was not severe:

  * the manifest invariant written to guarantee a human is notified
  * the Lyapunov payload, which scored HALT exactly as it scores ALLOW
  * two policies, which would overwrite a HALT with THROTTLE
  * the verdict lookup, which crashed on any name outside the enum --
    before the ledger commit, so the decision left no record at all

A verdict arrives here from stored data, so "no policy emits it" is not
the same as "it cannot happen".
"""

import pytest

from ats_governance_kernel_bridge import (
    ATSGovernorKernel,
    CandidateSignals,
    _make_geographic_anomaly_policy,
    _make_low_confidence_policy,
    isolate_requires_escalation,
    resolve_verdict,
)
from gov4_kernel import (
    ESCALATION_THRESHOLD,
    NormalizedEvent,
    Provenance,
    Verdict,
    verdict_severity,
)

PROV = Provenance(actor_id="recruiter-7", policy_id="P-1", justification="screening")


def decision(verdict_name):
    return NormalizedEvent(
        event_id="evt-1", entity_id="cand-1", sequence_no=1,
        event_type="hiring_decision", delta={"verdict": verdict_name},
        provenance=PROV,
    )


# ------------------------------------------------- the manifest invariant

def test_halt_without_escalation_breaches_the_manifest():
    ok, reason = isolate_requires_escalation({}, decision("HALT"), {})
    assert ok is False
    assert "HALT" in reason


def test_isolate_without_escalation_still_breaches_the_manifest():
    """The control: ranking must not have loosened the original case."""
    ok, _ = isolate_requires_escalation({}, decision("ISOLATE"), {})
    assert ok is False


def test_an_escalated_halt_is_not_a_breach():
    ok, _ = isolate_requires_escalation(
        {}, decision("HALT"), {"escalation_logged": True})
    assert ok is True


def test_allow_is_not_a_breach():
    ok, _ = isolate_requires_escalation({}, decision("ALLOW"), {})
    assert ok is True


# -------------------------------------------------------- the two policies

@pytest.mark.parametrize("make_policy,state", [
    (_make_low_confidence_policy, {"confidence": "low"}),
    (_make_geographic_anomaly_policy,
     {"location_distance_miles": 500, "keyword_coverage": 1.0}),
])
def test_a_policy_does_not_downgrade_a_more_severe_verdict(make_policy, state):
    """Both guards read `!= ISOLATE` and meant "is not already worse". A
    HALT in state is not ISOLATE, so both overwrote it with THROTTLE."""
    policy = make_policy()
    vm_state = {"_pending_signals": state, "verdict": Verdict.HALT.name}

    assert policy.predicate(vm_state) is True, "policy must fire for this test to mean anything"
    assert policy.action(vm_state)["verdict"] == Verdict.HALT.name


@pytest.mark.parametrize("make_policy,state", [
    (_make_low_confidence_policy, {"confidence": "low"}),
    (_make_geographic_anomaly_policy,
     {"location_distance_miles": 500, "keyword_coverage": 1.0}),
])
def test_a_policy_still_throttles_an_allow(make_policy, state):
    """The control: the guard must still let the policy do its job."""
    policy = make_policy()
    vm_state = {"_pending_signals": state, "verdict": Verdict.ALLOW.name}

    assert policy.action(vm_state)["verdict"] == Verdict.THROTTLE.name


# ----------------------------------------------------- reading the verdict

def test_a_readable_verdict_keeps_the_policy_reason():
    verdict, reason = resolve_verdict({"verdict": "ISOLATE", "flag_reason": "stuffing"})
    assert verdict is Verdict.ISOLATE
    assert reason == "stuffing"


def test_an_absent_verdict_is_allow():
    """The VM seeds ALLOW, so an untouched state must stay ALLOW rather than
    failing closed on a decision no policy objected to."""
    assert resolve_verdict({})[0] is Verdict.ALLOW


@pytest.mark.parametrize("raw", ["SOMETHING_NEW", "isolate", "", None])
def test_an_unreadable_verdict_ranks_as_severe_and_says_so(raw):
    """Case matters, so a lowercased name is unreadable too -- and must not
    be the quiet path to ALLOW."""
    verdict, reason = resolve_verdict({"verdict": raw, "flag_reason": "stuffing"})
    assert verdict_severity(verdict) >= ESCALATION_THRESHOLD
    assert reason == f"unrecognised_verdict:{raw}"


# ------------------------------------------- the full path through the VM

def _signals(**over):
    base = dict(
        candidate_id="cand-1", job_id="job-1", keyword_score=0.5,
        keyword_coverage=0.2, semantic_similarity=0.2, keyword_density=0.1,
        decision="review", confidence="high", algorithm_version="v1",
        location_distance_miles=5.0, reason="screening", resume_word_count=400,
        matched_terms=[], missing_terms=[],
    )
    base.update(over)
    return CandidateSignals(**base)


def test_an_unrecognised_verdict_is_recorded_rather_than_crashing(tmp_path, monkeypatch):
    """`Verdict[name]` raised KeyError before the ledger commit, so the
    decision vanished. In a tamper-evident ledger, no entry is worse than a
    bad one."""
    kernel = ATSGovernorKernel(wal_path=str(tmp_path / "wal.log"))
    monkeypatch.setattr(
        kernel.policy_vm, "step",
        lambda state: ({"verdict": "SOMETHING_NEW", "flag_reason": "x"}, ["p"]),
    )

    record = kernel.evaluate_candidate(_signals())

    assert record["flag_reason"] == "unrecognised_verdict:SOMETHING_NEW"
    assert kernel.store.stream_for("cand-1"), "the decision must reach the ledger"


def test_a_halt_registers_as_an_abort_not_a_calm_pipeline(tmp_path, monkeypatch):
    """The Lyapunov payload scored HALT at 0.0 -- the value ALLOW scores --
    so the regime classifier read the calmest possible pipeline at the moment
    the strongest stop was issued."""
    kernel = ATSGovernorKernel(wal_path=str(tmp_path / "wal.log"))
    monkeypatch.setattr(
        kernel.policy_vm, "step",
        lambda state: ({"verdict": Verdict.HALT.name, "flag_reason": "x"}, ["p"]),
    )

    seen = {}
    original = kernel.chassis.step
    kernel.chassis.step = lambda tp: (seen.setdefault("abort_rate", tp.abort_rate), original(tp))[1]

    kernel.evaluate_candidate(_signals())

    assert seen["abort_rate"] == 1.0

"""Tests for the governance kernel's two integrity properties.

The repository had no tests. These cover the two things gov4_kernel.py exists
to guarantee and which nothing checked:

1. An event the reducer does not understand must not pass governance.
2. A modified event must be detectable.

Both were broken, in the same way and for the same reason: the failure was
silent. Something that could not do its job returned a value indistinguishable
from having done it.
"""

import pytest

from gov4_kernel import (
    EventStore,
    GovernanceAuditor,
    GovernanceCoreReducer,
    Manifest,
    NormalizedEvent,
    Provenance,
    UnknownEventType,
    critical_requires_escalation,
)

PROV = Provenance(actor_id="recruiter-7", policy_id="P-1", justification="screening")


def event(event_type, delta=None, seq=1):
    return NormalizedEvent(
        event_id=f"evt-{seq}", entity_id="cand-1", sequence_no=seq,
        event_type=event_type, delta=delta or {}, provenance=PROV,
    )


@pytest.fixture
def auditor():
    manifest = Manifest(
        manifest_id="m", version="1",
        invariants={"critical_requires_escalation": critical_requires_escalation},
    )
    return GovernanceAuditor(manifest, GovernanceCoreReducer())


# ---------------------------------------------------------------------------
# 1. An unrecognised event type must not pass governance
# ---------------------------------------------------------------------------

def test_isolate_verdict_without_escalation_is_refused(auditor):
    """The control, so the tests below are known to be measuring something."""
    ok, errors = auditor.verify_transition({}, event("hiring_decision", {"verdict": "ISOLATE"}))
    assert ok is False
    assert any("CRITICAL status without escalation log" in e for e in errors)


def test_a_misspelled_event_type_cannot_launder_the_same_decision(auditor):
    """The regression this file was written for.

    `hiring_decision` -> `hiring_decisions` is one character. The reducer had
    no rule for it, fell off the end, and returned the state unchanged. after
    == before, so every before/after invariant held trivially and the
    transition came back approved with no errors -- the identical ISOLATE
    decision that is refused above, recorded as clean.

    Both generations of this reducer's ancestor raised on an unknown event
    type. Falling through was a regression, and a silent one.
    """
    ok, errors = auditor.verify_transition(
        {}, event("hiring_decisions", {"verdict": "ISOLATE"}))

    assert ok is False, (
        "an event type the reducer has no rule for was approved: the state "
        "could not have been evaluated, because it was never changed"
    )
    assert any("unknown_event_type" in e for e in errors)


def test_the_reducer_raises_rather_than_returning_the_state_unchanged():
    """Returning `before` unchanged is the failure, not a gentler version of it."""
    with pytest.raises(UnknownEventType) as caught:
        GovernanceCoreReducer().apply({}, event("hiring_decisions"))

    # The exception has to identify the event, or an operator learns only that
    # some event somewhere was not understood.
    assert caught.value.event_type == "hiring_decisions"
    assert caught.value.entity_id == "cand-1"
    assert caught.value.sequence_no == 1


@pytest.mark.parametrize("event_type", sorted(GovernanceCoreReducer.HANDLED_EVENT_TYPES))
def test_every_declared_event_type_is_actually_handled(event_type):
    """HANDLED_EVENT_TYPES gates the raise, so a name listed there but with no
    branch behind it would pass the gate and then no-op -- reintroducing the
    original defect through the guard added to prevent it."""
    delta = {"verdict": "ALLOW", "status": "OK"}
    before = {"sentinel": "unchanged"}
    after = GovernanceCoreReducer().apply(before, event(event_type, delta))

    assert after != before or event_type == "escalation_logged" or after.get("escalation_logged"), (
        f"{event_type} is declared handled but changed nothing"
    )


def test_the_auditor_does_not_convert_unrelated_errors_into_refusals(auditor):
    """A bug inside an invariant must crash, not surface as an orderly refusal.

    This is the Conservation Kernel failure shape: a NameError caught broadly
    was reported as 'REJECTED -- Conservation Kernel rejected decision', a
    broken call wearing a principled refusal's clothes. Only UnknownEventType
    is converted here.
    """
    def broken_invariant(before, event, after):
        raise RuntimeError("bug inside the invariant itself")

    manifest = Manifest(manifest_id="m", version="1",
                        invariants={"broken": broken_invariant})
    strict = GovernanceAuditor(manifest, GovernanceCoreReducer())

    with pytest.raises(RuntimeError, match="bug inside the invariant itself"):
        strict.verify_transition({}, event("hiring_decision", {"verdict": "ALLOW"}))


# ---------------------------------------------------------------------------
# 2. A modified event must be detectable
# ---------------------------------------------------------------------------

def test_an_untouched_chain_verifies():
    store = EventStore()
    store.append("cand-1", "hiring_decision", {"verdict": "ALLOW"}, PROV)
    store.append("cand-1", "escalation_logged", {"forced": False}, PROV)

    intact, diverged_at = store.verify_chain("cand-1")
    assert intact is True
    assert diverged_at is None


def test_a_modified_event_is_detected_and_located():
    """The property the section header claims. Nothing could check it before:
    the head hash was written on append and never recomputed, so altering a
    committed event left the head untouched and the change was invisible to
    every line of code in this repository."""
    store = EventStore()
    store.append("cand-1", "hiring_decision", {"verdict": "ISOLATE"}, PROV)
    store.append("cand-1", "escalation_logged", {"forced": True}, PROV)
    store.append("cand-1", "telemetry_update", {"load": 3}, PROV)

    assert store.verify_chain("cand-1")[0] is True

    # Rewrite history: the ISOLATE that forced an escalation becomes an ALLOW.
    # `stream_for` returns a shallow copy, so the delta dicts are the stored
    # ones -- this is a real mutation of the ledger, not of a copy.
    store.stream_for("cand-1")[0].delta["verdict"] = "ALLOW"

    intact, diverged_at = store.verify_chain("cand-1")
    assert intact is False, "a committed event was rewritten and the ledger agreed"
    assert diverged_at == 1, f"divergence located at {diverged_at}, expected the first event"


def test_divergence_is_located_at_the_first_altered_event():
    """Naming the point of divergence is the difference between an actionable
    answer and 'something in this ledger changed'."""
    store = EventStore()
    for i in range(1, 6):
        store.append("cand-1", "telemetry_update", {"load": i}, PROV)

    store.stream_for("cand-1")[3].delta["load"] = 999    # 4th event

    intact, diverged_at = store.verify_chain("cand-1")
    assert intact is False
    assert diverged_at == 4


def test_an_empty_stream_is_consistent():
    assert EventStore().verify_chain("nobody") == (True, None)


def test_streams_are_independent():
    """A tampered stream must not implicate an untouched one."""
    store = EventStore()
    store.append("cand-1", "telemetry_update", {"load": 1}, PROV)
    store.append("cand-2", "telemetry_update", {"load": 1}, PROV)

    store.stream_for("cand-1")[0].delta["load"] = 2

    assert store.verify_chain("cand-1")[0] is False
    assert store.verify_chain("cand-2")[0] is True

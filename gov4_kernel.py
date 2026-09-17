"""
gov4_kernel.py

GOV4 Governance Control Plane - Single Source of Truth (SSOT) v4.0.0

Cryptographic event stores, manifest-driven auditors, policy VMs,
stochastic stability classifiers, and write-ahead logging.

This is a self-contained copy of the kernel so the ATS integration
module can import it without external dependencies beyond numpy.
"""

from __future__ import annotations

import os
import json
import hmac
import hashlib
import logging
import math
import uuid
import copy
from dataclasses import dataclass, field
from enum import Enum, auto
from threading import Lock
from types import MappingProxyType
from typing import Any, Callable, Dict, List, Mapping, Optional, Protocol, Tuple


# ============================================================
# LOGGING & CORE SYSTEM CONSTANTS
# ============================================================
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("gov4.ssot")

APP_NAME = "GOV4 Governance Control Plane"
VERSION = "4.0.0"


# ============================================================
# UTILITIES & SERIALIZATION
# ============================================================
def canonical(obj: Dict[str, Any]) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def normalize(obj: Any, precision: int = 10) -> Any:
    if isinstance(obj, float):
        return round(obj, precision)
    if isinstance(obj, dict):
        return {k: normalize(v, precision) for k, v in obj.items()}
    if isinstance(obj, list):
        return [normalize(v, precision) for v in obj]
    return obj


def public(obj: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in obj.items() if not k.startswith("_")}


# ============================================================
# CORE DATA MODELS & ENUMS
# ============================================================
class Regime(Enum):
    STABLE = auto()
    SURGE = auto()
    SATURATED = auto()
    CONFUSION = auto()
    ANOMALOUS = auto()
    PANIC = auto()


class Verdict(Enum):
    """What a policy decided, ranked by VERDICT_SEVERITY below.

    HALT is produced by no policy in this repository. It arrives by being
    read back out of a stored record -- see parse_verdict -- which is not
    the same as being unreachable, and is worse: it enters from data into
    code that never intends it. Every comparison against a verdict is
    therefore made by rank rather than by name, so a member nothing here
    emits is still ordered correctly when one shows up. Do not delete it
    on the grounds that nothing assigns it; that would turn reading an
    existing record into a KeyError.
    """

    ALLOW = auto()
    THROTTLE = auto()
    ISOLATE = auto()
    HALT = auto()


REGIME_SEVERITY = {
    Regime.STABLE: 1,
    Regime.SURGE: 2,
    Regime.SATURATED: 3,
    Regime.CONFUSION: 4,
    Regime.ANOMALOUS: 5,
    Regime.PANIC: 6,
}

#: Verdict severity, ascending. Regimes have had an ordering since the
#: beginning; verdicts did not, so every place that needed one wrote
#: `== Verdict.ISOLATE` and silently meant "severe". That is correct only
#: while ISOLATE is the most severe verdict that exists, and HALT has been
#: declared above it the whole time. Each of those comparisons answered
#: "is this severe?" with "no" for the single most severe verdict in the
#: vocabulary.
VERDICT_SEVERITY = {
    Verdict.ALLOW: 1,
    Verdict.THROTTLE: 2,
    Verdict.ISOLATE: 3,
    Verdict.HALT: 4,
}

#: Adding a Verdict member without ranking it would reintroduce exactly the
#: bug this table exists to close, so the omission is refused at import
#: rather than discovered when the new verdict fails to escalate.
_UNRANKED = set(Verdict) - set(VERDICT_SEVERITY)
if _UNRANKED:
    raise RuntimeError(
        f"VERDICT_SEVERITY does not rank {sorted(v.name for v in _UNRANKED)}; "
        f"rank every Verdict member or severity comparisons silently mis-order"
    )

#: The severity at or above which a decision is a governance event rather
#: than a routing hint: it sets CRITICAL status and therefore requires an
#: escalation log.
ESCALATION_THRESHOLD = VERDICT_SEVERITY[Verdict.ISOLATE]

#: What an unreadable verdict is worth. See verdict_severity.
_MAX_VERDICT_SEVERITY = max(VERDICT_SEVERITY.values())


def verdict_severity(verdict: "Verdict | str | None") -> int:
    """Rank a verdict given as a member or as a stored name.

    FAILS CLOSED, DELIBERATELY. A name this kernel does not recognise, and
    a decision that recorded no verdict at all, both rank at maximum
    severity rather than minimum. The alternative -- treating what we
    cannot read as ALLOW -- means a corrupted, forged or simply newer
    record is waved through, and it is waved through most quietly exactly
    when something is wrong with it.

    An unreadable verdict is therefore escalated to a human, which is the
    same answer this kernel gives everywhere else it cannot assess
    something. The caller is expected to say so in the record: see the
    bridge's `unrecognised_verdict` flag reason.
    """
    if isinstance(verdict, Verdict):
        return VERDICT_SEVERITY[verdict]
    if isinstance(verdict, str):
        member = Verdict.__members__.get(verdict)
        if member is not None:
            return VERDICT_SEVERITY[member]
    return _MAX_VERDICT_SEVERITY


def parse_verdict(name: "str | None") -> Verdict:
    """A stored verdict name as a member, failing closed on anything this
    kernel cannot read -- see verdict_severity for why that direction."""
    if isinstance(name, str):
        member = Verdict.__members__.get(name)
        if member is not None:
            return member
    return max(VERDICT_SEVERITY, key=VERDICT_SEVERITY.get)


@dataclass(frozen=True)
class EngineCeilings:
    MAX_LATENCY: float = 600.0
    MAX_ABORT_RATE: float = 1.0
    MAX_REENTRY_RATE: float = 10.0
    MAX_LOAD_DEPTH: float = 5000.0
    MIN_DETERMINISM: float = 0.0
    MAX_DETERMINISM: float = 1.0


@dataclass(frozen=True)
class LyapunovConfig:
    w_latency: float = 0.20
    w_abort: float = 0.30
    w_reentry: float = 0.20
    w_load: float = 0.15
    w_det: float = 0.15


@dataclass(frozen=True)
class TrafficPayload:
    latency: float
    abort_rate: float
    reentry_rate: float
    load_depth: float
    determinism_index: float


@dataclass(frozen=True)
class Provenance:
    actor_id: str
    policy_id: str
    justification: str


@dataclass(frozen=True)
class NormalizedEvent:
    event_id: str
    entity_id: str
    sequence_no: int
    event_type: str
    delta: Dict[str, Any]
    provenance: Provenance


@dataclass(frozen=True)
class StateSnapshot:
    entity_id: str
    last_sequence_no: int
    context: Dict[str, Any]


@dataclass(frozen=True)
class RuleResult:
    passed: bool
    rule: str
    details: Optional[str] = None


# ============================================================
# WRITE-AHEAD LOG (WAL SYSTEM AUDIT ENGINE)
# ============================================================
class WAL:
    def __init__(self, path: str):
        self.path = path
        if os.path.dirname(path):
            os.makedirs(os.path.dirname(path), exist_ok=True)
        self.f = open(path, "a+", encoding="utf-8", buffering=1)

    def append(self, record: Dict[str, Any]) -> None:
        self.f.write(canonical(record) + "\n")

    def close(self) -> None:
        self.f.close()

    def replay(self) -> List[Dict[str, Any]]:
        self.f.flush()
        with open(self.path, "r", encoding="utf-8") as f:
            return [json.loads(x) for x in f if x.strip()]


# ============================================================
# CRYPTOGRAPHIC SECURITY LAYER
# ============================================================
def sign(state: Dict[str, Any], key: bytes) -> str:
    payload = canonical(public(state)).encode()
    return hmac.new(key, payload, hashlib.sha256).hexdigest()


def verify(state: Dict[str, Any], key: bytes) -> bool:
    sig = state.get("_sig")
    if not sig:
        return False
    return hmac.compare_digest(sig, sign(state, key))


# ============================================================
# HASH CHAINING LEDGER (TAMPER-EVIDENT EVENT STORE)
# ============================================================
class HashStrategy(Protocol):
    def compute(self, previous_hash: str, event: NormalizedEvent) -> str:
        ...


class SHA256Hash:
    def compute(self, previous_hash: str, event: NormalizedEvent) -> str:
        payload = {
            "previous_hash": previous_hash,
            "event_id": event.event_id,
            "entity_id": event.entity_id,
            "sequence_no": event.sequence_no,
            "event_type": event.event_type,
            "delta": event.delta,
            "provenance": {
                "actor_id": event.provenance.actor_id,
                "policy_id": event.provenance.policy_id,
                "justification": event.provenance.justification,
            },
        }
        encoded = json.dumps(payload, sort_keys=True).encode()
        return hashlib.sha256(encoded).hexdigest()


class EventStore:
    def __init__(self, hash_strategy: Optional[HashStrategy] = None):
        self._entity_streams: Dict[str, List[NormalizedEvent]] = {}
        self._entity_heads: Dict[str, str] = {}
        # Every link, not just the head. Keeping only the head proves that a
        # stream changed but never which event changed, and verify_chain needs
        # to name the divergence point for the answer to be actionable.
        self._entity_hashes: Dict[str, List[str]] = {}
        self._hash_strategy = hash_strategy or SHA256Hash()

    def append(self, entity_id: str, event_type: str, delta: Dict[str, Any],
               provenance: Provenance) -> Tuple[NormalizedEvent, str]:
        stream = self._entity_streams.setdefault(entity_id, [])
        sequence_no = len(stream) + 1

        event = NormalizedEvent(
            event_id=str(uuid.uuid4()),
            entity_id=entity_id,
            sequence_no=sequence_no,
            event_type=event_type,
            delta=copy.deepcopy(delta),
            provenance=provenance,
        )

        previous_hash = self._entity_heads.get(entity_id, "GENESIS")
        current_hash = self._hash_strategy.compute(previous_hash, event)

        stream.append(event)
        self._entity_hashes.setdefault(entity_id, []).append(current_hash)
        self._entity_heads[entity_id] = current_hash
        return event, current_hash

    def events_since(self, entity_id: str, sequence_no: int) -> List[NormalizedEvent]:
        stream = self._entity_streams.get(entity_id, [])
        return [e for e in stream if e.sequence_no > sequence_no]

    def stream_for(self, entity_id: str) -> List[NormalizedEvent]:
        return list(self._entity_streams.get(entity_id, []))

    def head_hash(self, entity_id: str) -> str:
        return self._entity_heads.get(entity_id, "GENESIS")

    def verify_chain(self, entity_id: str) -> Tuple[bool, Optional[int]]:
        """Recompute the chain from GENESIS and compare it to the head.

        This section is headed "TAMPER-EVIDENT EVENT STORE" and the chaining
        that earns the name was already here, but the store exposed no way to
        check it. The only verification in the repository was ten lines inside
        the demo block at the bottom of ats_governance_kernel_bridge.py,
        hardcoded to a single candidate id and reachable by no caller. A
        control that exists only in a demo is not available to the system it
        is supposed to protect.

        It also could only answer yes or no. This walks the recorded links, so
        it can say which event diverged.

        Returns (True, None) if the stream reproduces the head, else
        (False, sequence_no) naming the earliest event that does not match.
        The sequence number is the point of divergence: everything at or after
        it is suspect, everything before it is confirmed intact.
        """
        expected_head = self._entity_heads.get(entity_id)
        if expected_head is None:
            # No stream. Consistent only if nothing claims to be here.
            return (entity_id not in self._entity_streams), None

        running = "GENESIS"
        recorded = self._entity_hashes.get(entity_id, [])
        for index, event in enumerate(self._entity_streams.get(entity_id, [])):
            running = self._hash_strategy.compute(running, event)
            # Compare each link against the one written at append time. Only
            # the head was kept before, which is enough to prove a stream was
            # altered but not to say where -- and "something in this ledger
            # changed" is not an answer anyone can act on.
            if index < len(recorded) and running != recorded[index]:
                return False, event.sequence_no

        # Every link matched what was recorded, so the head must agree too;
        # if it does not, the head itself was altered rather than an event.
        return running == expected_head, None


# ============================================================
# STATE REDUCERS & POLICY VM
# ============================================================
class Reducer(Protocol):
    def apply(self, context: Dict[str, Any], event: NormalizedEvent) -> Dict[str, Any]:
        ...


class UnknownEventType(ValueError):
    """A reducer was handed an event type it has no rule for.

    Carries the identifying fields so an operator can find the exact event in
    the stream rather than only learning that some event, somewhere, was not
    understood.
    """

    def __init__(self, event: NormalizedEvent) -> None:
        self.event_type = event.event_type
        self.event_id = event.event_id
        self.entity_id = event.entity_id
        self.sequence_no = event.sequence_no
        super().__init__(
            f"unknown event type {event.event_type!r} "
            f"(entity={event.entity_id}, seq={event.sequence_no}, "
            f"event_id={event.event_id})"
        )


class GovernanceCoreReducer:
    # The event types this reducer has rules for. A class attribute rather
    # than a chain of literals so it can be read -- by the check below, and by
    # a test asserting it matches what callers actually emit.
    HANDLED_EVENT_TYPES = frozenset({
        "telemetry_update", "escalation", "status_change",
        "hiring_decision", "escalation_logged",
    })

    def apply(self, context: Dict[str, Any], event: NormalizedEvent) -> Dict[str, Any]:
        # Both generations of this reducer's ancestor raised here. This one
        # fell off the end and returned the state unchanged, which is not a
        # smaller failure than raising -- it is a larger one. An unrecognised
        # event produces after == before, every before/after invariant holds
        # trivially, and the transition is reported as governed and clean. A
        # one-character typo in an event type turned a decision that violates
        # the manifest into one that passes it.
        if event.event_type not in self.HANDLED_EVENT_TYPES:
            raise UnknownEventType(event)

        next_state = copy.deepcopy(context)
        if event.event_type == "telemetry_update":
            next_state["metrics"] = event.delta
        elif event.event_type == "escalation":
            next_state["escalation_logged"] = True
        elif event.event_type == "status_change":
            next_state["system_status"] = event.delta.get("status")
        elif event.event_type == "hiring_decision":
            next_state["last_decision"] = event.delta
            # Ranked, not compared by name. `== "ISOLATE"` read as "is this
            # severe?" and answered no for HALT, the one verdict above it:
            # a HALT decision set no CRITICAL status, so
            # critical_requires_escalation never fired, no escalation was
            # required, and the strongest stop this vocabulary has produced
            # a transition the auditor reported as governed and clean. The
            # same silence the unknown-event-type check above exists to
            # stop, one branch further down.
            if verdict_severity(event.delta.get("verdict")) >= ESCALATION_THRESHOLD:
                next_state["system_status"] = "CRITICAL"
        elif event.event_type == "escalation_logged":
            next_state["escalation_logged"] = True
        return next_state


class Policy:
    def __init__(self, name: str,
                 predicate: Callable[[Dict[str, Any]], bool],
                 action: Callable[[Dict[str, Any]], Dict[str, Any]]):
        self.name = name
        self.predicate = predicate
        self.action = action


class PolicyVM:
    def __init__(self, policies: List[Policy]):
        self.policies = sorted(policies, key=lambda p: p.name)

    def step(self, state: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
        """Run all policies. Return (new_state, list_of_triggered_policy_names)."""
        snap = normalize(dict(state))
        out = normalize(dict(state))
        triggered: List[str] = []

        for p in self.policies:
            try:
                if p.predicate(snap):
                    out = normalize(p.action(out))
                    triggered.append(p.name)
            except Exception:
                logger.exception("policy VM predicate failed: %s", p.name)
                raise

        return out, triggered


# ============================================================
# MANIFEST AUDITOR
# ============================================================
@dataclass(frozen=True)
class Manifest:
    manifest_id: str
    version: str
    invariants: Dict[str, Callable[
        [Mapping[str, Any], NormalizedEvent, Mapping[str, Any]], Tuple[bool, str]
    ]] = field(default_factory=dict)


def critical_requires_escalation(
    before: Mapping[str, Any], event: NormalizedEvent, after: Mapping[str, Any]
) -> Tuple[bool, str]:
    if after.get("system_status") == "CRITICAL" and not after.get("escalation_logged", False):
        return False, "CRITICAL status without escalation log"
    return True, "OK"


class GovernanceAuditor:
    def __init__(self, manifest: Manifest, reducer: Reducer) -> None:
        self._manifest = manifest
        self._reducer = reducer

    def verify_transition(self, before: Dict[str, Any], event: NormalizedEvent
                          ) -> Tuple[bool, List[str]]:
        # Caught by its specific type, never broadly. A generic `except
        # Exception` here would let an unrelated bug inside an invariant
        # surface as an orderly governance refusal -- a broken call wearing a
        # principled refusal's clothes, which is strictly harder to diagnose
        # than a crash. Only "I do not know this event type" is converted, and
        # it is converted into a refusal rather than propagated so the caller's
        # remediation path (auto-escalation on breach) runs instead of the
        # whole evaluation aborting.
        try:
            after = self._reducer.apply(before, event)
        except UnknownEventType as exc:
            return False, [f"unknown_event_type: {exc}"]

        before_view = MappingProxyType(before)
        after_view = MappingProxyType(after)
        errors = []

        for name, invariant in self._manifest.invariants.items():
            ok, msg = invariant(before_view, event, after_view)
            if not ok:
                errors.append(f"{name}: {msg}")
        return len(errors) == 0, errors


# ============================================================
# STOCHASTIC ONLINE STATISTICS & LYAPUNOV STABILITY
# ============================================================
class Welford:
    def __init__(self) -> None:
        self.n = 0
        self.mean = 0.0
        self.m2 = 0.0

    def update(self, x: float) -> None:
        self.n += 1
        delta = x - self.mean
        self.mean += delta / self.n
        self.m2 += delta * (x - self.mean)

    def std(self) -> float:
        if self.n < 2:
            return 1e-9
        return math.sqrt(self.m2 / (self.n - 1))


class SystemAnalytics:
    def __init__(self) -> None:
        self.lock = Lock()
        self.stats = {
            "latency": Welford(), "abort": Welford(),
            "reentry": Welford(), "load": Welford(), "det": Welford(),
        }

    def update(self, p: TrafficPayload) -> Dict[str, Tuple[float, float]]:
        with self.lock:
            self.stats["latency"].update(p.latency)
            self.stats["abort"].update(p.abort_rate)
            self.stats["reentry"].update(p.reentry_rate)
            self.stats["load"].update(p.load_depth)
            self.stats["det"].update(p.determinism_index)
            return self.snapshot()

    def snapshot(self) -> Dict[str, Tuple[float, float]]:
        return {k: (v.mean, v.std()) for k, v in self.stats.items()}


def compute_entropy(payload: TrafficPayload, c: EngineCeilings) -> float:
    vals = [
        payload.latency / c.MAX_LATENCY,
        payload.abort_rate,
        payload.reentry_rate / c.MAX_REENTRY_RATE,
        payload.load_depth / c.MAX_LOAD_DEPTH,
        payload.determinism_index,
    ]
    s = sum(vals)
    if s == 0:
        return 0.0
    e = 0.0
    for v in vals:
        if v > 0:
            p = v / s
            e -= p * math.log2(p)
    return e


def compute_lyapunov(p: TrafficPayload, stats: Dict[str, Tuple[float, float]],
                     cfg: LyapunovConfig) -> float:
    def z(x, mean, std):
        return (x - mean) / std if std > 1e-6 else x

    return (
        cfg.w_latency * z(p.latency, *stats["latency"]) ** 2 +
        cfg.w_abort * z(p.abort_rate, *stats["abort"]) ** 2 +
        cfg.w_reentry * z(p.reentry_rate, *stats["reentry"]) ** 2 +
        cfg.w_load * z(p.load_depth, *stats["load"]) ** 2 +
        cfg.w_det * z(p.determinism_index, *stats["det"]) ** 2
    )


class RegimeClassifier:
    def __init__(self) -> None:
        self.analytics = SystemAnalytics()

    def classify(self, p: TrafficPayload) -> Tuple[Regime, float, float]:
        stats = self.analytics.update(p)
        ceilings = EngineCeilings()
        e = compute_entropy(p, ceilings)
        energy = compute_lyapunov(p, stats, LyapunovConfig())

        if p.determinism_index > 0.85 and energy > 3:
            return Regime.ANOMALOUS, e, energy
        if e > 2.0:
            return Regime.CONFUSION, e, energy
        if p.load_depth > 0.85 * ceilings.MAX_LOAD_DEPTH:
            return Regime.SATURATED, e, energy

        mean, std = stats["latency"]
        if p.latency > mean + 2 * std:
            return Regime.SURGE, e, energy

        return Regime.STABLE, e, energy


class GovernanceChassis:
    def __init__(self) -> None:
        self.classifier = RegimeClassifier()
        self.state = Regime.STABLE
        self.lock = Lock()

    def step(self, p: TrafficPayload) -> Dict[str, Any]:
        regime, e, energy = self.classifier.classify(p)
        with self.lock:
            prev = self.state
            if REGIME_SEVERITY[regime] > REGIME_SEVERITY[self.state]:
                self.state = regime
            elif REGIME_SEVERITY[regime] < REGIME_SEVERITY[self.state]:
                if self.state == Regime.STABLE:
                    self.state = regime
        return {
            "regime": self.state.name,
            "classified_as": regime.name,
            "previous": prev.name,
            "entropy": e,
            "energy": energy,
        }


# ============================================================
# EXECUTION RUNTIME
# ============================================================
class SnapshotPolicy(Protocol):
    def should_snapshot(self, events_since_last: int) -> bool: ...


class EveryNEventsSnapshot:
    def __init__(self, n: int = 50):
        self._n = n
    def should_snapshot(self, events_since_last: int) -> bool:
        return events_since_last >= self._n


class ExecutionRuntime:
    def __init__(self, store: EventStore, reducer: Reducer,
                 snapshot_policy: Optional[SnapshotPolicy] = None) -> None:
        self._store = store
        self._reducer = reducer
        self._snapshot_policy = snapshot_policy or EveryNEventsSnapshot(50)
        self._snapshots: Dict[str, StateSnapshot] = {}

    def materialize_state(self, entity_id: str) -> Mapping[str, Any]:
        snapshot = self._snapshots.get(
            entity_id,
            StateSnapshot(entity_id=entity_id, last_sequence_no=0, context={})
        )
        context = copy.deepcopy(snapshot.context)
        events = self._store.events_since(entity_id, snapshot.last_sequence_no)

        for event in events:
            context = self._reducer.apply(context, event)

        if events and self._snapshot_policy.should_snapshot(len(events)):
            self._snapshots[entity_id] = StateSnapshot(
                entity_id=entity_id,
                last_sequence_no=events[-1].sequence_no,
                context=copy.deepcopy(context),
            )
        return MappingProxyType(context)

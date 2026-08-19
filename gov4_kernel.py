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
import time
import re
import uuid
import copy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from threading import Lock
from types import MappingProxyType
from typing import Any, Callable, Dict, List, Mapping, Optional, Protocol, Tuple

import numpy as np

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
        self._entity_heads[entity_id] = current_hash
        return event, current_hash

    def events_since(self, entity_id: str, sequence_no: int) -> List[NormalizedEvent]:
        stream = self._entity_streams.get(entity_id, [])
        return [e for e in stream if e.sequence_no > sequence_no]

    def stream_for(self, entity_id: str) -> List[NormalizedEvent]:
        return list(self._entity_streams.get(entity_id, []))

    def head_hash(self, entity_id: str) -> str:
        return self._entity_heads.get(entity_id, "GENESIS")


# ============================================================
# STATE REDUCERS & POLICY VM
# ============================================================
class Reducer(Protocol):
    def apply(self, context: Dict[str, Any], event: NormalizedEvent) -> Dict[str, Any]:
        ...


class GovernanceCoreReducer:
    def apply(self, context: Dict[str, Any], event: NormalizedEvent) -> Dict[str, Any]:
        next_state = copy.deepcopy(context)
        if event.event_type == "telemetry_update":
            next_state["metrics"] = event.delta
        elif event.event_type == "escalation":
            next_state["escalation_logged"] = True
        elif event.event_type == "status_change":
            next_state["system_status"] = event.delta.get("status")
        elif event.event_type == "hiring_decision":
            next_state["last_decision"] = event.delta
            if event.delta.get("verdict") == "ISOLATE":
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
        after = self._reducer.apply(before, event)
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

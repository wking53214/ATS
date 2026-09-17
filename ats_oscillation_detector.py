"""
Oscillation Detector for ATS: identifies repeated normalized outputs/decisions.

Tracks a bounded history of normalized audit events, decisions, and findings
to detect oscillation patterns. Exposed as a non-authoritative diagnostic signal
in the audit trail and governance pipeline.

This detector is deterministic, cheap, local, and has no governance authority.
It reports but does not execute governance actions or modify hiring decisions.
"""

from collections import deque
from typing import Dict, Any, List, Optional
import json


class OscillationDetector:
    """
    Detect repeated normalized outputs within a bounded history.

    This detector maintains a sliding window of observed normalized outputs
    (decisions, audit events, findings). When a repeated output is observed,
    it signals oscillation detected.

    Args:
        max_history: Maximum number of normalized outputs to retain in history.
            Default 64 (larger than content-polish-pipeline's 32 to account for
            batch processing in ATS). Once the limit is reached, the oldest
            observation is discarded when a new one is added.

    Attributes:
        history: Deque of observed normalized outputs (newest at right).
        event_type_counts: Dict tracking how many times each event type repeats.
    """

    def __init__(self, max_history: int = 64):
        """Initialize the detector with a bounded history."""
        if max_history < 1:
            raise ValueError(f"max_history must be >= 1, got {max_history}")
        self.history = deque(maxlen=max_history)
        self.event_type_counts: Dict[str, int] = {}

    def observe(self, output: str, event_type: Optional[str] = None) -> bool:
        """
        Observe an output and check if it repeats earlier history.

        Normalizes the output (strip whitespace, lowercase) before comparison.
        The normalized form is added to the history after the check.

        Args:
            output: Raw output/decision text to observe.
            event_type: Optional event type label (e.g., "BIAS_DETECTED", "APPROVED")
                for additional tracking.

        Returns:
            True if the normalized output was already in history (oscillation
            detected). False if it is a new observation.

        Example:
            >>> detector = OscillationDetector()
            >>> detector.observe("BIAS DETECTED: geographic penalty")  # False
            False
            >>> detector.observe("Bias detected: geographic penalty")   # True
            True
        """
        normalized = output.strip().lower()
        repeated = normalized in self.history
        self.history.append(normalized)

        # Track event type occurrences for additional diagnostics
        if event_type:
            self.event_type_counts[event_type] = self.event_type_counts.get(event_type, 0) + (1 if repeated else 0)

        return repeated

    def observe_decision_dict(self, decision: Dict[str, Any]) -> bool:
        """
        Observe a decision dictionary and check for recurrence.

        Normalizes by converting to sorted JSON for deterministic comparison.

        Args:
            decision: Decision dict with candidate_id, score, decision, reason, etc.

        Returns:
            True if this exact decision (normalized) was already observed.
        """
        # Canonical form: sorted JSON without timestamp/hash-chain fields
        canonical = {k: v for k, v in decision.items()
                    if k not in {"timestamp", "hash", "hmac", "sequence", "event_id"}}
        normalized = json.dumps(canonical, sort_keys=True).strip().lower()
        repeated = normalized in self.history
        self.history.append(normalized)
        return repeated

    def reset(self):
        """Clear all history. Use to start a new observation session (batch)."""
        self.history.clear()
        self.event_type_counts.clear()

    def get_history(self) -> List[str]:
        """Return a snapshot of current history (newest at end)."""
        return list(self.history)

    def get_diagnostics(self) -> Dict[str, Any]:
        """Return diagnostic information about oscillation patterns."""
        return {
            "history_size": len(self.history),
            "max_history": self.history.maxlen,
            "event_type_repetitions": self.event_type_counts,
            "is_potentially_oscillating": any(count > 2 for count in self.event_type_counts.values()),
        }

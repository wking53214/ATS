"""
Tests for OscillationDetector and its integration with ATS audit trail.

Run with: python -m pytest test_ats_oscillation_detector.py -v
"""

import unittest
import json
from ats_oscillation_detector import OscillationDetector
from ats_governor_fixed import CryptoAuditTrail


class TestOscillationDetectorBasics(unittest.TestCase):
    """Basic OscillationDetector functionality tests."""

    def setUp(self):
        self.detector = OscillationDetector(max_history=32)

    def test_first_observation_returns_false(self):
        """First observation should return False (not yet repeated)."""
        result = self.detector.observe("BIAS DETECTED: geographic penalty")
        self.assertFalse(result)

    def test_exact_repeat_returns_true(self):
        """Second identical observation should return True."""
        self.detector.observe("BIAS DETECTED: geographic penalty")
        result = self.detector.observe("BIAS DETECTED: geographic penalty")
        self.assertTrue(result)

    def test_normalized_repeat_whitespace(self):
        """Whitespace variations should normalize to same observation."""
        self.detector.observe("BIAS DETECTED: geographic penalty")
        result = self.detector.observe("  bias detected: geographic penalty  ")
        self.assertTrue(result)

    def test_normalized_repeat_case(self):
        """Case variations should normalize to same observation."""
        self.detector.observe("BIAS DETECTED: geographic penalty")
        result = self.detector.observe("bias detected: geographic penalty")
        self.assertTrue(result)

    def test_distinct_events_return_false(self):
        """Different events should not trigger oscillation."""
        self.detector.observe("BIAS DETECTED: geographic penalty")
        result = self.detector.observe("BIAS DETECTED: demographic proxy")
        self.assertFalse(result)

    def test_reset_clears_history(self):
        """reset() should clear all history."""
        self.detector.observe("BIAS DETECTED: geographic penalty")
        self.detector.reset()
        result = self.detector.observe("BIAS DETECTED: geographic penalty")
        self.assertFalse(result)

    def test_bounded_history_eviction(self):
        """Oldest observation should be evicted when max_history is reached."""
        small_detector = OscillationDetector(max_history=3)
        small_detector.observe("Event A")
        small_detector.observe("Event B")
        small_detector.observe("Event C")
        # History is now [A, B, C]
        history = small_detector.get_history()
        self.assertEqual(len(history), 3)
        self.assertEqual(history, ["event a", "event b", "event c"])

        # Add fourth event; A should be evicted
        small_detector.observe("Event D")
        history = small_detector.get_history()
        self.assertEqual(len(history), 3)
        self.assertEqual(history, ["event b", "event c", "event d"])

        # Now A is gone; observing it should return False (new observation)
        result = small_detector.observe("Event A")
        self.assertFalse(result)

    def test_get_history(self):
        """get_history() should return current observations in order."""
        self.detector.observe("Event A")
        self.detector.observe("Event B")
        self.detector.observe("Event C")
        history = self.detector.get_history()
        self.assertEqual(history, ["event a", "event b", "event c"])

    def test_constructor_rejects_invalid_max_history(self):
        """max_history must be >= 1."""
        with self.assertRaises(ValueError):
            OscillationDetector(max_history=0)
        with self.assertRaises(ValueError):
            OscillationDetector(max_history=-1)

    def test_observe_with_event_type(self):
        """Observe with event_type should track repetition counts."""
        detector = OscillationDetector()
        detector.observe("CRITICAL: bias found", event_type="BIAS_ALERT")
        detector.observe("CRITICAL: bias found", event_type="BIAS_ALERT")
        diag = detector.get_diagnostics()
        self.assertEqual(diag["event_type_repetitions"]["BIAS_ALERT"], 1)

    def test_observe_decision_dict(self):
        """Observe decision dicts with canonical JSON normalization."""
        decision1 = {
            "candidate_id": "C001",
            "score": 0.85,
            "decision": "APPROVED",
            "reason": "Meets requirements"
        }
        decision2 = {
            "candidate_id": "C001",
            "score": 0.85,
            "decision": "APPROVED",
            "reason": "Meets requirements"
        }
        result1 = self.detector.observe_decision_dict(decision1)
        result2 = self.detector.observe_decision_dict(decision2)
        self.assertFalse(result1)
        self.assertTrue(result2)

    def test_decision_dict_ignores_metadata(self):
        """Decision dict comparison should ignore timestamp/hash fields."""
        decision1 = {
            "candidate_id": "C001",
            "score": 0.85,
            "decision": "APPROVED",
            "timestamp": "2026-08-30T12:00:00Z",
            "hash": "abc123"
        }
        decision2 = {
            "candidate_id": "C001",
            "score": 0.85,
            "decision": "APPROVED",
            "timestamp": "2026-08-30T12:01:00Z",  # Different timestamp
            "hash": "def456"  # Different hash
        }
        result1 = self.detector.observe_decision_dict(decision1)
        result2 = self.detector.observe_decision_dict(decision2)
        # Should detect as repeat despite different metadata
        self.assertFalse(result1)
        self.assertTrue(result2)


class TestOscillationInAuditTrail(unittest.TestCase):
    """Test OscillationDetector integration with CryptoAuditTrail."""

    def setUp(self):
        self.audit_trail = CryptoAuditTrail(log_file="test_audit.log")

    def tearDown(self):
        import os
        if os.path.exists("test_audit.log"):
            os.remove("test_audit.log")

    def test_audit_trail_includes_oscillation_signal(self):
        """Logged events should include oscillation_detected field."""
        self.audit_trail.log("DECISION", "Candidate C001: APPROVED")
        event = self.audit_trail.events[0]
        self.assertIn("oscillation_detected", event)
        self.assertFalse(event["oscillation_detected"])

    def test_repeated_event_detected_in_audit_trail(self):
        """Repeated events should be flagged with oscillation_detected=True."""
        self.audit_trail.log("BIAS_ALERT", "Geographic penalty detected for candidates in TX")
        self.audit_trail.log("BIAS_ALERT", "Geographic penalty detected for candidates in TX")

        event1 = self.audit_trail.events[0]
        event2 = self.audit_trail.events[1]

        self.assertFalse(event1["oscillation_detected"])
        self.assertTrue(event2["oscillation_detected"])

    def test_different_events_not_flagged(self):
        """Different events should not trigger oscillation flag."""
        self.audit_trail.log("DECISION", "Candidate C001: APPROVED")
        self.audit_trail.log("DECISION", "Candidate C002: REJECTED")

        event1 = self.audit_trail.events[0]
        event2 = self.audit_trail.events[1]

        self.assertFalse(event1["oscillation_detected"])
        self.assertFalse(event2["oscillation_detected"])

    def test_normalized_repeat_detected(self):
        """Normalized variations of events should be detected as repeats."""
        self.audit_trail.log("ALERT", "BIAS DETECTED")
        self.audit_trail.log("ALERT", "bias detected")  # Case variation

        event2 = self.audit_trail.events[1]
        self.assertTrue(event2["oscillation_detected"])

    def test_reset_oscillation_detector(self):
        """Resetting detector should clear history for new batch."""
        self.audit_trail.log("ALERT", "Bias found in round 1")
        self.audit_trail.reset_oscillation_detector()
        self.audit_trail.log("ALERT", "Bias found in round 1")

        # After reset, the same event should not be flagged as repeat
        event2 = self.audit_trail.events[1]
        self.assertFalse(event2["oscillation_detected"])

    def test_oscillation_diagnostics(self):
        """get_oscillation_diagnostics() should return diagnostic info."""
        self.audit_trail.log("ALERT", "Type A")
        self.audit_trail.log("ALERT", "Type A")
        self.audit_trail.log("ALERT", "Type B")
        self.audit_trail.log("ALERT", "Type B")
        self.audit_trail.log("ALERT", "Type B")

        diag = self.audit_trail.get_oscillation_diagnostics()
        self.assertEqual(diag["history_size"], 5)
        self.assertIn("event_type_repetitions", diag)
        self.assertTrue(diag["is_potentially_oscillating"])

    def test_oscillation_doesnt_affect_hash_chain(self):
        """Oscillation detection should not break hash chain."""
        self.audit_trail.log("EVENT", "First")
        self.audit_trail.log("EVENT", "First")  # Repeat
        self.audit_trail.log("EVENT", "Second")

        integrity = self.audit_trail.verify_integrity()
        self.assertTrue(integrity["valid"])
        self.assertEqual(len(integrity["violations"]), 0)

    def test_oscillation_in_audit_report(self):
        """Events should be retrievable with oscillation status."""
        self.audit_trail.log("FINDING", "Geographic bias: 40% gap")
        self.audit_trail.log("FINDING", "Geographic bias: 40% gap")

        events = self.audit_trail.events
        self.assertEqual(len(events), 2)
        self.assertFalse(events[0]["oscillation_detected"])
        self.assertTrue(events[1]["oscillation_detected"])


class TestGovernanceNeutrality(unittest.TestCase):
    """Verify oscillation detection is non-authoritative."""

    def test_oscillation_doesnt_change_event_type(self):
        """Oscillation detection should not modify event_type."""
        audit_trail = CryptoAuditTrail(log_file="test_gov.log")
        audit_trail.log("DECISION", "APPROVED")
        audit_trail.log("DECISION", "APPROVED")  # Repeat

        event2 = audit_trail.events[1]
        self.assertEqual(event2["event_type"], "DECISION")
        self.assertEqual(event2["details"], "APPROVED")

    def test_oscillation_doesnt_change_severity(self):
        """Oscillation detection should not modify severity."""
        audit_trail = CryptoAuditTrail(log_file="test_gov.log")
        audit_trail.log("ALERT", "Critical bias", severity="CRITICAL")
        audit_trail.log("ALERT", "Critical bias", severity="CRITICAL")  # Repeat

        event2 = audit_trail.events[1]
        self.assertEqual(event2["severity"], "CRITICAL")

    def test_oscillation_signal_only(self):
        """Oscillation is purely informational, not prescriptive."""
        audit_trail = CryptoAuditTrail(log_file="test_gov.log")

        # Log a decision three times (oscillating)
        audit_trail.log("DECISION", "Candidate C001: APPROVED")
        audit_trail.log("DECISION", "Candidate C001: APPROVED")
        audit_trail.log("DECISION", "Candidate C001: APPROVED")

        # Verify: only oscillation_detected flag is added, nothing else changes
        for i, event in enumerate(audit_trail.events):
            self.assertEqual(event["event_type"], "DECISION")
            self.assertEqual(event["details"], "Candidate C001: APPROVED")
            self.assertIn("oscillation_detected", event)

        # Verify: second and third are flagged, but decision unchanged
        self.assertFalse(audit_trail.events[0]["oscillation_detected"])
        self.assertTrue(audit_trail.events[1]["oscillation_detected"])
        self.assertTrue(audit_trail.events[2]["oscillation_detected"])

    def tearDown(self):
        import os
        for f in ["test_audit.log", "test_gov.log"]:
            if os.path.exists(f):
                os.remove(f)


if __name__ == "__main__":
    unittest.main()

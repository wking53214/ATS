"""Tests for ats_counter_system.py, the module behind the README's
"legal evidence" claim. Until 2026-09-08 it had no automated test.

Each detector is exercised on both sides of its threshold so a detector that
stops detecting (or never could) fails here. The fixture pools are built so
that exactly one bias is present at a time.
"""

import pytest

from ats_counter_system import (
    AuditReportValidator,
    BiasNeutralizationEngine,
    BiasSignature,
    CounterATS,
    DecisionFunctionInverter,
    SyntheticValidationBreaker,
)


def _cand(i, name="Bob Lund", miles=10, jobs=2, years=8):
    return {
        "id": f"{i:03d}",
        "name": name,
        "location_distance_miles": miles,
        "employment_history": [f"job{k}" for k in range(jobs)],
        "years_professional": years,
    }


def _dec(i, decision):
    return {"id": f"{i:03d}", "decision": decision}


# Names chosen so every candidate sits on the same side of the vowel-ratio
# split (all <= 0.4), and job/years ratios are all "stable", so the only
# attribute that varies below is distance.
def geographic_pool():
    cands, decs = [], []
    for i in range(10):
        remote = i >= 5
        cands.append(_cand(i, miles=500 if remote else 5))
        decs.append(_dec(i, "REJECTED" if remote else "APPROVED"))
    return cands, decs


def fair_pool():
    cands, decs = [], []
    for i in range(10):
        remote = i >= 5
        cands.append(_cand(i, miles=500 if remote else 5))
        # Same rejection rate on both sides: 2 of 5 rejected.
        decs.append(_dec(i, "REJECTED" if i % 5 < 2 else "APPROVED"))
    return cands, decs


class TestDecisionFunctionInverter:
    def test_geographic_penalty_detected(self):
        inv = DecisionFunctionInverter()
        inv.ingest_decisions(*geographic_pool())
        sigs = inv.detect_correlated_rejection_patterns()
        assert [s.bias_type for s in sigs] == ["geographic_penalty"]
        sig = sigs[0]
        assert sig.hidden_factor == "location_distance_miles"
        assert sig.correlation_strength == pytest.approx(1.0)
        assert sig.evidence_confidence == pytest.approx(0.95)  # capped
        assert sorted(sig.affected_candidates) == [f"{i:03d}" for i in range(5, 10)]

    def test_equal_rates_produce_no_signature(self):
        inv = DecisionFunctionInverter()
        inv.ingest_decisions(*fair_pool())
        assert inv.detect_correlated_rejection_patterns() == []

    def test_gap_at_threshold_is_not_flagged(self):
        # Exactly 30 points is not "> 0.3"; 40 points is.
        cands, decs = [], []
        for i in range(20):
            remote = i >= 10
            cands.append(_cand(i, miles=500 if remote else 5))
        # remote: 5/10 rejected; local: 2/10 rejected -> gap 0.3
        for i in range(20):
            if i < 10:
                decs.append(_dec(i, "REJECTED" if i < 2 else "APPROVED"))
            else:
                decs.append(_dec(i, "REJECTED" if i < 15 else "APPROVED"))
        inv = DecisionFunctionInverter()
        inv.ingest_decisions(cands, decs)
        assert inv.detect_correlated_rejection_patterns() == []
        decs[15] = _dec(15, "REJECTED")  # gap 0.4
        inv.ingest_decisions(cands, decs)
        assert [s.bias_type for s in inv.detect_correlated_rejection_patterns()] == ["geographic_penalty"]

    def test_volatility_penalty_detected(self):
        cands, decs = [], []
        for i in range(10):
            volatile = i >= 5
            cands.append(_cand(i, jobs=8 if volatile else 2, years=4))
            decs.append(_dec(i, "REJECTED" if volatile else "APPROVED"))
        inv = DecisionFunctionInverter()
        inv.ingest_decisions(cands, decs)
        sigs = inv.detect_correlated_rejection_patterns()
        assert [s.bias_type for s in sigs] == ["volatility_penalty"]
        assert sigs[0].hidden_factor == "turnover_rate"
        assert sigs[0].evidence_confidence == pytest.approx(0.90)

    def test_name_proxy_detected(self):
        cands, decs = [], []
        for i in range(10):
            vowel_heavy = i >= 5
            cands.append(_cand(i, name="Aiea Oue" if vowel_heavy else "Bob Lund"))
            decs.append(_dec(i, "REJECTED" if vowel_heavy else "APPROVED"))
        inv = DecisionFunctionInverter()
        inv.ingest_decisions(cands, decs)
        sigs = inv.detect_correlated_rejection_patterns()
        assert [s.bias_type for s in sigs] == ["demographic_proxy_via_name"]
        assert sigs[0].hidden_factor == "name_analysis"
        assert sigs[0].evidence_confidence == pytest.approx(0.85)

    def test_one_sided_pool_cannot_be_compared(self):
        # All candidates local: no remote group, so no geographic signature.
        cands = [_cand(i, miles=5) for i in range(6)]
        decs = [_dec(i, "REJECTED") for i in range(6)]
        inv = DecisionFunctionInverter()
        inv.ingest_decisions(cands, decs)
        assert inv.detect_correlated_rejection_patterns() == []


class TestSyntheticValidationBreaker:
    def test_circular_validation_flagged(self):
        out = SyntheticValidationBreaker().analyze_validation_circularity(0.99, 0.67)
        assert out["verdict"] == "SUSPICIOUS_VALIDATION_LOOP_DETECTED"
        assert out["gap_magnitude"] == pytest.approx(0.66)

    def test_consistent_validation_passes(self):
        out = SyntheticValidationBreaker().analyze_validation_circularity(0.80, 0.25)
        assert out["verdict"] == "VALIDATION_APPEARS_GENUINE"

    def test_homogeneous_approved_pool_flagged(self):
        pool = [{"name": "Bob Lund", "decision": "APPROVED"} for _ in range(4)]
        out = SyntheticValidationBreaker().detect_synthetic_positive_overrepresentation(pool, {})
        assert out["verdict"] == "APPROVED_POOL_SUSPICIOUSLY_HOMOGENEOUS"
        assert out["value"] == pytest.approx(0.0)

    def test_varied_approved_pool_accepted(self):
        pool = [
            {"name": "Bob Lund", "decision": "APPROVED"},
            {"name": "Aiea Oue", "decision": "APPROVED"},
            {"name": "Xyz Qwrt", "decision": "APPROVED"},
            {"name": "Eeeee", "decision": "APPROVED"},
        ]
        out = SyntheticValidationBreaker().detect_synthetic_positive_overrepresentation(pool, {})
        assert out["verdict"] == "APPROVED_POOL_VARIANCE_ACCEPTABLE"
        assert out["metric_value"] > 0.1

    @pytest.mark.parametrize("n", [0, 1, 2])
    def test_small_approved_pools_do_not_crash(self, n):
        # Regression: with one or two approved candidates the metric was read
        # before it was assigned (UnboundLocalError) until 2026-09-08.
        pool = [{"name": "Bob Lund", "decision": "APPROVED"} for _ in range(n)]
        out = SyntheticValidationBreaker().detect_synthetic_positive_overrepresentation(pool, {})
        assert out["verdict"] == "APPROVED_POOL_VARIANCE_ACCEPTABLE"
        assert out["metric_value"] == 0.0


class TestAuditReportValidator:
    def test_approval_rate_mismatch_and_implausible_metric(self):
        decs = [_dec(i, "APPROVED" if i < 4 else "REJECTED") for i in range(10)]
        report = {"approval_rate": 0.90, "bias_detection_tests": {"geographic_diversity": 0.98}}
        out = AuditReportValidator().check_for_contradiction(report, decs)
        assert [c["type"] for c in out] == ["APPROVAL_RATE_MISMATCH", "BIAS_METRIC_IMPLAUSIBLY_HIGH"]
        assert out[0]["actual"] == pytest.approx(0.4)

    def test_consistent_report_has_no_contradictions(self):
        decs = [_dec(i, "APPROVED" if i < 4 else "REJECTED") for i in range(10)]
        report = {"approval_rate": 0.41, "bias_detection_tests": {"geographic_diversity": 0.80}}
        assert AuditReportValidator().check_for_contradiction(report, decs) == []

    def test_no_decisions_is_reported_not_crashed(self):
        # Regression: an empty decision list divided by zero until 2026-09-08.
        out = AuditReportValidator().check_for_contradiction({"approval_rate": 0.5}, [])
        assert [c["type"] for c in out] == ["NO_DECISIONS_TO_COMPARE"]
        assert out[0]["severity"] == "INFO"


class TestBiasNeutralizationEngine:
    def test_rescores_only_named_candidates(self):
        eng = BiasNeutralizationEngine()
        eng.ingest_biases([BiasSignature("geographic_penalty", ["002", "999"], 0.5, "location_distance_miles", 0.8)])
        out = eng.recommend_candidate_rescores([_cand(1), _cand(2)])
        assert [c["candidate_id"] for c in out] == ["002"]
        assert out[0]["penalty_applied"] == pytest.approx(0.4)
        assert out[0]["bias_detected"] == "geographic_penalty"

    def test_safeguards_match_detected_bias_types(self):
        eng = BiasNeutralizationEngine()
        eng.ingest_biases([BiasSignature("demographic_proxy_via_name", ["001"], 0.5, "name_analysis", 0.8)])
        names = [s["safeguard"] for s in eng.propose_system_safeguards()]
        assert "Name_Anonymization" in names
        assert "Geographic_Blind_Scoring" not in names
        assert "Employment_History_Normalization" not in names
        # The two structural safeguards are always proposed.
        assert names[-2:] == ["Independent_Validation_Suite", "Real_Time_Bias_Detection"]

    def test_no_biases_yields_only_structural_safeguards(self):
        names = [s["safeguard"] for s in BiasNeutralizationEngine().propose_system_safeguards()]
        assert names == ["Independent_Validation_Suite", "Real_Time_Bias_Detection"]


class TestCounterATS:
    def test_full_audit_of_biased_system_with_falsified_report(self):
        cands, decs = geographic_pool()
        report = {
            "approval_rate": 0.90,
            "system_validation_accuracy": 0.99,
            "bias_detection_tests": {"geographic_diversity": 0.98},
        }
        audit = CounterATS().audit_adversarial_system(cands, decs, report)
        assert audit["audit_verdict"] == "SYSTEMATIC_BIAS_DETECTED"
        assert audit["report_verdict"] == "AUDIT_REPORT_FALSIFIED"
        assert audit["validation_integrity"]["verdict"] == "SUSPICIOUS_VALIDATION_LOOP_DETECTED"
        assert [b["type"] for b in audit["biases_found"]] == ["geographic_penalty"]
        assert all(b["prosecutable"] for b in audit["biases_found"])
        assert audit["summary"]["total_candidates_affected"] == 5
        assert audit["summary"]["false_rejections_likely"] == 5
        assert [c["candidate_id"] for c in audit["candidate_corrections"]] == [f"{i:03d}" for i in range(5, 10)]

    def test_full_audit_of_fair_system_with_honest_report(self):
        cands, decs = fair_pool()
        report = {
            "approval_rate": 0.60,
            "system_validation_accuracy": 0.70,
            "bias_detection_tests": {"geographic_diversity": 0.80},
        }
        audit = CounterATS().audit_adversarial_system(cands, decs, report)
        assert audit["audit_verdict"] == "NO_BIAS_DETECTED"
        assert audit["report_verdict"] == "AUDIT_REPORT_CONSISTENT"
        assert audit["validation_integrity"]["verdict"] == "VALIDATION_APPEARS_GENUINE"
        assert audit["biases_found"] == []
        assert audit["candidate_corrections"] == []
        assert audit["summary"]["total_candidates_affected"] == 0

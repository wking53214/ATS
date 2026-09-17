"""Tests for ats_counter_system.py, the module behind the README's
"legal evidence" claim. Until 2026-09-08 it had no automated test.

Each detector is exercised on both sides of its threshold so a detector that
stops detecting (or never could) fails here. The fixture pools are built so
that exactly one bias is present at a time.
"""

import pytest

from ats_counter_system import (
    ALPHA,
    MIN_COHORT_N,
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
#
# POOL SIZE IS PART OF THE FIXTURE, NOT AN ARBITRARY NUMBER. Every pool here
# used to hold 10 candidates, 5 per cohort, and the detector reported bias
# from them at 95% confidence. It cannot: MIN_COHORT_N is 30 per cohort and a
# 5-versus-5 split supports no claim at all. The pools are sized to clear the
# floor so the tests exercise the detector rather than its power guard, and
# test_a_cohort_below_the_floor_is_never_a_finding holds the floor itself.
POOL = 2 * MIN_COHORT_N + 20          # 40 per cohort, with headroom


def geographic_pool(n=POOL):
    cands, decs = [], []
    for i in range(n):
        remote = i >= n // 2
        cands.append(_cand(i, miles=500 if remote else 5))
        decs.append(_dec(i, "REJECTED" if remote else "APPROVED"))
    return cands, decs


def fair_pool(n=POOL):
    cands, decs = [], []
    for i in range(n):
        remote = i >= n // 2
        cands.append(_cand(i, miles=500 if remote else 5))
        # Same rejection rate on both sides: 2 in every 5 rejected.
        decs.append(_dec(i, "REJECTED" if i % 5 < 2 else "APPROVED"))
    return cands, decs


class TestDecisionFunctionInverter:
    """Every assertion here used to hold on 5 candidates per cohort, which is
    the defect: the detector emitted "geographic_penalty" at 0.95 confidence
    from samples that support no claim. It now runs a hypothesis test with a
    power guard, so these exercise the test and the ones below hold the
    guard."""

    def test_geographic_penalty_detected(self):
        inv = DecisionFunctionInverter()
        inv.ingest_decisions(*geographic_pool())
        sigs = inv.detect_correlated_rejection_patterns()
        assert [s.bias_type for s in sigs] == ["geographic_penalty"]
        sig = sigs[0]
        assert sig.hidden_factor == "location_distance_miles"
        # Tied to the test that produced it, not merely "small". Asserting
        # `< ALPHA` alone passes for a hardcoded 0.0, which is the shape of
        # the bug being fixed: a number in the confidence field that no
        # measurement stands behind.
        result = next(r for r in inv.last_test_results
                      if r.cohort_label == "geographic_penalty")
        assert sig.p_value == pytest.approx(result.p_value_adjusted)
        assert sig.p_value < ALPHA
        # phi, from a Yates-corrected chi-square, so perfect separation lands
        # just under 1 rather than exactly on it. Asserted as "a strong
        # effect" rather than pinned to the constant the correction happens
        # to produce, which would be testing scipy's arithmetic.
        assert sig.correlation_strength > 0.9
        assert sorted(sig.affected_candidates) == [f"{i:03d}" for i in range(POOL // 2, POOL)]

    def test_equal_rates_produce_no_signature(self):
        inv = DecisionFunctionInverter()
        inv.ingest_decisions(*fair_pool())
        assert inv.detect_correlated_rejection_patterns() == []

    def test_a_cohort_below_the_floor_is_never_a_finding(self):
        """THE REGRESSION THIS FIX EXISTS FOR.

        The old guard was `if group_a and group_b`, so one rejected remote
        candidate was a 100% rejection rate, cleared the 0.3 gap, and produced
        a prosecutable finding from n=1 -- with confidence computed from the
        gap, so the smallest possible sample gave the highest possible
        confidence. Perfect separation is kept here so nothing but the sample
        size can be what stops it."""
        for n in (2, 10, MIN_COHORT_N * 2 - 2):
            inv = DecisionFunctionInverter()
            inv.ingest_decisions(*geographic_pool(n))
            assert inv.detect_correlated_rejection_patterns() == [], f"n={n}"

    def test_the_floor_is_the_only_thing_stopping_it(self):
        """The control for the test above: the same perfectly separated pool
        one pair either side of the floor. If this failed, the test above
        would be passing for some other reason."""
        inv = DecisionFunctionInverter()
        inv.ingest_decisions(*geographic_pool(MIN_COHORT_N * 2))
        assert [s.bias_type for s in inv.detect_correlated_rejection_patterns()] \
            == ["geographic_penalty"]

    def test_an_untested_cohort_is_recorded_as_untested(self):
        """"Not enough data" and "no bias" must not read the same. The
        detector keeps every result, so an audit can tell a cohort that was
        cleared from one that was never examined."""
        from ats_statistics import Significance

        inv = DecisionFunctionInverter()
        inv.ingest_decisions(*geographic_pool(10))
        inv.detect_correlated_rejection_patterns()
        outcome = {r.cohort_label: r.significance for r in inv.last_test_results}
        assert outcome["geographic_penalty"] is Significance.INSUFFICIENT_DATA
        assert len(outcome) == 3, "every cohort is reported, not only the ones that fired"

    def test_three_tests_are_corrected_for_multiplicity(self):
        """Three simultaneous tests at alpha=0.05 give roughly a 1-in-7 chance
        of at least one false positive uncorrected, and a bias auditor that
        cries wolf on one cohort in seven is not usable evidence. Two cohorts
        split here, so Benjamini-Hochberg has something to adjust."""
        cands, decs = [], []
        for i in range(POOL):
            remote = i >= POOL // 2
            cands.append(_cand(i, miles=500 if remote else 5,
                               jobs=8 if remote else 2, years=4))
            decs.append(_dec(i, "REJECTED" if remote else "APPROVED"))
        inv = DecisionFunctionInverter()
        inv.ingest_decisions(cands, decs)
        inv.detect_correlated_rejection_patterns()
        tested = [r for r in inv.last_test_results if r.p_value is not None]
        assert len(tested) == 2
        for r in tested:
            assert r.p_value_adjusted is not None
            assert r.p_value_adjusted >= r.p_value, "correction only ever raises a p-value"

    def test_the_signature_carries_the_p_value_the_test_produced(self):
        """A moderate disparity -- 65% versus 35% across 40 a side -- which is
        significant at p=0.014. Moderate on purpose: under perfect separation
        the p-value is so close to zero that comparing a signature against it
        cannot tell a real measurement from a hardcoded 0.0, and a number in
        the evidence field that no measurement stands behind is exactly the
        defect this replaced."""
        cands, decs = [], []
        half = POOL // 2
        for i in range(POOL):
            remote = i >= half
            cands.append(_cand(i, miles=500 if remote else 5))
            k = i - half if remote else i
            rejected = k < (26 if remote else 14)
            decs.append(_dec(i, "REJECTED" if rejected else "APPROVED"))
        inv = DecisionFunctionInverter()
        inv.ingest_decisions(cands, decs)

        sigs = inv.detect_correlated_rejection_patterns()
        assert [s.bias_type for s in sigs] == ["geographic_penalty"]
        result = next(r for r in inv.last_test_results
                      if r.cohort_label == "geographic_penalty")
        assert sigs[0].p_value == pytest.approx(result.p_value_adjusted)
        assert 0.001 < sigs[0].p_value < ALPHA, "far enough from zero to be a real comparison"

    def test_a_disparity_too_weak_to_be_evidence_is_not_a_finding(self):
        """A 60%-vs-40% rejection gap across 40 candidates a side: a real
        difference in the sample, p=0.12, and not evidence of anything at
        alpha=0.05. The old code had no notion of this -- 20 points cleared
        its 0.2 threshold and became a prosecutable finding. It is also what
        holds ALPHA honest: declared in advance, and loosening it to swallow
        this case fails here."""
        cands, decs = [], []
        half = POOL // 2
        for i in range(POOL):
            remote = i >= half
            cands.append(_cand(i, miles=500 if remote else 5))
            k = i - half if remote else i
            rejected = k < (24 if remote else 16)
            decs.append(_dec(i, "REJECTED" if rejected else "APPROVED"))
        inv = DecisionFunctionInverter()
        inv.ingest_decisions(cands, decs)

        assert inv.detect_correlated_rejection_patterns() == []
        result = next(r for r in inv.last_test_results
                      if r.cohort_label == "geographic_penalty")
        assert result.p_value is not None, "it was tested, not skipped"
        assert result.p_value > ALPHA
        assert result.rate_gap == pytest.approx(0.2), "the disparity is real; the evidence is not"

    def test_volatility_penalty_detected(self):
        cands, decs = [], []
        for i in range(POOL):
            volatile = i >= POOL // 2
            cands.append(_cand(i, jobs=8 if volatile else 2, years=4))
            decs.append(_dec(i, "REJECTED" if volatile else "APPROVED"))
        inv = DecisionFunctionInverter()
        inv.ingest_decisions(cands, decs)
        sigs = inv.detect_correlated_rejection_patterns()
        assert [s.bias_type for s in sigs] == ["volatility_penalty"]
        assert sigs[0].hidden_factor == "turnover_rate"
        assert sigs[0].p_value < ALPHA

    def test_name_proxy_detected(self):
        cands, decs = [], []
        for i in range(POOL):
            vowel_heavy = i >= POOL // 2
            cands.append(_cand(i, name="Aiea Oue" if vowel_heavy else "Bob Lund"))
            decs.append(_dec(i, "REJECTED" if vowel_heavy else "APPROVED"))
        inv = DecisionFunctionInverter()
        inv.ingest_decisions(cands, decs)
        sigs = inv.detect_correlated_rejection_patterns()
        assert [s.bias_type for s in sigs] == ["demographic_proxy_via_name"]
        assert sigs[0].hidden_factor == "name_analysis"
        assert sigs[0].p_value < ALPHA

    def test_one_sided_pool_cannot_be_compared(self):
        # All candidates local: no remote group, so no geographic signature.
        cands = [_cand(i, miles=5) for i in range(POOL)]
        decs = [_dec(i, "REJECTED") for i in range(POOL)]
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
        rejected = POOL // 2
        assert audit["summary"]["total_candidates_affected"] == rejected
        assert audit["summary"]["false_rejections_likely"] == rejected
        assert [c["candidate_id"] for c in audit["candidate_corrections"]] \
            == [f"{i:03d}" for i in range(rejected, POOL)]

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

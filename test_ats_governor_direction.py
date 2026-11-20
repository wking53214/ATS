"""ats_governor_fixed.py: the geographic checks report which group was worse off.

The rejection-rate gap is an absolute size. These tests pin that the direction is reported alongside it, so a gap
that favours remote candidates is not described as a penalty on them.
"""

from ats_governor_fixed import DecisionFunctionAnalyzer, StreamingBiasMonitor

N = 40


def _data(remote_rejected, local_rejected):
    cands, decs = [], []
    for i in range(2 * N):
        remote = i >= N
        k = i - N if remote else i
        limit = remote_rejected if remote else local_rejected
        cands.append({"id": f"{i:03d}", "location_distance_miles": 500 if remote else 5})
        decs.append({"id": f"{i:03d}", "decision": "REJECTED" if k < limit else "APPROVED"})
    return cands, decs


def _signatures(remote_rejected, local_rejected):
    analyzer = DecisionFunctionAnalyzer()
    analyzer.ingest(*_data(remote_rejected, local_rejected))
    return analyzer.detect_correlated_rejection_patterns()


def test_remote_rejected_more_is_a_geographic_penalty_naming_remote_candidates():
    found = _signatures(remote_rejected=N, local_rejected=0)
    assert [s.bias_type for s in found] == ["GEOGRAPHIC_PENALTY"]
    assert found[0].affected_candidates and all(int(c) >= N for c in found[0].affected_candidates)


def test_local_rejected_more_is_reported_as_remote_favoured_and_names_local_candidates():
    found = _signatures(remote_rejected=0, local_rejected=N)
    assert [s.bias_type for s in found] == ["REMOTE_FAVOURED_OVER_LOCAL"]
    assert found[0].affected_candidates and all(int(c) < N for c in found[0].affected_candidates)


def _batch_event(remote_rejected, local_rejected):
    monitor = StreamingBiasMonitor(batch_size=10_000)
    for candidate, decision in zip(*_data(remote_rejected, local_rejected)):
        monitor.ingest_decision(candidate, decision)
    report = monitor.analyze_batch()
    return next(e for e in report["events"] if e["event_type"] == "GEOGRAPHIC_DISPARITY")


def test_the_batch_event_says_which_cohort_was_rejected_more():
    assert _batch_event(N, 0)["details"]["higher_rejection_cohort"] == "remote"
    assert _batch_event(0, N)["details"]["higher_rejection_cohort"] == "local"

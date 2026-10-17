"""Tests for ats_cns_connector.py, the optional binding-only link to CNS.

The connector turns two ATS outputs (the counter audit and the evidence
package) into deterministic content and asks a ``cns.gate.GateResult`` whether
it was issued against exactly that content. Nothing here decides a verdict.

Skipped when CNS is not installed, unless ATS_REQUIRE_CNS=1, in which case a
missing CNS fails the run (the CI ``cns`` job sets it). The independence tests
in test_ats_cns_independence.py never skip.
"""

import copy
import importlib
import json
import os
import secrets
from types import SimpleNamespace

import pytest

if os.environ.get("ATS_REQUIRE_CNS") == "1":
    gate = importlib.import_module("cns.gate")
else:
    gate = pytest.importorskip("cns.gate")

import ats_cns_connector as conn  # noqa: E402
from ats_counter_system import MIN_COHORT_N, CounterATS  # noqa: E402
from ats_governor_fixed import ATS, ATSGovernorProduction  # noqa: E402

CANARY = "CANARY-7f3a9c-do-not-log"
POOL = 2 * MIN_COHORT_N + 20


# ------------------------------------------------------------------ real outputs

def _pool(canary=False):
    """Remote candidates are all rejected, local ones all approved."""
    cands, decs = [], []
    for i in range(POOL):
        remote = i >= POOL // 2
        cand = {
            "id": f"{i:03d}", "name": "Bob Lund",
            "location_distance_miles": 500 if remote else 5,
            "employment_history": ["a", "b"], "years_professional": 8,
        }
        if canary:
            cand.update(name=f"Zxq {CANARY}", email=f"{CANARY}@example.org", resume_text=CANARY)
        cands.append(cand)
        decs.append({"id": f"{i:03d}", "decision": "REJECTED" if remote else "APPROVED"})
    return cands, decs


FALSIFIED = {
    "approval_rate": 0.90,
    "system_validation_accuracy": 0.99,
    "bias_detection_tests": {"geographic_diversity": 0.98},
}


@pytest.fixture(autouse=True)
def _in_tmp(tmp_path, monkeypatch):
    """CryptoAuditTrail writes audit.log into the working directory."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("AUDIT_KEY", raising=False)


def make_audit(canary=False):
    cands, decs = _pool(canary)
    return CounterATS().audit_adversarial_system(cands, decs, copy.deepcopy(FALSIFIED))


def make_package(report=None, canary=False):
    cands, decs = _pool(canary)
    prod = ATSGovernorProduction(signing_key=secrets.token_hex(16))
    return prod.run_full_audit(cands, decs, copy.deepcopy(FALSIFIED if report is None else report))


def make_result(digest, subject, **kw):
    return gate.GateResult(
        gate="test", position=gate.GatePosition.ALPHA, outcome=gate.GateOutcome.PASS,
        reason="test", subject=subject, subject_digest=digest, **kw)


@pytest.fixture
def audit():
    out = make_audit()
    assert out["biases_found"] and out["candidate_corrections"] and out["audit_report_contradictions"]
    return out


@pytest.fixture
def package():
    out = make_package()
    assert out["detected_biases"] and out["candidate_corrections"] and out["audit_contradictions"]
    return out


# ------------------------------------------------------------------ helpers

def leaves(node, path=()):
    """Every scalar position in a nested dict / list, as a path of keys and indexes."""
    if isinstance(node, dict):
        for key, item in node.items():
            yield from leaves(item, path + (key,))
    elif isinstance(node, list):
        for index, item in enumerate(node):
            yield from leaves(item, path + (index,))
    else:
        yield path


def get(node, path):
    for step in path:
        node = node[step]
    return node


def changed(value):
    if isinstance(value, bool):
        return not value
    if isinstance(value, int):
        return value + 1
    if isinstance(value, float):
        return value + 0.125
    if isinstance(value, str):
        return value + "x"
    return "was-none"


def mutated(obj, path):
    # Through JSON, not deepcopy: ATS hands the same list to two keys of one
    # output, and deepcopy keeps that sharing, so one edit would change both.
    out = json.loads(json.dumps(obj))
    parent = get(out, path[:-1])
    parent[path[-1]] = changed(parent[path[-1]])
    return out


def assert_binding_types(value, where="content"):
    """Only what cns accepts, and exactly those types (no subclasses, no tuples)."""
    if isinstance(value, dict):
        for key, item in value.items():
            assert type(key) is str, where
            assert_binding_types(item, f"{where}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            assert_binding_types(item, f"{where}[{index}]")
    else:
        assert value is None or type(value) in (str, int, float, bool), (where, type(value))
        if type(value) is float:
            assert value == value and value not in (float("inf"), float("-inf")), where


# ------------------------------------------------------------------ determinism

def test_audit_content_is_deterministic(audit):
    assert conn.audit_content(audit) == conn.audit_content(copy.deepcopy(audit))
    assert conn.audit_digest(audit) == conn.audit_digest(copy.deepcopy(audit))
    assert conn.audit_digest(audit) == conn.audit_digest(make_audit())


def test_evidence_content_is_deterministic(package):
    assert conn.evidence_content(package) == conn.evidence_content(copy.deepcopy(package))
    assert conn.evidence_digest(package) == conn.evidence_digest(copy.deepcopy(package))


def test_two_real_runs_of_the_evidence_pipeline_agree_though_their_reports_differ():
    first, second = make_package(), make_package()
    assert first["litigation_report"] != second["litigation_report"]  # generated at, and signed
    assert conn.evidence_digest(first) == conn.evidence_digest(second)


def test_digest_is_cns_subject_digest_of_the_content(audit, package):
    assert conn.audit_digest(audit) == gate.subject_digest(conn.audit_content(audit))
    assert conn.evidence_digest(package) == gate.subject_digest(conn.evidence_content(package))


def test_content_names_its_own_kind(audit, package):
    assert conn.audit_content(audit)["kind"] == conn.AUDIT_SUBJECT == "ats.audit"
    assert conn.evidence_content(package)["kind"] == conn.EVIDENCE_SUBJECT == "ats.evidence"


def test_the_two_output_types_never_share_a_digest(audit, package):
    assert conn.audit_digest(audit) != conn.evidence_digest(package)
    assert conn.AUDIT_SUBJECT != conn.EVIDENCE_SUBJECT


# A small hand-built output of each shape, with its digest pinned. The content
# shape is what a stored binding refers to: if this changes, every digest an
# earlier verdict carried stops matching, and that should be a deliberate act.
SMALL_AUDIT = {
    "audit_verdict": "SYSTEMATIC_BIAS_DETECTED",
    "biases_found": [{
        "type": "geographic_penalty", "affected_candidates": ["b", "a"],
        "correlation_strength": 0.5, "evidence_confidence": 0.5, "prosecutable": True}],
    "validation_integrity": {"verdict": "VALIDATION_APPEARS_GENUINE", "gap_magnitude": 0.1},
    "audit_report_contradictions": [],
    "report_verdict": "AUDIT_REPORT_CONSISTENT",
    "candidate_corrections": [],
    "recommended_safeguards": [],
    "summary": {"biases_detected_count": 1},
}
SMALL_PACKAGE = {
    "detected_biases": [{
        "bias_type": "GEOGRAPHIC_PENALTY", "affected_candidates": ["b", "a"],
        "correlation_strength": 0.5, "hidden_factor": "location_distance_miles",
        "evidence_confidence": 0.5, "p_value": 0.01}],
    "audit_contradictions": [],
    "candidate_corrections": [],
    "legal_evidence": {"statistical": [], "fraud": [], "harm": []},
    "litigation_report": json.dumps({"generated": "now", "conclusion": "Review required"}),
    "system_recommendation": "CONTINUE_WITH_MONITORING",
}


def test_pinned_digests_of_small_hand_built_outputs():
    assert conn.audit_digest(SMALL_AUDIT) == \
        "de3e35c163db904877ee4b0105d5cba6a98bee0a7f1a7077595b2d0b8f40208d"
    assert conn.evidence_digest(SMALL_PACKAGE) == \
        "4a0d2f23c312f64c60cedf3628003d20ad52bbafdecce7a9d5071ea785b805a0"


# ------------------------------------------------------------------ every bound field

def test_changing_any_audit_field_changes_the_digest(audit):
    base = conn.audit_digest(audit)
    paths = [p for p in leaves(audit)]
    assert len(paths) > 40
    for path in paths:
        assert conn.audit_digest(mutated(audit, path)) != base, path


def test_changing_any_evidence_field_changes_the_digest(package):
    base = conn.evidence_digest(package)
    bound = {k: v for k, v in package.items() if k not in ("streaming_alerts", "audit_trail_valid", "litigation_report")}
    paths = [p for p in leaves(bound)]
    assert len(paths) > 40
    for path in paths:
        assert conn.evidence_digest({**package, **mutated(bound, path)}) != base, path


def _report_paths(report):
    volatile = ("generated", "generated_by", "warning")
    return [p for p in leaves(report) if p[0] not in volatile]


def test_changing_any_stable_field_of_the_litigation_report_changes_the_digest(package):
    base = conn.evidence_digest(package)
    report = json.loads(package["litigation_report"])
    paths = _report_paths(report)
    assert len(paths) > 20
    for path in paths:
        edited = {**package, "litigation_report": json.dumps(mutated(report, path))}
        assert conn.evidence_digest(edited) != base, path


def test_the_methodology_thresholds_are_bound(package):
    report = json.loads(package["litigation_report"])
    for key in ("significance_level_alpha", "minimum_cohort_n", "approval_rate_threshold"):
        edited = copy.deepcopy(report)
        edited["methodology"][key] += 1
        assert conn.evidence_digest({**package, "litigation_report": json.dumps(edited)}) \
            != conn.evidence_digest(package), key


def test_adding_or_dropping_a_record_changes_the_digest(audit, package):
    more = copy.deepcopy(audit)
    more["candidate_corrections"].append(copy.deepcopy(more["candidate_corrections"][0]))
    assert conn.audit_digest(more) != conn.audit_digest(audit)
    fewer = copy.deepcopy(package)
    fewer["audit_contradictions"].pop()
    assert conn.evidence_digest(fewer) != conn.evidence_digest(package)


def test_int_and_float_are_not_the_same_value(audit):
    other = copy.deepcopy(audit)
    other["summary"]["biases_detected_count"] = float(other["summary"]["biases_detected_count"])
    assert conn.audit_digest(other) != conn.audit_digest(audit)


# ------------------------------------------------------------------ claimed-irrelevant differences

def test_audit_order_of_set_like_collections_is_irrelevant(audit):
    shuffled = copy.deepcopy(audit)
    for bias in shuffled["biases_found"]:
        bias["affected_candidates"].reverse()
    shuffled["candidate_corrections"].reverse()
    shuffled["recommended_safeguards"].reverse()
    shuffled["audit_report_contradictions"].reverse()
    assert shuffled != audit
    assert conn.audit_digest(shuffled) == conn.audit_digest(audit)


def test_evidence_order_of_set_like_collections_is_irrelevant(package):
    shuffled = copy.deepcopy(package)
    for bias in shuffled["detected_biases"]:
        bias["affected_candidates"].reverse()
    shuffled["candidate_corrections"].reverse()
    shuffled["audit_contradictions"].reverse()
    legal = shuffled["legal_evidence"]
    legal["harm"].reverse()
    legal["fraud"].reverse()
    legal["statistical"].reverse()
    assert shuffled != package
    assert conn.evidence_digest(shuffled) == conn.evidence_digest(package)


def test_the_order_of_the_input_candidates_does_not_move_the_audit_digest(audit):
    cands, decs = _pool()
    pairs = list(zip(cands, decs))[::-1]
    reversed_audit = CounterATS().audit_adversarial_system(
        [c for c, _ in pairs], [d for _, d in pairs], copy.deepcopy(FALSIFIED))
    assert reversed_audit != audit
    assert conn.audit_digest(reversed_audit) == conn.audit_digest(audit)


def test_unnamed_keys_of_an_output_are_ignored(audit, package):
    audit["applicant_notes"] = CANARY
    package["applicant_notes"] = CANARY
    assert conn.audit_digest(audit) == conn.audit_digest(make_audit())
    assert conn.evidence_digest(package) == conn.evidence_digest(make_package())
    assert CANARY not in json.dumps(conn.audit_content(audit))
    assert CANARY not in json.dumps(conn.evidence_content(package))


def test_volatile_parts_of_the_evidence_package_are_not_bound(package):
    base = conn.evidence_digest(package)
    other = copy.deepcopy(package)
    other["streaming_alerts"] = {"batch_number": 99, "events": [{"timestamp": "2099-01-01T00:00:00+00:00"}]}
    other["audit_trail_valid"] = {"status": "BROKEN", "valid": False, "total_events": 0}
    assert conn.evidence_digest(other) == base


def test_the_reports_clock_and_signature_are_not_bound(package, monkeypatch):
    base = conn.evidence_digest(package)
    # unsigned form carries a warning, and a different clock
    report = json.loads(package["litigation_report"])
    report["generated"] = "2001-01-01T00:00:00+00:00"
    report["generated_by"] = "someone-else"
    report["warning"] = "UNSIGNED: Provide signing_key for cryptographic verification"
    unsigned = {**package, "litigation_report": json.dumps(report, indent=2)}
    assert conn.evidence_digest(unsigned) == base
    # the real signed form, wrapped, with its own signature and time
    monkeypatch.setenv("AUDIT_KEY", secrets.token_hex(16))
    signed = make_package()
    wrapped = json.loads(signed["litigation_report"])
    assert set(wrapped) == {"report", "signature", "signed_at"}
    assert conn.evidence_digest(signed) == base


def test_wall_clock_figures_of_a_contradiction_are_not_bound(audit):
    one, two = copy.deepcopy(audit), copy.deepcopy(audit)
    stale = {"type": "STALE_REPORT", "severity": "WARNING"}
    one["audit_report_contradictions"].append({**stale, "age_days": 400.5})
    two["audit_report_contradictions"].append({**stale, "age_days": 913.25})
    future = {"type": "FUTURE_TIMESTAMP", "report_time": "2099-01-01T00:00:00+00:00", "severity": "CRITICAL"}
    one["audit_report_contradictions"].append({**future, "current_time": "2026-01-01T00:00:00+00:00"})
    two["audit_report_contradictions"].append({**future, "current_time": "2027-02-02T00:00:00+00:00"})
    assert conn.audit_digest(one) == conn.audit_digest(two)
    two["audit_report_contradictions"][-1]["report_time"] = "2098-01-01T00:00:00+00:00"
    assert conn.audit_digest(one) != conn.audit_digest(two)


def test_subclasses_of_float_int_and_str_digest_like_the_plain_values(audit):
    class F(float):
        pass

    class I(int):  # noqa: E742
        pass

    class S(str):
        pass

    other = copy.deepcopy(audit)
    bias = other["biases_found"][0]
    bias["correlation_strength"] = F(bias["correlation_strength"])
    other["summary"]["biases_detected_count"] = I(other["summary"]["biases_detected_count"])
    other["audit_verdict"] = S(other["audit_verdict"])
    assert conn.audit_digest(other) == conn.audit_digest(audit)
    assert_binding_types(conn.audit_content(other))


def test_tuples_are_bound_as_lists(audit):
    other = copy.deepcopy(audit)
    other["biases_found"][0]["affected_candidates"] = tuple(other["biases_found"][0]["affected_candidates"])
    other["summary"]["extra"] = ("a", 1)
    content = conn.audit_content(other)
    assert content["summary"]["extra"] == ["a", 1]
    assert_binding_types(content)


# ------------------------------------------------------------------ wrong types, missing keys

@pytest.mark.parametrize("bad", [None, [], "audit", 3, ("a",), object()])
def test_a_non_dict_raises_type_error(bad):
    for fn in (conn.audit_content, conn.audit_digest, conn.evidence_content, conn.evidence_digest):
        with pytest.raises(TypeError):
            fn(bad)


def test_binds_with_a_non_dict_raises_type_error(audit):
    result = make_result(conn.audit_digest(audit), conn.AUDIT_SUBJECT)
    with pytest.raises(TypeError):
        conn.audit_binds(result, None)
    with pytest.raises(TypeError):
        conn.evidence_binds(result, [])


@pytest.mark.parametrize("key", conn._AUDIT_KEYS)
def test_audit_missing_key_raises_value_error_naming_it(audit, key):
    del audit[key]
    with pytest.raises(ValueError, match=key):
        conn.audit_content(audit)


@pytest.mark.parametrize("key", conn._EVIDENCE_KEYS)
def test_evidence_missing_key_raises_value_error_naming_it(package, key):
    del package[key]
    with pytest.raises(ValueError, match=key):
        conn.evidence_content(package)


@pytest.mark.parametrize("key", conn._AUDIT_BIAS_KEYS)
def test_audit_bias_missing_key_raises_value_error_naming_it(audit, key):
    del audit["biases_found"][0][key]
    with pytest.raises(ValueError, match=key):
        conn.audit_content(audit)


@pytest.mark.parametrize("key", conn._EVIDENCE_BIAS_KEYS)
def test_evidence_bias_missing_key_raises_value_error_naming_it(package, key):
    del package["detected_biases"][0][key]
    with pytest.raises(ValueError, match=key):
        conn.evidence_content(package)


@pytest.mark.parametrize("key", conn._LEGAL_EVIDENCE_KEYS)
def test_evidence_legal_evidence_missing_key_raises_value_error_naming_it(package, key):
    del package["legal_evidence"][key]
    with pytest.raises(ValueError, match=key):
        conn.evidence_content(package)


def test_nested_wrong_types_raise_type_error(audit, package):
    def edit(obj, fn):
        out = copy.deepcopy(obj)
        fn(out)
        return out

    cases = [
        (conn.audit_content, edit(audit, lambda a: a.update(biases_found={}))),
        (conn.audit_content, edit(audit, lambda a: a.update(biases_found=["x"]))),
        (conn.audit_content, edit(audit, lambda a: a["biases_found"][0].update(affected_candidates="001"))),
        (conn.audit_content, edit(audit, lambda a: a.update(audit_report_contradictions=[1]))),
        (conn.audit_content, edit(audit, lambda a: a.update(candidate_corrections="none"))),
        (conn.audit_content, edit(audit, lambda a: a["summary"].update(extra={1, 2}))),
        (conn.audit_content, edit(audit, lambda a: a["summary"].update(extra=b"raw"))),
        (conn.audit_content, edit(audit, lambda a: a["summary"].update({3: "int key"}))),
        (conn.audit_content, edit(audit, lambda a: a["biases_found"][0].update(correlation_strength=float("nan")))),
        (conn.audit_content, edit(audit, lambda a: a["summary"].update(extra=float("inf")))),
        (conn.evidence_content, edit(package, lambda p: p.update(litigation_report={"a": 1}))),
        (conn.evidence_content, edit(package, lambda p: p.update(detected_biases=None))),
        (conn.evidence_content, edit(package, lambda p: p["legal_evidence"].update(harm="none"))),
        (conn.evidence_content, edit(package, lambda p: p["detected_biases"][0].update(p_value=float("nan")))),
    ]
    for fn, bad in cases:
        with pytest.raises(TypeError):
            fn(bad)


def test_a_litigation_report_that_is_not_json_raises_value_error(package):
    for text in ("not json", "[1, 2]", json.dumps({"report": [], "signature": "s"})):
        with pytest.raises(ValueError):
            conn.evidence_content({**package, "litigation_report": text})


# ------------------------------------------------------------------ binds

def test_audit_binds_true_for_a_result_issued_against_exactly_it(audit):
    result = make_result(conn.audit_digest(audit), conn.AUDIT_SUBJECT)
    assert conn.audit_binds(result, audit) is True


def test_evidence_binds_true_for_a_result_issued_against_exactly_it(package):
    result = make_result(conn.evidence_digest(package), conn.EVIDENCE_SUBJECT)
    assert conn.evidence_binds(result, package) is True


def test_binds_is_false_when_the_output_changed_after_the_verdict(audit, package):
    audit_result = make_result(conn.audit_digest(audit), conn.AUDIT_SUBJECT)
    package_result = make_result(conn.evidence_digest(package), conn.EVIDENCE_SUBJECT)
    audit["biases_found"][0]["correlation_strength"] += 0.01
    package["detected_biases"][0]["p_value"] *= 2
    assert conn.audit_binds(audit_result, audit) is False
    assert conn.evidence_binds(package_result, package) is False


def test_binds_is_false_for_an_unbound_hand_built_result(audit, package):
    bare = gate.GateResult(gate="g", position=gate.GatePosition.ALPHA, outcome=gate.GateOutcome.PASS)
    assert conn.audit_binds(bare, audit) is False
    assert conn.evidence_binds(bare, package) is False
    no_digest = make_result("", conn.AUDIT_SUBJECT)
    no_subject = make_result(conn.audit_digest(audit), "")
    assert conn.audit_binds(no_digest, audit) is False
    assert conn.audit_binds(no_subject, audit) is False


def test_binds_is_false_for_the_wrong_subject_and_true_for_a_chosen_one(audit):
    digest = conn.audit_digest(audit)
    assert conn.audit_binds(make_result(digest, "something.else"), audit) is False
    assert conn.audit_binds(make_result(digest, "something.else"), audit, subject="something.else") is True
    assert conn.audit_binds(make_result(digest, conn.AUDIT_SUBJECT), audit, subject="something.else") is False


def test_a_verdict_on_one_output_type_does_not_bind_the_other(audit, package):
    result = make_result(conn.audit_digest(audit), conn.AUDIT_SUBJECT)
    assert conn.evidence_binds(result, package) is False
    assert conn.evidence_binds(result, package, subject=conn.AUDIT_SUBJECT) is False


def test_binds_is_false_for_something_that_is_not_a_gate_result(audit):
    claim = SimpleNamespace(binds=lambda subject, digest: True)
    assert conn.audit_binds(claim, audit) is False
    assert conn.audit_binds(None, audit) is False


def test_binds_is_false_for_a_result_bound_to_different_content(audit):
    other = make_result(gate.subject_digest({"x": "y"}), conn.AUDIT_SUBJECT)
    assert conn.audit_binds(other, audit) is False


# ------------------------------------------------------------------ types and sensitive text

def test_content_has_only_types_cns_accepts(audit, package):
    for content in (conn.audit_content(audit), conn.evidence_content(package),
                    conn.audit_content(SMALL_AUDIT), conn.evidence_content(SMALL_PACKAGE)):
        assert_binding_types(content)
        gate.subject_digest(content)  # cns itself accepts it


def test_content_is_json_and_does_not_hold_the_input_objects(audit):
    content = conn.audit_content(audit)
    assert json.loads(json.dumps(content)) == content
    content["biases_found"][0]["affected_candidates"].append("zzz")
    assert "zzz" not in audit["biases_found"][0]["affected_candidates"]


def test_sensitive_text_never_reaches_the_audit_content():
    out = make_audit(canary=True)
    assert out["biases_found"], "the canary pool must still produce a finding"
    text = json.dumps(conn.audit_content(out))
    assert CANARY not in text
    assert CANARY.lower() not in text.lower()


def test_sensitive_text_never_reaches_the_evidence_content():
    out = make_package(canary=True)
    assert out["detected_biases"]
    text = json.dumps(conn.evidence_content(out))
    assert CANARY not in text
    assert CANARY.lower() not in text.lower()


def test_free_text_of_an_unparsable_report_timestamp_is_hashed_not_copied():
    out = make_package(report={**FALSIFIED, "timestamp": f"not a date {CANARY}"})
    assert any(c["type"] == "INVALID_TIMESTAMP_FORMAT" for c in out["audit_contradictions"])
    content = conn.evidence_content(out)
    text = json.dumps(content)
    assert CANARY not in text
    assert "timestamp_sha256" in text
    # and it is still bound: a different text is a different digest
    other = make_package(report={**FALSIFIED, "timestamp": f"not a date {CANARY} 2"})
    assert conn.evidence_digest(other) != conn.evidence_digest(out)


# ------------------------------------------------------------------ real end to end

def test_real_counter_audit_then_digest_then_bind(audit):
    assert audit["audit_verdict"] == "SYSTEMATIC_BIAS_DETECTED"
    digest = conn.audit_digest(audit)
    assert len(digest) == 64
    content = conn.audit_content(audit)
    assert content["audit_verdict"] == audit["audit_verdict"]
    assert content["report_verdict"] == "AUDIT_REPORT_FALSIFIED"
    assert [b["type"] for b in content["biases_found"]] == ["geographic_penalty"]
    assert content["biases_found"][0]["affected_candidates"] == [f"{i:03d}" for i in range(POOL // 2, POOL)]
    assert conn.audit_binds(make_result(digest, conn.AUDIT_SUBJECT), audit)


def test_real_evidence_pipeline_then_digest_then_bind(package):
    content = conn.evidence_content(package)
    assert content["system_recommendation"] == "IMMEDIATE_PAUSE_AND_INVESTIGATE"
    bias = content["detected_biases"][0]
    assert bias["bias_type"] == "GEOGRAPHIC_PENALTY"
    assert 0 < bias["p_value"] < 0.05
    assert content["litigation_report"]["methodology"]["minimum_cohort_n"] == MIN_COHORT_N
    assert "streaming_alerts" not in content and "audit_trail_valid" not in content
    assert conn.evidence_binds(make_result(conn.evidence_digest(package), conn.EVIDENCE_SUBJECT), package)


def test_the_whole_ats_flow_with_applicant_details_binds_without_copying_them(tmp_path):
    system = ATS(signing_key=secrets.token_hex(16))
    job = system.create_job("Engineer", "Core", "HQ", "Python and AI work", ["Python", "AI"])
    for i in range(90):
        remote = i % 3 == 0
        cand = system.add_candidate(
            name=f"Zxq {CANARY} {i}", email=f"{CANARY}-{i}@example.org", phone=f"555-{CANARY}",
            resume_text=f"{CANARY} Legacy engineer" if remote else f"{CANARY} Python AI systems",
            location_distance_miles=150.0 if remote else 25.0)
        system.apply_to_job(cand.candidate_id, job.job_id)
        if remote:
            cand.stage = "Rejected"
    audited = system.run_system_wide_audit({"approval_rate": 0.5})["production_pipeline_audit"]
    assert audited["detected_biases"], "the flow must produce a finding to bind"
    content = conn.evidence_content(audited)
    assert CANARY not in json.dumps(content)
    ids = content["detected_biases"][0]["affected_candidates"]
    assert ids and set(ids) <= set(system.candidates)
    result = make_result(conn.evidence_digest(audited), conn.EVIDENCE_SUBJECT)
    assert conn.evidence_binds(result, audited)
    audited["detected_biases"][0]["affected_candidates"].pop()
    assert not conn.evidence_binds(result, audited)


def test_cns_available_is_true_here():
    assert conn.cns_available() is True

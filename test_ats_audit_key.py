"""The audit trail and the evidence report fail closed on a missing key.

CryptoAuditTrail used to fall back to a key written in the source, so anyone
who read the source could forge its signatures. ATSGovernorProduction signed
the evidence report with AUDIT_KEY only, ignoring the key it was given, so a
caller who passed a key got a signed trail and an unsigned report.
"""

import hashlib
import hmac
import json
import secrets
from pathlib import Path

import pytest

import ats_governor_fixed
from ats_governor_fixed import ATS, ATSGovernorProduction, CryptoAuditTrail


@pytest.fixture(autouse=True)
def _no_env_key(tmp_path, monkeypatch):
    """No AUDIT_KEY unless a test sets one; the audit log goes to tmp_path."""
    monkeypatch.delenv("AUDIT_KEY", raising=False)
    monkeypatch.setenv("ATS_AUDIT_LOG_PATH", str(tmp_path / "audit.log"))


def _pool():
    cands, decs = [], []
    for i in range(100):
        remote = i >= 50
        cands.append({"id": f"{i:03d}", "location_distance_miles": 500 if remote else 5})
        decs.append({"id": f"{i:03d}", "decision": "REJECTED" if remote else "APPROVED"})
    return cands, decs


def _report_signature_ok(text, key):
    wrapped = json.loads(text)
    assert set(wrapped) == {"report", "signature", "signed_at"}, "the report must be signed"
    body = json.dumps(wrapped["report"], sort_keys=True, indent=2)
    expected = hmac.new(key.encode(), body.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(wrapped["signature"], expected)


def test_no_key_and_no_audit_key_is_an_error(tmp_path):
    log = tmp_path / "trail.log"
    with pytest.raises(ValueError, match="signing key"):
        CryptoAuditTrail(log_file=str(log))
    assert not log.exists(), "a refused trail must not create its log"


def test_an_empty_audit_key_is_an_error(tmp_path, monkeypatch):
    monkeypatch.setenv("AUDIT_KEY", "")
    with pytest.raises(ValueError, match="signing key"):
        CryptoAuditTrail(log_file=str(tmp_path / "trail.log"))


# Keys that are blank or already public: whitespace only, and the two literals
# this repository once published (the old fallback and the old demo key). The
# literals are built from parts so neither is written whole into this file.
_UNUSABLE_KEYS = [
    " ",
    "\n",
    " \t\r\n",
    "default_key_" + "change_me",
    "test_signing_key_" + "change_in_production",
    "default_key_" + "change_me\n",
]


@pytest.mark.parametrize("key", _UNUSABLE_KEYS)
def test_a_blank_or_published_signing_key_is_an_error(tmp_path, key):
    log = tmp_path / "trail.log"
    with pytest.raises(ValueError, match="signing key"):
        CryptoAuditTrail(signing_key=key, log_file=str(log))
    assert not log.exists(), "a refused trail must not create its log"


@pytest.mark.parametrize("key", _UNUSABLE_KEYS)
def test_a_blank_or_published_audit_key_is_an_error(tmp_path, monkeypatch, key):
    monkeypatch.setenv("AUDIT_KEY", key)
    log = tmp_path / "trail.log"
    with pytest.raises(ValueError, match="signing key"):
        CryptoAuditTrail(log_file=str(log))
    assert not log.exists(), "a refused trail must not create its log"


@pytest.mark.parametrize("key", _UNUSABLE_KEYS)
def test_the_pipelines_refuse_a_blank_or_published_key(monkeypatch, key):
    with pytest.raises(ValueError, match="signing key"):
        ATSGovernorProduction(signing_key=key)
    monkeypatch.setenv("AUDIT_KEY", key)
    with pytest.raises(ValueError, match="signing key"):
        ATS()


def test_the_pipelines_refuse_to_start_without_a_key():
    with pytest.raises(ValueError, match="signing key"):
        ATSGovernorProduction()
    with pytest.raises(ValueError, match="signing key"):
        ATS()


def test_audit_key_is_used_when_no_key_is_passed(tmp_path, monkeypatch):
    key = secrets.token_hex(16)
    monkeypatch.setenv("AUDIT_KEY", key)
    trail = CryptoAuditTrail(log_file=str(tmp_path / "trail.log"))
    trail.log("DECISION", "APPROVED")
    event = trail.events[0]
    payload = {k: v for k, v in event.items() if k not in ("hash", "hmac", "oscillation_detected")}
    expected = hmac.new(key.encode(), json.dumps(payload, sort_keys=True).encode(), hashlib.sha256).hexdigest()
    assert event["hmac"] == expected


def test_the_report_is_signed_with_the_key_the_pipeline_was_given():
    key = secrets.token_hex(16)
    out = ATSGovernorProduction(signing_key=key).run_full_audit(*_pool(), {"approval_rate": 0.9})
    assert _report_signature_ok(out["litigation_report"], key)
    assert out["audit_trail_valid"]["valid"]


def test_the_report_ignores_audit_key_when_a_key_was_passed(monkeypatch):
    key, other = secrets.token_hex(16), secrets.token_hex(16)
    monkeypatch.setenv("AUDIT_KEY", other)
    out = ATSGovernorProduction(signing_key=key).run_full_audit(*_pool(), {"approval_rate": 0.9})
    assert _report_signature_ok(out["litigation_report"], key)
    assert not _report_signature_ok(out["litigation_report"], other)


def test_the_report_uses_audit_key_when_no_key_was_passed(monkeypatch):
    key = secrets.token_hex(16)
    monkeypatch.setenv("AUDIT_KEY", key)
    out = ATSGovernorProduction().run_full_audit(*_pool(), {"approval_rate": 0.9})
    assert _report_signature_ok(out["litigation_report"], key)


@pytest.mark.parametrize("forged", ["0" * 64, None, 12345, "é" * 64, ""])
def test_a_forged_or_malformed_hmac_is_a_violation_not_a_crash(tmp_path, forged):
    trail = CryptoAuditTrail(signing_key=secrets.token_hex(16), log_file=str(tmp_path / "t.log"))
    trail.log("DECISION", "APPROVED")
    trail.events[0]["hmac"] = forged
    result = trail.verify_integrity()
    assert not result["valid"]
    assert result["violations"][0]["error"] == "HMAC_SIGNATURE_INVALID"


def test_signatures_are_compared_in_constant_time(tmp_path, monkeypatch):
    calls = []
    real = hmac.compare_digest
    monkeypatch.setattr(ats_governor_fixed.hmac, "compare_digest",
                        lambda a, b: calls.append(1) or real(a, b))
    trail = CryptoAuditTrail(signing_key=secrets.token_hex(16), log_file=str(tmp_path / "t.log"))
    trail.log("DECISION", "APPROVED")
    trail.log("DECISION", "REJECTED")
    assert trail.verify_integrity()["valid"]
    assert len(calls) == 2


def test_no_signing_key_is_written_into_the_module():
    source = Path(ats_governor_fixed.__file__).read_text(encoding="utf-8")
    assert "default_key_change_me" not in source
    assert "test_signing_key_change_in_production" not in source

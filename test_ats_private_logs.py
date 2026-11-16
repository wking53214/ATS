"""The audit log and the bridge WAL have no default location and are private.

The bridge WAL used to default to a fixed, shared /tmp path, and the audit
trail to audit.log in whatever directory the process ran in. Both files hold
candidate ids and decisions. Each now needs a path (argument or environment
variable), is created owner-only (0600), and refuses a symlink at the path.
"""

import inspect
import os
import secrets
import stat

import pytest

from ats_governance_kernel_bridge import WAL_PATH_ENV, ATSGovernorKernel, CandidateSignals
from ats_governor_fixed import AUDIT_LOG_PATH_ENV, ATS, ATSGovernorProduction, CryptoAuditTrail
from gov4_kernel import WAL

needs_nofollow = pytest.mark.skipif(not hasattr(os, "O_NOFOLLOW"), reason="needs O_NOFOLLOW")


@pytest.fixture(autouse=True)
def _clean_env(tmp_path, monkeypatch):
    monkeypatch.delenv(AUDIT_LOG_PATH_ENV, raising=False)
    monkeypatch.delenv(WAL_PATH_ENV, raising=False)
    monkeypatch.delenv("AUDIT_KEY", raising=False)
    # A permissive umask, so a 0600 result comes from the code and not the umask.
    old = os.umask(0)
    yield
    os.umask(old)


def _key():
    return secrets.token_hex(16)


def _mode(path):
    return stat.S_IMODE(os.lstat(path).st_mode)


def _signals():
    return CandidateSignals(
        candidate_id="cand-1", job_id="job-1", keyword_score=40.0, keyword_coverage=0.5,
        semantic_similarity=0.3, keyword_density=0.1, decision="APPROVED", confidence="high",
        algorithm_version="t", location_distance_miles=10.0, reason="r", resume_word_count=200,
        matched_terms=[], missing_terms=[],
    )


def test_env_var_names_are_explicit():
    assert AUDIT_LOG_PATH_ENV == "ATS_AUDIT_LOG_PATH"
    assert WAL_PATH_ENV == "ATS_WAL_PATH"


def test_there_is_no_default_location():
    assert inspect.signature(CryptoAuditTrail).parameters["log_file"].default is None
    assert inspect.signature(ATSGovernorKernel).parameters["wal_path"].default is None


# ------------------------------------------------------------------ audit trail

def test_audit_trail_without_a_path_is_an_error(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValueError, match="log path"):
        CryptoAuditTrail(signing_key=_key())
    with pytest.raises(ValueError, match="log path"):
        ATSGovernorProduction(signing_key=_key())
    with pytest.raises(ValueError, match="log path"):
        ATS(signing_key=_key())
    assert os.listdir(tmp_path) == [], "nothing may be written to the working directory"


def test_audit_trail_uses_the_env_var(tmp_path, monkeypatch):
    path = tmp_path / "from-env.log"
    monkeypatch.setenv(AUDIT_LOG_PATH_ENV, str(path))
    trail = CryptoAuditTrail(signing_key=_key())
    trail.log("DECISION", "APPROVED")
    assert trail.log_file == str(path)
    assert path.read_text(encoding="utf-8").count("\n") == 1


def test_audit_trail_file_is_owner_only(tmp_path):
    path = tmp_path / "audit.log"
    trail = CryptoAuditTrail(signing_key=_key(), log_file=str(path))
    assert _mode(path) == 0o600
    trail.log("DECISION", "APPROVED")
    assert _mode(path) == 0o600


def test_audit_trail_appends_to_an_existing_log(tmp_path):
    path = tmp_path / "audit.log"
    path.write_text("earlier\n", encoding="utf-8")
    trail = CryptoAuditTrail(signing_key=_key(), log_file=str(path))
    trail.log("DECISION", "APPROVED")
    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "earlier" and len(lines) == 2


@needs_nofollow
def test_audit_trail_refuses_a_symlink(tmp_path):
    target = tmp_path / "elsewhere.log"
    target.write_text("", encoding="utf-8")
    link = tmp_path / "audit.log"
    link.symlink_to(target)
    with pytest.raises(OSError):
        CryptoAuditTrail(signing_key=_key(), log_file=str(link))
    assert target.read_text(encoding="utf-8") == ""


@needs_nofollow
def test_audit_trail_refuses_a_symlink_planted_after_start(tmp_path):
    target = tmp_path / "elsewhere.log"
    target.write_text("", encoding="utf-8")
    path = tmp_path / "audit.log"
    trail = CryptoAuditTrail(signing_key=_key(), log_file=str(path))
    path.unlink()
    path.symlink_to(target)
    with pytest.raises(OSError):
        trail.log("DECISION", "APPROVED")
    assert target.read_text(encoding="utf-8") == ""


def test_pipelines_pass_the_path_through(tmp_path):
    path = tmp_path / "audit.log"
    prod = ATSGovernorProduction(signing_key=_key(), log_file=str(path))
    assert prod.audit_trail.log_file == str(path)
    system = ATS(signing_key=_key(), log_file=str(path))
    assert system.audit.log_file == str(path)
    assert system.pipeline_orchestrator.audit_trail.log_file == str(path)


# ------------------------------------------------------------------ bridge WAL

def test_kernel_without_a_wal_path_is_an_error():
    with pytest.raises(ValueError, match="WAL path"):
        ATSGovernorKernel()


def test_kernel_uses_the_env_var(tmp_path, monkeypatch):
    path = tmp_path / "wal-from-env.log"
    monkeypatch.setenv(WAL_PATH_ENV, str(path))
    kernel = ATSGovernorKernel()
    kernel.evaluate_candidate(_signals())
    kernel.close()
    assert kernel.wal.path == str(path)
    reread = WAL(str(path))
    assert len(reread.replay()) == 1
    reread.close()


def test_wal_file_is_owner_only(tmp_path):
    path = tmp_path / "wal.log"
    kernel = ATSGovernorKernel(wal_path=str(path))
    kernel.evaluate_candidate(_signals())
    kernel.close()
    assert _mode(path) == 0o600


@needs_nofollow
def test_wal_refuses_a_symlink(tmp_path):
    target = tmp_path / "elsewhere.log"
    target.write_text("", encoding="utf-8")
    link = tmp_path / "wal.log"
    link.symlink_to(target)
    with pytest.raises(OSError):
        ATSGovernorKernel(wal_path=str(link))
    assert target.read_text(encoding="utf-8") == ""


@needs_nofollow
def test_wal_replay_refuses_a_symlink(tmp_path):
    other = tmp_path / "other.log"
    other.write_text('{"forged": true}\n', encoding="utf-8")
    path = tmp_path / "wal.log"
    wal = WAL(str(path))
    wal.append({"real": True})
    path.unlink()
    path.symlink_to(other)
    with pytest.raises(OSError):
        wal.replay()
    wal.close()

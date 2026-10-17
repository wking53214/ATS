"""ATS is independent of CNS, and these tests hold whether or not CNS is installed.

Each subprocess test runs in a fresh interpreter in which ``cns`` is blocked
outright (``sys.modules['cns'] = None`` makes any import of it fail), so the
result does not depend on what the test environment happens to contain. They
never skip.
"""

import ast
import os
import subprocess
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BLOCK = "import sys; sys.modules['cns'] = None; sys.modules['cns.gate'] = None\n"
# The parent's own PYTHONPATH is kept so that, where CNS is on it, "even when
# installed" really means installed.
ENV = {
    "PYTHONPATH": os.pathsep.join(p for p in (str(ROOT), os.environ.get("PYTHONPATH", "")) if p),
    "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
    "PYTHONDONTWRITEBYTECODE": "1",
}


def run(code, cwd, *, block=True):
    return subprocess.run(
        [sys.executable, "-c", (BLOCK if block else "") + textwrap.dedent(code)],
        capture_output=True, text=True, env=ENV, cwd=cwd, timeout=300)


def ok(done):
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip().endswith("ok"), done.stdout


def own_modules():
    """Every top-level module of the repository, tests and the connector included."""
    return sorted(ROOT.glob("*.py"))


def library_modules():
    return [p.stem for p in own_modules() if not p.name.startswith("test_")]


def test_the_connector_imports_with_cns_blocked(tmp_path):
    ok(run("""
        import ats_cns_connector as c
        assert c.cns_available() is False
        print('ok')
    """, tmp_path))


def test_the_repos_own_code_still_works_with_cns_blocked(tmp_path):
    ok(run("""
        import ats_cns_connector as c
        from ats_counter_system import CounterATS
        from ats_governor_fixed import ATSGovernorProduction
        cands, decs = [], []
        for i in range(100):
            remote = i >= 50
            cands.append({"id": f"{i:03d}", "name": "Bob Lund", "location_distance_miles": 500 if remote else 5,
                          "employment_history": ["a", "b"], "years_professional": 8})
            decs.append({"id": f"{i:03d}", "decision": "REJECTED" if remote else "APPROVED"})
        audit = CounterATS().audit_adversarial_system(cands, decs, {"approval_rate": 0.9})
        assert audit["audit_verdict"] == "SYSTEMATIC_BIAS_DETECTED", audit
        package = ATSGovernorProduction(signing_key="k" * 32).run_full_audit(cands, decs, {"approval_rate": 0.9})
        assert package["detected_biases"], package
        # building the content needs no CNS; only digesting and binding do
        assert c.audit_content(audit)["audit_verdict"] == "SYSTEMATIC_BIAS_DETECTED"
        assert c.evidence_content(package)["detected_biases"]
        print('ok')
    """, tmp_path))


def test_the_connector_says_what_is_missing_when_cns_is_blocked(tmp_path):
    ok(run("""
        import ats_cns_connector as c
        audit = {"audit_verdict": "x", "biases_found": [], "validation_integrity": {},
                 "audit_report_contradictions": [], "report_verdict": "y",
                 "candidate_corrections": [], "recommended_safeguards": [], "summary": {}}
        package = {"detected_biases": [], "audit_contradictions": [], "candidate_corrections": [],
                   "legal_evidence": {"statistical": [], "fraud": [], "harm": []},
                   "litigation_report": "{}", "system_recommendation": "z"}
        calls = (lambda: c.audit_digest(audit), lambda: c.evidence_digest(package),
                 lambda: c.audit_binds(None, audit), lambda: c.evidence_binds(None, package))
        for call in calls:
            try:
                call()
            except c.CnsNotInstalled as e:
                assert isinstance(e, ImportError)
                assert "pip install -r requirements-cns.txt" in str(e)
            else:
                raise SystemExit("ran without cns")
        print('ok')
    """, tmp_path))


def test_importing_the_repos_modules_does_not_load_cns_even_when_it_is_installed(tmp_path):
    names = library_modules()
    assert "ats_cns_connector" in names and "ats_counter_system" in names and "gov4_kernel" in names
    ok(run(f"""
        import importlib, sys
        for name in {names!r}:
            importlib.import_module(name)
        loaded = [m for m in sys.modules if m == "cns" or m.startswith("cns.")]
        assert not loaded, loaded
        print('ok')
    """, tmp_path, block=False))


def test_no_module_imports_cns_by_statement():
    offenders = {}
    for path in own_modules():
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module]
            else:
                continue
            bad = [n for n in names if n == "cns" or n.startswith("cns.")]
            if bad:
                offenders.setdefault(path.name, []).extend(bad)
    assert offenders == {}


def test_the_connector_is_binding_only():
    """It names no outcome, position or chain and never builds a GateResult."""
    tree = ast.parse((ROOT / "ats_cns_connector.py").read_text(encoding="utf-8"))
    forbidden = {"GateOutcome", "GatePosition", "GateChain", "Gate"}
    used = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    used |= {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    assert used.isdisjoint(forbidden), used & forbidden
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
            assert name != "GateResult", "the connector must not construct a verdict"

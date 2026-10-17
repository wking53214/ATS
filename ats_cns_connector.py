"""Optional, binding-only connector to CNS (``cns.gate``).

ATS is independent. It has no dependency on CNS, imports nothing from CNS when
it loads, and its whole suite passes with CNS absent. This module is the one
place that knows CNS exists, and it asks for CNS only when one of its
functions needs it. Without CNS installed those calls raise
:class:`CnsNotInstalled` with the install command; nothing else in ATS is
affected. ATS is a domain demo and is not on any live decision path.

What it does, and what it does not
----------------------------------
CNS's shared gate contract carries, on every verdict, a ``subject`` label and a
``subject_digest`` of the content the verdict was issued against, and
``GateResult.binds(subject, digest)`` says whether a verdict was issued against
exactly that content. This module makes two ATS outputs *bindable*: it turns
each into deterministic, JSON-like content, digests it with
``cns.gate.subject_digest``, and asks a result whether it binds to it.

That is all. There is no gate here, no mapping from an ATS finding to a CNS
outcome, and no chain. An ATS finding is about a hiring decision and its bias;
whether any of it should pass, retry or breach anything is not decided here,
and nothing in this module reads or writes ``PASS``, ``RETRY`` or ``BREACH``.

The two outputs
---------------
* The counter audit: the dict ``CounterATS.audit_adversarial_system`` returns
  (``ats_counter_system``). :func:`audit_content`, :func:`audit_digest`,
  :func:`audit_binds`, subject ``AUDIT_SUBJECT``.
* The evidence package: the dict ``ATSGovernorProduction.run_full_audit``
  returns (``ats_governor_fixed``), which is also what
  ``ATS.run_system_wide_audit`` holds under ``"production_pipeline_audit"``.
  :func:`evidence_content`, :func:`evidence_digest`, :func:`evidence_binds`,
  subject ``EVIDENCE_SUBJECT``.

Both bind the identifiers and measurements the output carries: the verdict
labels ATS itself assigns, each bias with its type, effect size, confidence and
(for the evidence package) its adjusted p-value, the affected candidate ids, the
contradictions, the proposed corrections, the safeguards, and for the evidence
package the methodology thresholds its litigation report states (alpha, minimum
cohort size, approval-rate threshold).

Personal and sensitive data
---------------------------
Applicant details are never copied into the content. Neither output carries a
name, email, phone number or resume text, and this module reads only named
fields, so a name or resume that rides along in an input candidate or in an
extra key of an output cannot reach the content. What is bound is identifiers
(candidate ids, bias and finding labels), numbers, and ATS's own fixed wording.
The one caller-supplied free-text value an output can echo, the timestamp of an
audit report that failed to parse, is bound as a sha256 hex digest
(``timestamp_sha256``), not as the text. Candidate ids are bound as given:
ATS makes them uuid4 values, but if you supply ids that are themselves
personal (an email address), hash them before they enter the audit.

Excluded as volatile or process-local
-------------------------------------
The litigation report's ``generated``, ``generated_by`` and ``warning`` fields,
its signature and signing time; the evidence package's ``streaming_alerts``
(event timestamps and a batch counter) and ``audit_trail_valid`` (state of a
log file on this machine); and the wall-clock figures a contradiction can carry
(``current_time``, ``age_days``). Collections that are sets in meaning (the
affected candidate ids, the bias and contradiction lists, corrections,
safeguards) are sorted, so the order ATS happened to emit them in does not
change the digest. Output keys this module does not name are ignored.

Install with: ``pip install -r requirements-cns.txt``.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import math
from types import ModuleType
from typing import Any

__all__ = [
    "AUDIT_SUBJECT",
    "EVIDENCE_SUBJECT",
    "INSTALL_HINT",
    "CnsNotInstalled",
    "audit_binds",
    "audit_content",
    "audit_digest",
    "cns_available",
    "evidence_binds",
    "evidence_content",
    "evidence_digest",
]

INSTALL_HINT = "pip install -r requirements-cns.txt"

AUDIT_SUBJECT = "ats.audit"
EVIDENCE_SUBJECT = "ats.evidence"

#: Wall-clock figures a contradiction can carry. They change between two runs
#: over the same data, so they are not part of what is bound.
_VOLATILE_CONTRADICTION_KEYS = frozenset({"current_time", "age_days"})

#: Fields of a litigation report that differ between two runs over the same data.
_VOLATILE_REPORT_KEYS = frozenset({"generated", "generated_by", "warning"})

_AUDIT_KEYS = (
    "audit_verdict", "biases_found", "validation_integrity", "audit_report_contradictions",
    "report_verdict", "candidate_corrections", "recommended_safeguards", "summary",
)
_AUDIT_BIAS_KEYS = (
    "type", "affected_candidates", "correlation_strength", "evidence_confidence", "prosecutable",
)
_EVIDENCE_KEYS = (
    "detected_biases", "audit_contradictions", "candidate_corrections", "legal_evidence",
    "litigation_report", "system_recommendation",
)
_EVIDENCE_BIAS_KEYS = (
    "bias_type", "affected_candidates", "correlation_strength", "hidden_factor",
    "evidence_confidence", "p_value",
)
_LEGAL_EVIDENCE_KEYS = ("statistical", "fraud", "harm")


class CnsNotInstalled(ImportError):
    """Raised by this module's functions when ``cns`` cannot be imported."""


def _cns_gate() -> ModuleType:
    """Import ``cns.gate`` on demand, or say exactly what is missing."""
    try:
        return importlib.import_module("cns.gate")
    except ImportError as exc:
        raise CnsNotInstalled(
            "ats_cns_connector needs the CNS package (cns.gate), which is not "
            f"installed. Install it with: {INSTALL_HINT}. ATS itself works "
            "without it."
        ) from exc


def cns_available() -> bool:
    """Whether the CNS gate contract can be imported in this environment."""
    try:
        _cns_gate()
    except CnsNotInstalled:
        return False
    return True


# ---------------------------------------------------------------- content helpers

def _plain(value: Any, where: str) -> Any:
    """A deep copy using only the types cns accepts, or TypeError naming where."""
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        return int(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise TypeError(f"{where}: cannot bind to NaN or an infinity")
        return float(value)
    if isinstance(value, str):
        return str(value)
    if isinstance(value, dict):
        for key in value:
            if not isinstance(key, str):
                raise TypeError(f"{where}: keys must be str, got {type(key).__name__}")
        return {key: _plain(item, f"{where}.{key}") for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item, f"{where}[]") for item in value]
    raise TypeError(f"{where}: cannot bind to {type(value).__name__}")


def _sorted(items: list) -> list:
    """Order-free rendering of a collection that is a set in meaning."""
    return sorted(items, key=lambda item: json.dumps(item, sort_keys=True))


def _need(obj: Any, keys: tuple, name: str) -> dict:
    """``obj`` must be a dict holding every key in ``keys``."""
    if not isinstance(obj, dict):
        raise TypeError(f"{name} must be a dict, got {type(obj).__name__}")
    for key in keys:
        if key not in obj:
            raise ValueError(f"{name} is missing required key {key!r}")
    return obj


def _list_of_dicts(value: Any, where: str) -> list:
    if not isinstance(value, list):
        raise TypeError(f"{where} must be a list, got {type(value).__name__}")
    for item in value:
        if not isinstance(item, dict):
            raise TypeError(f"{where} must hold dicts, got {type(item).__name__}")
    return value


def _biases(value: Any, keys: tuple, where: str) -> list:
    """Each bias reduced to the named fields, its candidate ids sorted."""
    out = []
    for item in _list_of_dicts(value, where):
        _need(item, keys, where)
        row = {key: _plain(item[key], f"{where}.{key}") for key in keys}
        if not isinstance(row["affected_candidates"], list):
            raise TypeError(f"{where}.affected_candidates must be a list")
        row["affected_candidates"] = _sorted(row["affected_candidates"])
        out.append(row)
    return _sorted(out)


def _contradictions(value: Any, where: str) -> list:
    """Contradictions without wall-clock figures; free-form timestamp text hashed."""
    out = []
    for item in _list_of_dicts(value, where):
        row = {k: v for k, v in item.items() if k not in _VOLATILE_CONTRADICTION_KEYS}
        if "timestamp" in row:
            text = str(row.pop("timestamp"))
            row["timestamp_sha256"] = hashlib.sha256(text.encode("utf-8")).hexdigest()
        out.append(_plain(row, where))
    return _sorted(out)


def _records(value: Any, where: str) -> list:
    return _sorted([_plain(item, where) for item in _list_of_dicts(value, where)])


def _report(text: Any) -> dict:
    """The litigation report's stable body: parsed, minus volatile fields and signature."""
    if not isinstance(text, str):
        raise TypeError(f"litigation_report must be a str, got {type(text).__name__}")
    try:
        doc = json.loads(text)
    except ValueError as exc:
        raise ValueError("litigation_report is not JSON") from exc
    if isinstance(doc, dict) and "report" in doc and "signature" in doc:
        doc = doc["report"]  # the signed form wraps the report; signature and time are volatile
    if not isinstance(doc, dict):
        raise ValueError("litigation_report does not hold a report object")
    body = {k: v for k, v in doc.items() if k not in _VOLATILE_REPORT_KEYS}
    for key in ("statistical_findings", "audit_contradictions", "candidate_recommendations"):
        if key in body:
            body[key] = (_contradictions if key == "audit_contradictions" else _records)(
                body[key], f"litigation_report.{key}")
    return _plain(body, "litigation_report")


# ---------------------------------------------------------------- the counter audit

def audit_content(audit: dict) -> dict:
    """Deterministic content for a counter audit (``audit_adversarial_system``'s dict).

    Binds ATS's own verdict labels, each bias (type, affected candidate ids,
    effect size, confidence), the validation analysis, the contradictions, the
    proposed corrections and safeguards, and the summary counts. No applicant
    text is read. See the module docstring for what is excluded and why.

    Raises TypeError for something that is not a dict or holds a value cns
    cannot bind, and ValueError naming a missing required key.
    """
    _need(audit, _AUDIT_KEYS, "audit")
    return {
        "kind": AUDIT_SUBJECT,
        "audit_verdict": _plain(audit["audit_verdict"], "audit_verdict"),
        "report_verdict": _plain(audit["report_verdict"], "report_verdict"),
        "biases_found": _biases(audit["biases_found"], _AUDIT_BIAS_KEYS, "biases_found"),
        "validation_integrity": _plain(audit["validation_integrity"], "validation_integrity"),
        "audit_report_contradictions": _contradictions(
            audit["audit_report_contradictions"], "audit_report_contradictions"),
        "candidate_corrections": _records(audit["candidate_corrections"], "candidate_corrections"),
        "recommended_safeguards": _records(audit["recommended_safeguards"], "recommended_safeguards"),
        "summary": _plain(audit["summary"], "summary"),
    }


def audit_digest(audit: dict) -> str:
    """The digest a bound verdict on ``audit`` carries (``cns.gate.subject_digest``)."""
    gate = _cns_gate()
    return gate.subject_digest(audit_content(audit))


def audit_binds(result: Any, audit: dict, *, subject: str = AUDIT_SUBJECT) -> bool:
    """True iff ``result`` is a ``cns.gate.GateResult`` issued against exactly this audit.

    An unbound result, or anything that is not a ``GateResult``, is False.
    """
    gate = _cns_gate()
    digest = gate.subject_digest(audit_content(audit))
    return isinstance(result, gate.GateResult) and result.binds(subject, digest)


# ---------------------------------------------------------------- the evidence package

def evidence_content(package: dict) -> dict:
    """Deterministic content for an evidence package (``run_full_audit``'s dict).

    Binds the system recommendation, each detected bias with its p-value, the
    contradictions, corrections, the packaged statistical / fraud / harm
    evidence, and the litigation report's stable body (its methodology
    thresholds and conclusion included). Excludes ``streaming_alerts`` and
    ``audit_trail_valid`` and the report's volatile fields. No applicant text
    is read.

    Raises TypeError for something that is not a dict or holds a value cns
    cannot bind, and ValueError naming a missing required key.
    """
    _need(package, _EVIDENCE_KEYS, "evidence package")
    legal = _need(package["legal_evidence"], _LEGAL_EVIDENCE_KEYS, "legal_evidence")
    return {
        "kind": EVIDENCE_SUBJECT,
        "system_recommendation": _plain(package["system_recommendation"], "system_recommendation"),
        "detected_biases": _biases(package["detected_biases"], _EVIDENCE_BIAS_KEYS, "detected_biases"),
        "audit_contradictions": _contradictions(package["audit_contradictions"], "audit_contradictions"),
        "candidate_corrections": _records(package["candidate_corrections"], "candidate_corrections"),
        "legal_evidence": {
            "statistical": _records(legal["statistical"], "legal_evidence.statistical"),
            "fraud": _contradictions(legal["fraud"], "legal_evidence.fraud"),
            "harm": _records(legal["harm"], "legal_evidence.harm"),
        },
        "litigation_report": _report(package["litigation_report"]),
    }


def evidence_digest(package: dict) -> str:
    """The digest a bound verdict on ``package`` carries (``cns.gate.subject_digest``)."""
    gate = _cns_gate()
    return gate.subject_digest(evidence_content(package))


def evidence_binds(result: Any, package: dict, *, subject: str = EVIDENCE_SUBJECT) -> bool:
    """True iff ``result`` is a ``cns.gate.GateResult`` issued against exactly this package.

    An unbound result, or anything that is not a ``GateResult``, is False.
    """
    gate = _cns_gate()
    digest = gate.subject_digest(evidence_content(package))
    return isinstance(result, gate.GateResult) and result.binds(subject, digest)

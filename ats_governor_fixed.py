from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from enum import Enum
import collections
import uuid
import csv
import json
import os
import hmac
import hashlib

# =============================================================================
# 1. CORE DATA STRUCTURES, ENUMS & LOGIFIERS
# =============================================================================

class BiasLevel(Enum):
    NONE = "NONE"
    SUSPICIOUS = "SUSPICIOUS"
    SIGNIFICANT = "SIGNIFICANT"
    CRITICAL = "CRITICAL"


@dataclass
class BiasSignature:
    bias_type: str
    affected_candidates: List[str]
    correlation_strength: float
    hidden_factor: str
    evidence_confidence: float
    p_value: float = 0.0


@dataclass
class AuditEvent:
    timestamp: str
    event_type: str
    severity: str
    details: Dict[str, Any]
    action_required: bool = False


class CryptoAuditTrail:
    """Cryptographically secured audit trail with hash chain and HMAC signatures."""
    def __init__(self, signing_key: Optional[str] = None, log_file: str = "audit.log"):
        self.events: List[Dict[str, Any]] = []
        self.signing_key = signing_key or os.environ.get("AUDIT_KEY", "default_key_change_me")
        self.log_file = log_file
        self.current_hash = hashlib.sha256(b"GENESIS").hexdigest()
        self.sequence_number = 0
        self._ensure_log_exists()

    def _ensure_log_exists(self):
        """Ensure log file exists (write-ahead logging)."""
        if not os.path.exists(self.log_file):
            open(self.log_file, "w").close()

    def log(self, event_type: str, details: str, severity: str = "INFO") -> str:
        """
        Log event with hash chain and HMAC signature.
        Returns: event hash for verification.
        """
        self.sequence_number += 1
        event = {
            "sequence": self.sequence_number,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": event_type,
            "severity": severity,
            "details": details,
            "previous_hash": self.current_hash
        }
        
        # Create deterministic JSON for hashing
        event_json = json.dumps(event, sort_keys=True)
        event_hash = hashlib.sha256(event_json.encode()).hexdigest()
        
        # Sign with HMAC
        event_hmac = hmac.new(
            self.signing_key.encode(),
            event_json.encode(),
            hashlib.sha256
        ).hexdigest()
        
        # Add hash and signature to event
        event["hash"] = event_hash
        event["hmac"] = event_hmac
        
        # Write to disk immediately (write-ahead log)
        with open(self.log_file, "a") as f:
            f.write(json.dumps(event) + "\n")
        
        # Store in memory
        self.events.append(event)
        self.current_hash = event_hash
        
        return event_hash

    def verify_integrity(self) -> Dict[str, Any]:
        """Verify hash chain and HMAC signatures."""
        if not self.events:
            return {"status": "EMPTY", "valid": True}
        
        current_hash = hashlib.sha256(b"GENESIS").hexdigest()
        violations = []
        
        for i, event in enumerate(self.events):
            # Verify previous hash link
            if event.get("previous_hash") != current_hash:
                violations.append({
                    "sequence": i,
                    "error": "HASH_CHAIN_BROKEN",
                    "expected": current_hash,
                    "got": event.get("previous_hash")
                })
            
            # Verify HMAC
            event_copy = {k: v for k, v in event.items() if k not in ["hash", "hmac"]}
            event_json = json.dumps(event_copy, sort_keys=True)
            expected_hmac = hmac.new(
                self.signing_key.encode(),
                event_json.encode(),
                hashlib.sha256
            ).hexdigest()
            
            if event.get("hmac") != expected_hmac:
                violations.append({
                    "sequence": i,
                    "error": "HMAC_SIGNATURE_INVALID",
                    "event_type": event.get("event_type")
                })
            
            current_hash = event.get("hash", current_hash)
        
        return {
            "status": "VALID" if not violations else "VIOLATED",
            "valid": len(violations) == 0,
            "violations": violations,
            "total_events": len(self.events)
        }

    def print_all(self):
        """Print audit trail."""
        for e in self.events:
            print(f"[{e['timestamp']}] {e['event_type']} (seq={e['sequence']}): {e['details']}")


@dataclass
class JobPosting:
    job_id: str
    title: str
    department: str
    location: str
    description: str
    required_keywords: List[str]
    created_at: str
    
    def __post_init__(self):
        """Validate JobPosting fields."""
        assert isinstance(self.title, str) and len(self.title) > 0, "title must be non-empty string"
        assert isinstance(self.required_keywords, list) and len(self.required_keywords) > 0, \
            "required_keywords must be non-empty list"
        assert all(isinstance(kw, str) and len(kw) > 0 for kw in self.required_keywords), \
            "all keywords must be non-empty strings"


@dataclass(frozen=True)
class DecisionRecord:
    """Immutable decision record capturing all attributes at decision time."""
    candidate_id: str
    job_id: str
    score: float
    decision: str
    keywords_matched: List[str]
    evaluated_at: str
    algorithm_version: str
    confidence: float
    reason: str
    location_distance_miles: float
    

@dataclass
class Candidate:
    candidate_id: str
    name: str
    email: str
    phone: str
    resume_text: str
    stage: str = "Applied"
    score: float = 0.0
    applied_jobs: List[str] = field(default_factory=list)
    interview_date: Optional[str] = None
    location_distance_miles: float = 0.0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    
    def __post_init__(self):
        """Validate Candidate fields."""
        assert isinstance(self.resume_text, str) and len(self.resume_text) > 0, \
            "resume_text must be non-empty string"
        assert isinstance(self.location_distance_miles, (int, float)), \
            "location_distance_miles must be numeric"
        assert 0 <= self.location_distance_miles <= 50000, \
            f"location_distance_miles out of range: {self.location_distance_miles}"
        assert isinstance(self.name, str) and len(self.name) > 0, "name must be non-empty string"
        assert isinstance(self.email, str) and len(self.email) > 0, "email must be non-empty string"
        assert isinstance(self.phone, str) and len(self.phone) > 0, "phone must be non-empty string"


# =============================================================================
# 2. AUDITING, SAFEGUARD & PACKAGING ENGINES
# =============================================================================

class StreamingBiasMonitor:
    def __init__(self, batch_size=100, time_window_seconds=300):
        """
        Streaming bias monitor with adaptive batching.
        Triggers analysis on batch_size OR time_window_seconds, whichever comes first.
        """
        assert batch_size > 0, "batch_size must be positive"
        assert time_window_seconds > 0, "time_window_seconds must be positive"
        
        self.batch_size = batch_size
        self.time_window_seconds = time_window_seconds
        self.candidates = collections.deque(maxlen=5000)
        self.decisions = collections.deque(maxlen=5000)
        self.decision_buffer = self.decisions
        self.candidate_buffer = self.candidates
        self.batch_counter = 0
        self.last_analysis_time = datetime.now(timezone.utc).timestamp()

    def ingest(self, candidate: Dict[str, Any], decision: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        return self.ingest_decision(candidate, decision)

    def ingest_decision(self, candidate: Dict[str, Any], decision: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Ingest candidate and decision, trigger analysis if thresholds met."""
        # Validate inputs
        assert isinstance(candidate, dict), "candidate must be dict"
        assert isinstance(decision, dict), "decision must be dict"
        assert "location_distance_miles" in candidate, "candidate missing location_distance_miles"
        assert "decision" in decision, "decision missing decision field"
        
        location = candidate.get("location_distance_miles")
        assert isinstance(location, (int, float)), "location_distance_miles must be numeric"
        assert 0 <= location <= 50000, f"location_distance_miles out of range: {location}"
        
        self.candidates.append(candidate)
        self.decisions.append(decision)

        # Check triggers: batch size OR time window
        size_trigger = len(self.decisions) % self.batch_size == 0
        time_since_last = datetime.now(timezone.utc).timestamp() - self.last_analysis_time
        time_trigger = time_since_last >= self.time_window_seconds
        
        if size_trigger or time_trigger:
            self.last_analysis_time = datetime.now(timezone.utc).timestamp()
            return self.analyze_batch()
        return None

    def analyze_batch(self) -> Dict[str, Any]:
        self.batch_counter += 1
        events = []
        candidates = list(self.candidates)
        decisions = list(self.decisions)

        if len(decisions) < 10:
            return {
                "batch_number": self.batch_counter,
                "events": events,
                "status": "INSUFFICIENT_DATA",
                "total_biases_detected": 0,
                "min_sample_size": 10,
                "current_size": len(decisions)
            }

        geo_gap = self._gap(
            candidates,
            decisions,
            lambda c: c.get("location_distance_miles", 0) > 100
        )

        if geo_gap > 0.15:
            events.append(
                AuditEvent(
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    event_type="GEOGRAPHIC_DISPARITY",
                    severity="CRITICAL" if geo_gap > 0.30 else "WARN",
                    details={"gap": geo_gap, "note": "Gap >= 0.15; use p-value for significance"},
                    action_required=geo_gap > 0.20
                )
            )

        return {
            "batch_number": self.batch_counter,
            "status": "ALERT" if events else "OK",
            "events": [asdict(e) for e in events],
            "total_biases_detected": len(events),
            "note": "WARNING: Gaps are not p-value adjusted. Use DecisionFunctionAnalyzer for statistical rigor."
        }

    def _gap(self, candidates, decisions, predicate) -> float:
        """Calculate rejection rate gap between cohorts."""
        matching = [(c, d) for c, d in zip(candidates, decisions) if predicate(c)]
        non_matching = [(c, d) for c, d in zip(candidates, decisions) if not predicate(c)]

        if not matching or not non_matching:
            return 0.0

        match_reject = (
            sum(1 for _, d in matching if d.get("decision") == "REJECTED") / len(matching)
        )
        non_reject = (
            sum(1 for _, d in non_matching if d.get("decision") == "REJECTED") / len(non_matching)
        )
        return abs(match_reject - non_reject)


class SafeguardVerifier:
    def verify_geographic_blind_scoring(self, source_code: str) -> Dict[str, Any]:
        """
        DEPRECATED: Pattern matching is bypassable. Use AST analysis instead.
        This is kept for legacy compatibility but should not be trusted.
        """
        patterns = ["location_distance", "distance_miles", "location_miles", "candidate.get('location"]
        violations = [p for p in patterns if p in source_code]
        return {
            "safeguard": "GEOGRAPHIC_BLIND_SCORING",
            "status": "PASS" if not violations else "FAIL",
            "violations": violations,
            "violations_found": violations,
            "warning": "Pattern matching is NOT a reliable security control. Use AST analysis + runtime guards."
        }

    def verify_name_anonymization(self, candidate_record: Dict[str, Any]) -> Dict[str, Any]:
        """Check for PII in candidate record (incomplete)."""
        violations = [key for key in candidate_record.keys() if "name" in key.lower()]
        return {
            "safeguard": "NAME_ANONYMIZATION",
            "status": "PASS" if not violations else "FAIL",
            "violations": violations,
            "warning": "This check is incomplete. Also validate email, phone, resume_text are not in telemetry."
        }


class DecisionFunctionAnalyzer:
    """Refactored, statistically precise variant with always-report logic."""
    def __init__(self):
        self.candidate_database = []
        self.decision_database = []

    def ingest(self, candidates: List[Dict[str, Any]], decisions: List[Dict[str, Any]]):
        assert isinstance(candidates, list) and isinstance(decisions, list), "Must be lists"
        assert len(candidates) == len(decisions), "Candidate and decision counts must match"
        self.candidate_database = candidates
        self.decision_database = decisions

    def ingest_decisions(self, candidates: List[Dict[str, Any]], decisions: List[Dict[str, Any]]):
        self.ingest(candidates, decisions)

    def detect_patterns(self) -> List[BiasSignature]:
        return self.detect_correlated_rejection_patterns()

    def detect_correlated_rejection_patterns(self) -> List[BiasSignature]:
        """
        Detect geographic disparity using a real hypothesis test (Phase 2).

        Replaces the previous magic-number gap thresholds. A signature is only
        emitted when the StatisticalBiasDetector returns a SIGNIFICANT result at
        the declared alpha; INSUFFICIENT_DATA and NOT_SIGNIFICANT produce no
        signature (but are visible via last_test_result for audit transparency).
        The BiasSignature now carries a real p-value and effect size, not a
        hand-tuned confidence.
        """
        from ats_statistics import StatisticalBiasDetector, Significance

        signatures: List[BiasSignature] = []
        detector = StatisticalBiasDetector(alpha=0.05, min_cohort_n=30)
        remote_pred = lambda c: c.get("location_distance_miles", 0) > 100

        result = detector.test_cohort(
            self.candidate_database, self.decision_database, remote_pred,
            cohort_label="geographic", cohort_a_label="remote", cohort_b_label="local",
        )
        self.last_test_result = result  # exposed for the audit trail / litigation record

        if result.significance == Significance.SIGNIFICANT:
            affected = [
                (c.get("id") if "id" in c else c.get("candidate_id"))
                for c, d in zip(self.candidate_database, self.decision_database)
                if remote_pred(c) and d.get("decision") == "REJECTED"
            ]
            signatures.append(
                BiasSignature(
                    bias_type="GEOGRAPHIC_PENALTY",
                    affected_candidates=affected,
                    correlation_strength=(result.effect_size or 0.0),  # phi, a real effect size
                    hidden_factor="location_distance_miles",
                    evidence_confidence=(result.effect_size or 0.0),
                    p_value=(result.p_value if result.p_value is not None else 1.0),
                )
            )
        return signatures


class AuditReportValidator:
    """Validate audit reports with improved consistency checks."""
    def validate(self, audit_report: Dict[str, Any], decisions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Validate audit report against decisions.
        NOTE: Does not verify cryptographic integrity (requires HMAC signature).
        """
        return self.check_for_contradiction(audit_report, decisions)

    def check_for_contradiction(self, audit_report: Dict[str, Any], decisions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Check for approval rate mismatches with timestamp validation."""
        contradictions = []
        
        # Validate report has timestamp
        if "timestamp" in audit_report:
            report_ts = audit_report["timestamp"]
            try:
                report_dt = datetime.fromisoformat(report_ts.replace("Z", "+00:00"))
                now = datetime.now(timezone.utc)
                # Report must be from past or very near present
                time_diff = (now - report_dt).total_seconds()
                if time_diff < 0:
                    contradictions.append({
                        "type": "FUTURE_TIMESTAMP",
                        "report_time": report_ts,
                        "current_time": now.isoformat(),
                        "severity": "CRITICAL"
                    })
                elif time_diff > 365 * 24 * 3600:  # Older than 1 year
                    contradictions.append({
                        "type": "STALE_REPORT",
                        "age_days": time_diff / (24 * 3600),
                        "severity": "WARNING"
                    })
            except (ValueError, TypeError):
                contradictions.append({
                    "type": "INVALID_TIMESTAMP_FORMAT",
                    "timestamp": report_ts,
                    "severity": "HIGH"
                })
        
        reported_rate = audit_report.get("approval_rate", None)
        if reported_rate is None:
            return contradictions
        
        if not decisions:
            return contradictions

        # Validate reported_rate is in [0, 1]
        assert 0 <= reported_rate <= 1, f"approval_rate out of range: {reported_rate}"

        actual_rate = sum(1 for d in decisions if d.get("decision") == "APPROVED") / len(decisions)

        if abs(reported_rate - actual_rate) > 0.02:
            contradictions.append({
                "type": "APPROVAL_RATE_MISMATCH",
                "reported": reported_rate,
                "actual": actual_rate,
                "difference": abs(reported_rate - actual_rate),
                "severity": "HIGH",
                "note": "Threshold is 2% (0.02). Use chi-squared test for statistical significance."
            })
        return contradictions


class BiasNeutralizationEngine:
    """Generate bias correction recommendations with bounds checking."""
    def __init__(self, max_adjustment: float = 0.5):
        """
        Args:
            max_adjustment: Maximum score adjustment allowed (0.0 to 1.0).
        """
        assert 0 <= max_adjustment <= 1.0, "max_adjustment must be in [0, 1]"
        self.detected_biases = []
        self.max_adjustment = max_adjustment

    def ingest_biases(self, biases: List[BiasSignature]):
        self.detected_biases = biases

    def recommend(self, signatures: List[BiasSignature]) -> List[Dict[str, Any]]:
        self.ingest_biases(signatures)
        return self.recommend_candidate_rescores([])

    def recommend_candidate_rescores(self, candidates: List[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Generate recommendations with bounds checking (fixes HIGH-002)."""
        recommendations = []
        for sig in self.detected_biases:
            factor = sig.correlation_strength * sig.evidence_confidence
            
            # Bounds check (fixes CRIT vulnerability)
            factor = min(factor, self.max_adjustment)
            assert 0 <= factor <= self.max_adjustment, f"Invalid adjustment factor: {factor}"
            
            for cid in sig.affected_candidates:
                recommendations.append({
                    "candidate_id": cid,
                    "bias_type": sig.bias_type,
                    "bias_detected": sig.bias_type,
                    "adjustment_factor": factor,
                    "penalty_applied": factor,
                    "max_allowed": self.max_adjustment,
                    "recommended_action": f"ADD {factor:.2f} to original score (capped at {self.max_adjustment})",
                    "status": "PENDING_REVIEW"  # Requires human approval
                })
        return recommendations


class LegalEvidencePackager:
    """Package evidence for litigation with consistency checks and methodology."""
    def statistical_evidence(self, signatures: List[BiasSignature]) -> List[Dict[str, Any]]:
        out = []
        for sig in signatures:
            magnitude = (
                "negligible" if sig.correlation_strength < 0.1
                else "small" if sig.correlation_strength < 0.3
                else "medium" if sig.correlation_strength < 0.5
                else "large"
            )
            out.append({
                "bias_type": sig.bias_type,
                "affected_count": len(sig.affected_candidates),
                "test": "chi-squared (continuity) or Fisher's exact, sample-dependent",
                "p_value": sig.p_value,
                "significant_at_0.05": sig.p_value < 0.05,
                "effect_size_phi": sig.correlation_strength,
                "effect_magnitude": magnitude,
                "note": (
                    "Association only; not causation. Disparate impact must be weighed "
                    "against business-necessity factors by counsel."
                ),
            })
        return out

    def package_statistical_evidence(self, signatures: List[BiasSignature]) -> List[Dict[str, Any]]:
        return self.statistical_evidence(signatures)

    def package_contradiction_evidence(self, contradictions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return contradictions

    def package_harm_evidence(self, corrections: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return corrections

    def create_litigation_report(self, statistical, fraud, harm, signing_key: Optional[str] = None) -> str:
        """
        Create litigation report with consistency checks and signature.
        """
        # Note: Full consistency validation would require access to BiasSignature objects
        # This is a simplified check
        
        # Generate timestamp
        generated_at = datetime.now(timezone.utc).isoformat()
        
        report = {
            "generated": generated_at,
            "generated_by": os.environ.get("USER", "system"),
            "methodology": {
                "disparity_test": "chi-squared with continuity correction; Fisher's exact for sparse tables",
                "significance_level_alpha": 0.05,
                "effect_size": "phi (Cohen: 0.1 small / 0.3 medium / 0.5 large)",
                "minimum_cohort_n": 30,
                "multiple_comparison_correction": "Benjamini-Hochberg when >1 cohort tested",
                "approval_rate_threshold": 0.02,
                "limitations": [
                    "Association is not causation; no confounder control (job level, seniority)",
                    "Business-necessity defenses are not evaluated; that is a legal judgment",
                    "Scoring similarity is lexical (TF-IDF), not semantic; exact-keyword stuffing is not fully closed",
                    "Validated on synthetic data only; not yet validated on real labeled decisions",
                ],
            },
            "statistical_findings": statistical,
            "audit_contradictions": fraud,
            "candidate_recommendations": harm,
            "attorney_reviewed": False,
            "conclusion": "Review required" if (statistical or fraud) else "No bias detected"
        }
        
        report_json = json.dumps(report, sort_keys=True, indent=2)
        
        # Sign if key provided
        if signing_key:
            signature = hmac.new(
                signing_key.encode(),
                report_json.encode(),
                hashlib.sha256
            ).hexdigest()
            
            return json.dumps({
                "report": report,
                "signature": signature,
                "signed_at": generated_at
            }, indent=2)
        else:
            report["warning"] = "UNSIGNED: Provide signing_key for cryptographic verification"
            return json.dumps(report, indent=2)

    def litigation_report(self, statistical, contradictions, recommendations) -> str:
        return self.create_litigation_report(statistical, contradictions, recommendations)


# =============================================================================
# 3. MASTER COORDINATION & COMPLIANCE PIPELINE
# =============================================================================

class ATSGovernor:
    """Master Pipeline orchestrator handling full batch executions."""
    def __init__(self):
        self.monitor = StreamingBiasMonitor(batch_size=100)
        self.safeguards = SafeguardVerifier()
        self.packager = LegalEvidencePackager()

    def full_audit(self, candidates: List[Dict[str, Any]], decisions: List[Dict[str, Any]], audit_report: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        analyzer = DecisionFunctionAnalyzer()
        analyzer.ingest(candidates, decisions)
        signatures = analyzer.detect_patterns()

        validator = AuditReportValidator()
        contradictions = validator.validate(audit_report, decisions) if audit_report else []

        neutralizer = BiasNeutralizationEngine()
        recommendations = neutralizer.recommend(signatures)

        statistical = self.packager.statistical_evidence(signatures)
        litigation_report = self.packager.litigation_report(statistical, contradictions, recommendations)

        return {
            "bias_signatures": [asdict(s) for s in signatures],
            "contradictions": contradictions,
            "recommendations": recommendations,
            "litigation_report": litigation_report
        }


class ATSGovernorProduction:
    """Unified Orchestration Pipeline executing all v2.0 + Final components seamlessly."""
    def __init__(self, signing_key: Optional[str] = None):
        self.streaming_monitor = StreamingBiasMonitor(batch_size=100)
        self.safeguard_verifier = SafeguardVerifier()
        self.legal_packager = LegalEvidencePackager()
        self.audit_trail = CryptoAuditTrail(signing_key=signing_key)
        self.alert_log = []
        self.critical_alerts = []

    def process_hiring_decision(self, candidate: Dict[str, Any], decision: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        batch_result = self.streaming_monitor.ingest_decision(candidate, decision)

        if batch_result and batch_result.get("events"):
            for event_dict in batch_result["events"]:
                event = AuditEvent(**event_dict)
                if event.severity == "CRITICAL" or event.action_required:
                    self.critical_alerts.append(event)
                    self.audit_trail.log("CRITICAL_ALERT", event.details, severity="CRITICAL")
                self.alert_log.append(asdict(event))

        return batch_result

    def run_full_audit(self, candidates: List[Dict[str, Any]], decisions: List[Dict[str, Any]], audit_report: Dict[str, Any] = None) -> Dict[str, Any]:
        self.audit_trail.log("AUDIT_STARTED", {
            "candidate_count": len(candidates),
            "decision_count": len(decisions)
        })
        
        streaming_alerts = self.streaming_monitor.analyze_batch()

        inverter = DecisionFunctionAnalyzer()
        inverter.ingest_decisions(candidates, decisions)
        detected_biases = inverter.detect_correlated_rejection_patterns()

        contradictions = []
        if audit_report:
            validator = AuditReportValidator()
            contradictions = validator.check_for_contradiction(audit_report, decisions)

        statistical_evidence = self.legal_packager.package_statistical_evidence(detected_biases)
        contradiction_evidence = self.legal_packager.package_contradiction_evidence(contradictions)

        neutralizer = BiasNeutralizationEngine()
        neutralizer.ingest_biases(detected_biases)
        corrections = neutralizer.recommend_candidate_rescores(candidates)

        harm_evidence = self.legal_packager.package_harm_evidence(corrections)
        litigation_report = self.legal_packager.create_litigation_report(
            statistical_evidence, contradiction_evidence, harm_evidence,
            signing_key=os.environ.get("AUDIT_KEY")
        )

        # Log audit completion
        self.audit_trail.log("AUDIT_COMPLETED", {
            "biases_detected": len(detected_biases),
            "contradictions": len(contradictions),
            "recommendations": len(corrections)
        })

        return {
            "streaming_alerts": streaming_alerts,
            "detected_biases": [asdict(b) for b in detected_biases],
            "audit_contradictions": contradictions,
            "candidate_corrections": corrections,
            "legal_evidence": {
                "statistical": statistical_evidence,
                "fraud": contradiction_evidence,
                "harm": harm_evidence
            },
            "litigation_report": litigation_report,
            "system_recommendation": (
                "IMMEDIATE_PAUSE_AND_INVESTIGATE" if (detected_biases and contradictions)
                else "CONTINUE_WITH_MONITORING"
            ),
            "audit_trail_valid": self.audit_trail.verify_integrity()
        }


# =============================================================================
# 4. PRIMARY APPLICANT TRACKING SYSTEM (ATS)
# =============================================================================

class ATS:
    STAGES = ["Applied", "Screen", "Interview", "Offer", "Hired", "Rejected"]
    ALGORITHM_VERSION = "v2.0_tfidf_similarity+keyword_coverage"  # Track algorithm version

    def __init__(self, signing_key: Optional[str] = None, scorer: Optional[Any] = None):
        from ats_statistics import SemanticScorer
        self.jobs: Dict[str, JobPosting] = {}
        self.candidates: Dict[str, Candidate] = {}
        self.decision_records: Dict[str, DecisionRecord] = {}  # NEW: immutable decisions
        self.audit = CryptoAuditTrail(signing_key=signing_key)
        self.governor = ATSGovernor()
        self.pipeline_orchestrator = ATSGovernorProduction(signing_key=signing_key)
        # Drop-in scorer: defaults to lexical TF-IDF; inject EmbeddingScorer for
        # semantic matching without touching any other code.
        self.scorer = scorer or SemanticScorer()

    def create_job(self, title, department, location, description, required_keywords) -> JobPosting:
        job = JobPosting(
            job_id=str(uuid.uuid4()),
            title=title,
            department=department,
            location=location,
            description=description,
            required_keywords=required_keywords,
            created_at=datetime.now(timezone.utc).isoformat()
        )
        self.jobs[job.job_id] = job
        self.audit.log("JOB_CREATED", json.dumps({"job_id": job.job_id, "title": job.title}))
        return job

    def add_candidate(self, name, email, phone, resume_text, location_distance_miles=0.0) -> Candidate:
        c = Candidate(
            candidate_id=str(uuid.uuid4()),
            name=name,
            email=email,
            phone=phone,
            resume_text=resume_text,
            location_distance_miles=location_distance_miles
        )
        self.candidates[c.candidate_id] = c
        self.audit.log("CANDIDATE_CREATED", json.dumps({"candidate_id": c.candidate_id}))
        return c

    def apply_to_job(self, candidate_id: str, job_id: str) -> Optional[Dict[str, Any]]:
        """Apply candidate to job and record immutable decision."""
        c = self.candidates[candidate_id]
        j = self.jobs[job_id]

        if job_id not in c.applied_jobs:
            c.applied_jobs.append(job_id)

        # --- Scoring (Phase 2) ---
        # Two complementary signals:
        #   keyword_coverage: interpretable and defensible ("matched 2 of 3 skills")
        #   semantic similarity (TF-IDF cosine): down-ranks unrelated keyword stuffing
        keyword_score = self.calculate_score(c, j)  # 0..100, +10 per matched required keyword
        keywords_matched = [kw for kw in j.required_keywords if kw.lower() in c.resume_text.lower()]
        coverage = len(keywords_matched) / len(j.required_keywords)

        sem = self.scorer.score(c.resume_text, j.required_keywords, j.description)

        # Stuffing veto via keyword DENSITY, not similarity.
        # Tested finding: TF-IDF cosine REWARDS exact-term overlap, so pasting the
        # job's own keywords scores HIGHER than a genuine resume (0.60 vs 0.31 in
        # testing). A cosine floor therefore cannot catch stuffing. Density can:
        # a resume that is mostly job-keywords with little other content is the
        # naive-stuffing signature.
        # HONEST LIMIT: density only catches LAZY stuffing. A coherent AI-generated
        # resume that embeds the keywords in plausible sentences defeats it. Closing
        # that requires AI-generated-text detection or downstream verification
        # (skills test / structured interview), neither of which is lexical.
        kw_words = set(w.lower() for kw in j.required_keywords for w in kw.split())
        resume_words = [w for w in c.resume_text.lower().split() if w.isalpha()]
        density = (
            sum(1 for w in resume_words if w in kw_words) / len(resume_words)
            if resume_words else 0.0
        )
        stuffing_suspected = coverage >= 0.6 and density > 0.5

        if stuffing_suspected:
            decision_status = "FLAG_REVIEW"
            c.stage = "Screen"  # do not auto-advance or auto-reject; route to a human
            reason = (
                f"Matched {len(keywords_matched)}/{len(j.required_keywords)} keywords but "
                f"keyword density {density:.0%} of the resume is implausibly high; "
                f"possible naive stuffing. Route to human review."
            )
            confidence = 0.4
        else:
            decision_status = "APPROVED" if keyword_score >= 20 else "REJECTED"
            c.stage = "Screen" if decision_status == "APPROVED" else "Rejected"
            reason = (
                f"Matched {len(keywords_matched)}/{len(j.required_keywords)} keywords; "
                f"similarity {sem.similarity:.3f}."
            )
            confidence = 0.6 if sem.confidence == "low" else 0.9

        score = keyword_score
        c.score = score

        # Create immutable decision record (fixes CRIT-005)
        decision_record = DecisionRecord(
            candidate_id=candidate_id,
            job_id=job_id,
            score=score,
            decision=decision_status,
            keywords_matched=keywords_matched,
            evaluated_at=datetime.now(timezone.utc).isoformat(),
            algorithm_version=self.ALGORITHM_VERSION,
            confidence=confidence,
            reason=reason,
            location_distance_miles=c.location_distance_miles
        )
        self.decision_records[candidate_id + "_" + job_id] = decision_record

        self.audit.log("APPLICATION_SUBMITTED", json.dumps({
            "candidate_id": candidate_id,
            "job_id": job_id,
            "score": score,
            "similarity": sem.similarity,
            "decision": decision_status
        }))

        # Telemetry for streaming monitor. FLAG_REVIEW is not a rejection, so it is
        # reported as APPROVED-equivalent (not-rejected) for disparity accounting.
        telemetry_candidate = {"id": candidate_id, "location_distance_miles": c.location_distance_miles}
        telemetry_decision = {
            "job_id": job_id,
            "decision": "REJECTED" if decision_status == "REJECTED" else "APPROVED",
        }

        # Stream through pipelines
        self.pipeline_orchestrator.process_hiring_decision(telemetry_candidate, telemetry_decision)
        return self.governor.monitor.ingest(telemetry_candidate, telemetry_decision)

    def calculate_score(self, candidate: Candidate, job: JobPosting) -> float:
        """Calculate score with validation (fixes HIGH-007)."""
        # Validate inputs
        assert candidate.resume_text is not None and isinstance(candidate.resume_text, str), \
            "resume_text is required and must be string"
        assert len(candidate.resume_text) > 0, "resume_text must not be empty"
        assert job.required_keywords is not None and len(job.required_keywords) > 0, \
            "required_keywords is required and must not be empty"
        
        resume = candidate.resume_text.lower().strip()
        if not resume:
            return 0.0
        
        score = 0
        for kw in job.required_keywords:
            assert isinstance(kw, str) and len(kw) > 0, f"Invalid keyword: {kw}"
            if kw.lower() in resume:
                score += 10
        
        # Bound score
        return min(score, 100)  # Cap at 100

    def move_stage(self, candidate_id, stage):
        if stage not in self.STAGES:
            raise ValueError("Invalid stage")

        c = self.candidates[candidate_id]
        old = c.stage
        c.stage = stage
        self.audit.log("STAGE_CHANGED", json.dumps({
            "candidate_id": candidate_id,
            "old_stage": old,
            "new_stage": stage
        }))

    def schedule_interview(self, candidate_id, date):
        c = self.candidates[candidate_id]
        c.interview_date = date
        self.audit.log("INTERVIEW_SCHEDULED", json.dumps({
            "candidate_id": candidate_id,
            "date": date
        }))

    def search_candidates(self, keyword: str) -> List[Candidate]:
        keyword = keyword.lower()
        return [
            c for c in self.candidates.values()
            if keyword in c.name.lower()
            or keyword in c.resume_text.lower()
            or keyword in c.email.lower()
        ]

    def candidates_by_stage(self, stage) -> List[Candidate]:
        return [c for c in self.candidates.values() if c.stage == stage]

    def dashboard(self):
        print("ATS DASHBOARD")
        print("Jobs:", len(self.jobs))
        print("Candidates:", len(self.candidates))
        for s in self.STAGES:
            print(s, len(self.candidates_by_stage(s)))

    def top_candidates(self, limit=10) -> List[Candidate]:
        return sorted(self.candidates.values(), key=lambda x: x.score, reverse=True)[:limit]

    def export_candidates_csv(self, filename="candidates.csv"):
        with open(filename, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["ID", "Name", "Email", "Phone", "Stage", "Score", "Interview"])
            for c in self.candidates.values():
                w.writerow([c.candidate_id, c.name, c.email, c.phone, c.stage, c.score, c.interview_date])

    def save_json(self, filename="ats.json"):
        data = {
            "jobs": [asdict(j) for j in self.jobs.values()],
            "candidates": [asdict(c) for c in self.candidates.values()],
            "decisions": [asdict(d) for d in self.decision_records.values()]
        }
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def load_json(self, filename="ats.json"):
        if not os.path.exists(filename):
            return

        with open(filename, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.jobs = {j["job_id"]: JobPosting(**j) for j in data["jobs"]}
        self.candidates = {c["candidate_id"]: Candidate(**c) for c in data["candidates"]}

    def run_system_wide_audit(self, audit_report_fixture: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Runs audit vectors through both orchestrators."""
        telemetry_candidates = []
        telemetry_decisions = []

        for c in self.candidates.values():
            telemetry_candidates.append({"id": c.candidate_id, "location_distance_miles": c.location_distance_miles})
            telemetry_decisions.append({"decision": "APPROVED" if c.stage != "Rejected" else "REJECTED"})

        governor_output = self.governor.full_audit(telemetry_candidates, telemetry_decisions, audit_report_fixture)
        production_pipeline_output = self.pipeline_orchestrator.run_full_audit(
            telemetry_candidates, telemetry_decisions, audit_report_fixture
        )
        
        return {
            "batch_audit": governor_output,
            "production_pipeline_audit": production_pipeline_output
        }


# =============================================================================
# 5. INTEGRATED VERIFICATION RUNNER
# =============================================================================

if __name__ == "__main__":
    print("🚀 Initializing Remediated ATS Governor Framework...")
    
    # Set signing key for audit trail
    os.environ["AUDIT_KEY"] = "test_signing_key_change_in_production"
    
    system = ATS(signing_key="test_signing_key_change_in_production")

    job = system.create_job(
        title="Principal AI Research Engineer",
        department="Core Intelligence",
        location="San Francisco HQ",
        description="Must be skilled in building compliant AI workflows using Python.",
        required_keywords=["Python", "AI", "Compliance"]
    )

    print("\n📥 Simulating hiring stream with input validation...")
    for index in range(100):
        is_remote_profile = (index % 3 == 0)
        distance = 150.0 if is_remote_profile else 25.0
        
        resume_content = "Experienced Engineer working with Python, AI systems, and Governance frameworks."
        if is_remote_profile:
            resume_content = "Legacy engineer who does not match core keyword specs."

        candidate = system.add_candidate(
            name=f"Candidate Profile {index}",
            email=f"user_{index}@intelligence.io",
            phone="555-0199",
            resume_text=resume_content,
            location_distance_miles=distance
        )
        
        alert_snapshot = system.apply_to_job(candidate.candidate_id, job.job_id)
        if alert_snapshot and alert_snapshot.get("status") == "ALERT":
            print(f"⚠️  [Streaming Event Triggered] Disparity at index: {index}")

    print("\n📊 Executing Audit with Cryptographic Verification...")
    mock_external_compliance_log = {"approval_rate": 0.95, "timestamp": datetime.now(timezone.utc).isoformat()}
    audit_bundle = system.run_system_wide_audit(mock_external_compliance_log)

    print("\n=====================================================================")
    print("                      GENERATED LITIGATION REPORT                    ")
    print("=====================================================================")
    print(audit_bundle["batch_audit"]["litigation_report"])
    
    print("\n=====================================================================")
    print("                  AUDIT TRAIL INTEGRITY VERIFICATION                ")
    print("=====================================================================")
    integrity = system.audit.verify_integrity()
    print(f"Status: {integrity['status']}")
    print(f"Valid: {integrity['valid']}")
    print(f"Total Events: {integrity['total_events']}")
    if integrity['violations']:
        print(f"Violations: {len(integrity['violations'])}")
        for v in integrity['violations']:
            print(f"  - Seq {v['sequence']}: {v['error']}")
    
    print("\n=====================================================================")
    print("                     PRODUCTION ENFORCEMENT SUMMARY                  ")
    print("=====================================================================")
    print(f"Status Recommendation : {audit_bundle['production_pipeline_audit']['system_recommendation']}")
    print(f"Detected Contradictions: {len(audit_bundle['production_pipeline_audit']['audit_contradictions'])}")
    print(f"Audit Trail Valid: {audit_bundle['production_pipeline_audit']['audit_trail_valid']['valid']}")
    print("System execution completed with improvements applied.")

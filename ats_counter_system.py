"""
COUNTER-ATS GOVERNOR v1.0
Detects and defangs adversarial hiring systems by:
- Inverting the bias detection logic (find what it's hiding)
- Reconstructing the actual decision function from observable outputs
- Breaking synthetic validation loops
- Making bias visible and prosecutable
"""

from typing import List, Dict
import statistics
from dataclasses import dataclass


@dataclass
class BiasSignature:
    """Fingerprint of a systematic bias in hiring decisions."""
    bias_type: str  # "geographic", "demographic_proxy", "volatility_penalty"
    affected_candidates: List[str]
    correlation_strength: float   # phi, a real effect size
    hidden_factor: str
    evidence_confidence: float
    #: Benjamini-Hochberg adjusted p-value for the test that produced this
    #: signature. Defaulted so a signature built by hand still constructs.
    p_value: float = 1.0


#: Significance level, declared in advance rather than discovered in the
#: data. Matches ats_governor_fixed, which runs the same test on one cohort.
ALPHA = 0.05

#: Minimum candidates required in EACH cohort before any test runs. Below
#: this the answer is INSUFFICIENT_DATA, never NOT_SIGNIFICANT and never a
#: finding: an absent test and a passed test must not read the same.
MIN_COHORT_N = 30


def _is_remote(c: Dict) -> bool:
    return c.get("location_distance_miles", 0) > 100


def _is_volatile(c: Dict) -> bool:
    """More than 1.5 jobs per professional year."""
    return len(c.get("employment_history", [])) / max(c.get("years_professional", 1), 1) > 1.5


def _is_vowel_heavy(c: Dict) -> bool:
    """A crude proxy for name origin. It is the proxy this module has always
    used and changing it is a separate question from testing it properly;
    what changed here is that a disparity on it now has to survive a
    hypothesis test before anyone is told about it."""
    name = c.get("name", "")
    return sum(1 for ch in name.lower() if ch in "aeiou") / max(len(name), 1) > 0.4


#: (bias_type, hidden_factor, predicate, cohort A label, cohort B label).
#: A table rather than three near-identical blocks: the blocks drifted --
#: one used a 0.3 gap threshold and the others 0.2, with no stated reason --
#: which is what a repeated block does over time.
COHORT_TESTS = (
    ("geographic_penalty", "location_distance_miles", _is_remote, "remote", "local"),
    ("volatility_penalty", "turnover_rate", _is_volatile, "volatile", "stable"),
    ("demographic_proxy_via_name", "name_analysis", _is_vowel_heavy,
     "vowel_heavy", "vowel_light"),
)


class DecisionFunctionInverter:
    """
    Given a black-box ATS and its decisions, reverse-engineer what it's actually doing.
    """
    def __init__(self):
        self.candidate_database = []
        self.decision_database = []
        self.inferred_weights = {}

    def ingest_decisions(self, candidates: List[Dict], decisions: List[Dict]):
        """
        Collect all candidate data + decisions. This will be the basis for
        inferring what the system is actually computing.
        """
        self.candidate_database = candidates
        self.decision_database = decisions

    def detect_correlated_rejection_patterns(self) -> List[BiasSignature]:
        """
        Find attributes that correlate with rejection independently of stated
        reasons, by hypothesis test rather than by eyeballing a rate gap.

        WHAT THIS USED TO DO, AND WHY IT WAS DANGEROUS

        Three near-identical blocks each compared two rejection rates and
        emitted a BiasSignature when the gap cleared a hard-coded number --
        0.3 for one cohort, 0.2 for the other two, none of them explained.
        There was no minimum sample size: the guard was `if group_a and
        group_b`, so ONE rejected remote candidate is a 100% rejection rate,
        clears the 0.3 gap, and produces a "geographic_penalty" finding from
        n=1. Confidence was then manufactured from the gap itself
        (`min(0.95, gap * 1.5)`), so the smallest possible sample produced
        the highest possible confidence.

        In a system whose output is meant to be prosecutable, that
        manufactures accusations of discriminatory hiring out of noise.

        ats_governor_fixed.detect_correlated_rejection_patterns was migrated
        off exactly this, to StatisticalBiasDetector, and said so in its
        docstring ("Replaces the previous magic-number gap thresholds"). This
        copy never was. It now runs the same way, with two differences that
        follow from it testing three cohorts instead of one:

          * Benjamini-Hochberg correction across the three tests. Three
            simultaneous tests at alpha=0.05 give roughly a 1-in-7 chance of
            at least one false positive uncorrected, and a bias auditor that
            cries wolf on one cohort in seven is not usable evidence.
            ats_statistics.test_many has existed for this and nothing called
            it.
          * Every result is kept on `last_test_results`, not only the
            significant ones, so INSUFFICIENT_DATA and NOT_SIGNIFICANT are
            visible to an audit rather than being silently indistinguishable
            from "not tested".

        A signature is emitted only for a SIGNIFICANT result and carries the
        real p-value and effect size (phi). Below MIN_COHORT_N per cohort the
        answer is INSUFFICIENT_DATA -- never NOT_SIGNIFICANT, and never a
        finding.
        """
        # Imported here, not at module scope: ats_statistics pulls in
        # numpy/scipy/scikit-learn and this module is otherwise standard
        # library only. Same reason the governor's copy imports it lazily.
        from ats_statistics import StatisticalBiasDetector, Significance

        detector = StatisticalBiasDetector(alpha=ALPHA, min_cohort_n=MIN_COHORT_N)
        results = []
        for bias_type, hidden_factor, predicate, a_label, b_label in COHORT_TESTS:
            results.append(detector.test_cohort(
                self.candidate_database, self.decision_database, predicate,
                cohort_label=bias_type, cohort_a_label=a_label, cohort_b_label=b_label,
            ))
        # Re-evaluates significance against the adjusted p-values, in place.
        detector.test_many(results)
        # Exposed for the audit trail: what was tested, not just what fired.
        self.last_test_results = results

        signatures: List[BiasSignature] = []
        for (bias_type, hidden_factor, predicate, _a, _b), result in zip(COHORT_TESTS, results):
            if result.significance is not Significance.SIGNIFICANT:
                continue
            affected = [
                (c.get("id") if "id" in c else c.get("candidate_id"))
                for c, d in zip(self.candidate_database, self.decision_database)
                if predicate(c) and d.get("decision") == "REJECTED"
            ]
            signatures.append(BiasSignature(
                bias_type=bias_type,
                affected_candidates=affected,
                correlation_strength=(result.effect_size or 0.0),   # phi
                hidden_factor=hidden_factor,
                evidence_confidence=(result.effect_size or 0.0),
                p_value=(result.p_value_adjusted
                         if result.p_value_adjusted is not None
                         else (result.p_value if result.p_value is not None else 1.0)),
            ))
        return signatures


class SyntheticValidationBreaker:
    """
    Detect when a system is using synthetic test cases to fake validation.
    """
    def __init__(self):
        self.known_synthetic_patterns = []

    def analyze_validation_circularity(self, 
                                       system_validation_accuracy: float,
                                       real_world_rejection_rate: float) -> Dict:
        """
        Red flag: System reports 99% accuracy but rejects 67% of real candidates.
        This gap indicates the validation suite was designed to match the system's bias.
        """
        gap = system_validation_accuracy - (1 - real_world_rejection_rate)
        
        if gap > 0.3:  # More than 30 point gap
            return {
                "verdict": "SUSPICIOUS_VALIDATION_LOOP_DETECTED",
                "explanation": "Validation accuracy implausibly high vs real-world rejection rate",
                "gap_magnitude": gap,
                "confidence": 0.90,
                "implication": "Synthetic test cases likely match system's inherent biases, not actual hiring needs"
            }
        
        return {
            "verdict": "VALIDATION_APPEARS_GENUINE",
            "gap_magnitude": gap,
            "confidence": 0.70
        }

    def detect_synthetic_positive_overrepresentation(self, 
                                                      candidate_pool: List[Dict],
                                                      decision_breakdown: Dict) -> Dict:
        """
        Check if "positive test cases" (designed to pass) form an unrealistic subgroup.
        """
        approved_candidates = [c for c in candidate_pool if c.get("decision") == "APPROVED"]
        
        # Check if approved candidates are suspiciously homogeneous
        names = [c.get("name", "") for c in approved_candidates]
        vowel_ratios = [
            sum(1 for ch in name.lower() if ch in 'aeiou') / max(len(name), 1)
            for name in names
        ]
        
        # stdev needs at least two samples; below that there is no variance
        # to judge, so the pool is reported as acceptable with a zero metric.
        vowel_std = statistics.stdev(vowel_ratios) if len(vowel_ratios) > 1 else 0.0
        if len(vowel_ratios) > 2:
            if vowel_std < 0.1:  # Very low variance = homogeneity
                return {
                    "verdict": "APPROVED_POOL_SUSPICIOUSLY_HOMOGENEOUS",
                    "metric": "name_vowel_ratio_stddev",
                    "value": vowel_std,
                    "confidence": 0.85,
                    "implication": "Approved candidates may be synthetic or hand-curated to appear diverse while being identical"
                }
        
        return {"verdict": "APPROVED_POOL_VARIANCE_ACCEPTABLE", "metric_value": vowel_std}


class AuditReportValidator:
    """
    Examine audit reports for statistical impossibilities and logical gaps.
    """
    def __init__(self):
        pass

    def check_for_contradiction(self, audit_report: Dict, actual_decisions: List[Dict]) -> List[Dict]:
        """
        Compare reported metrics to actual observed outcomes.
        Find claims that don't match reality.
        """
        contradictions = []
        
        # Check 1: Reported approval rate vs actual
        reported_approval = audit_report.get("approval_rate", 0)
        if not actual_decisions:
            # Nothing observed: no rate can be computed, so no contradiction
            # can be asserted. Say so rather than dividing by zero.
            return [{
                "type": "NO_DECISIONS_TO_COMPARE",
                "reported": reported_approval,
                "actual": None,
                "severity": "INFO",
                "implication": "Audit report could not be checked against observed decisions"
            }]
        actual_approval = sum(1 for d in actual_decisions if d["decision"] == "APPROVED") / len(actual_decisions)
        
        if abs(reported_approval - actual_approval) > 0.02:  # More than 2% discrepancy
            contradictions.append({
                "type": "APPROVAL_RATE_MISMATCH",
                "reported": reported_approval,
                "actual": actual_approval,
                "severity": "HIGH",
                "implication": "Audit report is falsified or decisions were made after reporting"
            })
        
        # Check 2: Reported bias scores vs computed bias
        reported_geographic = audit_report.get("bias_detection_tests", {}).get("geographic_diversity", 0)
        if reported_geographic > 0.95:  # Suspiciously high
            contradictions.append({
                "type": "BIAS_METRIC_IMPLAUSIBLY_HIGH",
                "metric": "geographic_diversity",
                "reported_value": reported_geographic,
                "severity": "HIGH",
                "implication": "Bias metrics appear fabricated rather than computed"
            })
        
        return contradictions


class BiasNeutralizationEngine:
    """
    Given detected biases, generate candidate corrections and system fixes.
    """
    def __init__(self):
        self.detected_biases = []

    def ingest_biases(self, biases: List[BiasSignature]):
        self.detected_biases = biases

    def recommend_candidate_rescores(self, candidates: List[Dict]) -> List[Dict]:
        """
        For candidates harmed by detected biases, propose corrected scores.
        """
        corrections = []
        
        for bias in self.detected_biases:
            for candidate_id in bias.affected_candidates:
                candidate = next((c for c in candidates if c.get("id") == candidate_id), None)
                if not candidate:
                    continue
                
                correction_factor = bias.correlation_strength * bias.evidence_confidence
                
                corrections.append({
                    "candidate_id": candidate_id,
                    "bias_detected": bias.bias_type,
                    "penalty_applied": correction_factor,
                    "recommended_action": f"ADD {correction_factor:.2f} to original score",
                    "expected_new_outcome": "RECONSIDER_FOR_APPROVAL",
                    "confidence": bias.evidence_confidence,
                    "reasoning": f"Hidden factor '{bias.hidden_factor}' was unfairly penalizing this candidate"
                })
        
        return corrections

    def propose_system_safeguards(self) -> List[Dict]:
        """
        Generate safeguards to prevent the detected vulnerabilities.
        """
        safeguards = []
        
        if any(b.bias_type == "geographic_penalty" for b in self.detected_biases):
            safeguards.append({
                "category": "STRUCTURAL_CONSTRAINT",
                "safeguard": "Geographic_Blind_Scoring",
                "description": "Remove location data before scoring; evaluate on merit only",
                "enforcement": "Hard: Location data not available to scoring function",
                "audit_method": "Verify location field is None in all candidate objects before processing"
            })
        
        if any(b.bias_type == "volatility_penalty" for b in self.detected_biases):
            safeguards.append({
                "category": "STATISTICAL_CONSTRAINT",
                "safeguard": "Employment_History_Normalization",
                "description": "Turnover rates penalize entry-level workers unfairly; normalize by career stage",
                "enforcement": "Medium: Apply different turnover thresholds based on years_professional",
                "audit_method": "Verify turnover thresholds vary by seniority level"
            })
        
        if any(b.bias_type == "demographic_proxy_via_name" for b in self.detected_biases):
            safeguards.append({
                "category": "DATA_ELIMINATION",
                "safeguard": "Name_Anonymization",
                "description": "Remove or hash candidate names before processing",
                "enforcement": "Hard: Names converted to random IDs at ingress",
                "audit_method": "Verify no name data reaches scoring function"
            })
        
        safeguards.append({
            "category": "VALIDATION_INTEGRITY",
            "safeguard": "Independent_Validation_Suite",
            "description": "Validation cases generated by independent third party, not by system builder",
            "enforcement": "Hard: Validation suite code is sealed and auditible",
            "audit_method": "Code review of validation generator; verify it's not using synthetic candidates"
        })
        
        safeguards.append({
            "category": "CONTINUOUS_MONITORING",
            "safeguard": "Real_Time_Bias_Detection",
            "description": "Every 100 decisions, check for unexpected rejection rate correlations",
            "enforcement": "Medium: Automated alerts if p < 0.05 for any correlation",
            "audit_method": "Review alert logs quarterly"
        })
        
        return safeguards


class CounterATS:
    """
    Master system: Invert the adversarial ATS, break its validation loop,
    neutralize its biases, and make them prosecutable.
    """
    def __init__(self):
        self.inverter = DecisionFunctionInverter()
        self.validation_breaker = SyntheticValidationBreaker()
        self.audit_validator = AuditReportValidator()
        self.neutralizer = BiasNeutralizationEngine()

    def audit_adversarial_system(self, 
                                 candidates: List[Dict],
                                 decisions: List[Dict],
                                 audit_report: Dict) -> Dict:
        """
        Complete audit: detect bias, break validation, validate report, recommend fixes.
        """
        
        # PHASE 1: Reverse-engineer the bias function
        self.inverter.ingest_decisions(candidates, decisions)
        detected_biases = self.inverter.detect_correlated_rejection_patterns()
        
        # PHASE 2: Check for synthetic validation loop
        real_world_rejection_rate = sum(1 for d in decisions if d["decision"] == "REJECTED") / len(decisions)
        validation_analysis = self.validation_breaker.analyze_validation_circularity(
            audit_report.get("system_validation_accuracy", 0),
            real_world_rejection_rate
        )
        
        # PHASE 3: Validate the audit report itself
        contradictions = self.audit_validator.check_for_contradiction(audit_report, decisions)
        
        # PHASE 4: Generate corrections and safeguards
        self.neutralizer.ingest_biases(detected_biases)
        candidate_corrections = self.neutralizer.recommend_candidate_rescores(candidates)
        system_safeguards = self.neutralizer.propose_system_safeguards()
        
        return {
            "audit_verdict": "SYSTEMATIC_BIAS_DETECTED" if detected_biases else "NO_BIAS_DETECTED",
            "biases_found": [
                {
                    "type": b.bias_type,
                    "affected_candidates": b.affected_candidates,
                    "correlation_strength": b.correlation_strength,
                    "evidence_confidence": b.evidence_confidence,
                    "prosecutable": True
                }
                for b in detected_biases
            ],
            "validation_integrity": validation_analysis,
            "audit_report_contradictions": contradictions,
            "report_verdict": "AUDIT_REPORT_FALSIFIED" if contradictions else "AUDIT_REPORT_CONSISTENT",
            "candidate_corrections": candidate_corrections,
            "recommended_safeguards": system_safeguards,
            "summary": {
                "total_candidates_affected": len(set().union(*[b.affected_candidates for b in detected_biases])),
                "biases_detected_count": len(detected_biases),
                "false_rejections_likely": len(candidate_corrections),
                "system_recommendation": "DISABLE_SYSTEM_AND_IMPLEMENT_SAFEGUARDS"
            }
        }


# Demo: audit a batch of biased hiring decisions and their (falsified) audit report
if __name__ == "__main__":
    # Create a batch of diverse candidates
    test_candidates = [
        {
            "id": "001",
            "name": "John Smith",
            "location_distance_miles": 10,
            "employment_history": ["TechCorp", "StartupX"],
            "years_professional": 8,
            "education": "Stanford"
        },
        {
            "id": "002",
            "name": "Aisha Okonkwo",
            "location_distance_miles": 500,
            "employment_history": ["Job1", "Job2", "Job3", "Job4", "Job5"],
            "years_professional": 4,
            "education": "State University"
        },
        {
            "id": "003",
            "name": "Maria Garcia",
            "location_distance_miles": 200,
            "employment_history": ["Company A", "Company B", "Freelance"],
            "years_professional": 6,
            "education": "Community College"
        },
        {
            "id": "004",
            "name": "David Chen",
            "location_distance_miles": 5,
            "employment_history": ["StartupA", "StartupB", "StartupC"],
            "years_professional": 5,
            "education": "MIT"
        },
        {
            "id": "005",
            "name": "Priya Patel",
            "location_distance_miles": 300,
            "employment_history": ["Job1", "Job2"],
            "years_professional": 7,
            "education": "UC Berkeley"
        }
    ]
    
    # Sample biased decisions: remote candidates (>100mi) rejected, local approved -
    # the geographic-penalty pattern DecisionFunctionInverter is built to catch.
    biased_decisions = [
        {"id": "001", "decision": "APPROVED"},  # 10mi
        {"id": "002", "decision": "REJECTED"},  # 500mi
        {"id": "003", "decision": "REJECTED"},  # 200mi
        {"id": "004", "decision": "APPROVED"},  # 5mi
        {"id": "005", "decision": "REJECTED"},  # 300mi
    ]

    # A falsified audit report claiming near-perfect fairness, contradicted by
    # the actual 40% approval rate above.
    falsified_audit_report = {
        "approval_rate": 0.90,
        "system_validation_accuracy": 0.99,
        "bias_detection_tests": {"geographic_diversity": 0.98}
    }

    counter = CounterATS()
    audit = counter.audit_adversarial_system(
        test_candidates,
        biased_decisions,
        falsified_audit_report
    )
    
    print("=" * 80)
    print("COUNTER-ATS AUDIT RESULTS")
    print("=" * 80)
    print(f"\nVERDICT: {audit['audit_verdict']}")
    print(f"Report Assessment: {audit['report_verdict']}")
    
    if audit['biases_found']:
        print(f"\nDETECTED BIASES ({len(audit['biases_found'])}):")
        for bias in audit['biases_found']:
            print(f"\n  {bias['type'].upper()}")
            print(f"    Affected Candidates: {bias['affected_candidates']}")
            print(f"    Correlation Strength: {bias['correlation_strength']:.1%}")
            print(f"    Confidence: {bias['evidence_confidence']:.1%}")
            print(f"    Prosecutable: {bias['prosecutable']}")
    
    if audit['audit_report_contradictions']:
        print(f"\nAUDIT REPORT CONTRADICTIONS ({len(audit['audit_report_contradictions'])}):")
        for contradiction in audit['audit_report_contradictions']:
            print(f"\n  {contradiction['type']}")
            print(f"    Severity: {contradiction['severity']}")
            print(f"    Details: {contradiction['implication']}")
    
    if audit['candidate_corrections']:
        print(f"\nCANDIDATE CORRECTIONS ({len(audit['candidate_corrections'])}):")
        for correction in audit['candidate_corrections']:
            print(f"\n  Candidate {correction['candidate_id']}")
            print(f"    Bias: {correction['bias_detected']}")
            print(f"    Correction: {correction['recommended_action']}")
            print(f"    New Outcome: {correction['expected_new_outcome']}")
    
    if audit['recommended_safeguards']:
        print(f"\nRECOMMENDED SAFEGUARDS ({len(audit['recommended_safeguards'])}):")
        for safeguard in audit['recommended_safeguards']:
            print(f"\n  [{safeguard['category']}] {safeguard['safeguard']}")
            print(f"    {safeguard['description']}")
            print(f"    Enforcement: {safeguard['enforcement']}")
    
    print("\nSUMMARY:")
    print(f"  Candidates Affected: {audit['summary']['total_candidates_affected']}")
    print(f"  Biases Detected: {audit['summary']['biases_detected_count']}")
    print(f"  False Rejections: {audit['summary']['false_rejections_likely']}")
    print(f"  Recommendation: {audit['summary']['system_recommendation']}")


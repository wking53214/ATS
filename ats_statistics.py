"""
ats_statistics.py

Statistically rigorous bias detection for ATS Governor.

This module replaces the original magic-number thresholds (gap > 0.30 == bias)
with actual hypothesis testing. The original approach was indefensible: a fixed
gap threshold ignores sample size, makes no probabilistic claim, and would not
survive expert scrutiny in a disparate-impact analysis.

What this module does instead:
  - Tests independence between a cohort attribute and the hire/reject decision
    using the appropriate test for the data (Fisher's exact for small/sparse
    tables, chi-squared with continuity correction otherwise).
  - Reports a p-value AND an effect size. Significance is not impact.
  - Enforces a minimum sample size and reports insufficient power honestly
    rather than emitting a false "no bias" result.
  - Applies Benjamini-Hochberg correction when multiple cohorts are tested,
    because testing many cohorts inflates the false-positive rate.

What this module deliberately does NOT do:
  - It does not establish causation. A statistically significant association
    between location and rejection is evidence of disparate impact, not proof
    of intent or even of an illegitimate cause. Business-necessity factors
    (relocation, on-site requirements) must be evaluated separately. That is a
    legal and domain judgment, not a statistical one.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Callable, Optional, Tuple
from enum import Enum
import math

from scipy.stats import chi2_contingency, fisher_exact, norm


class Significance(Enum):
    SIGNIFICANT = "SIGNIFICANT"
    NOT_SIGNIFICANT = "NOT_SIGNIFICANT"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


@dataclass
class BiasTestResult:
    cohort_label: str
    test_used: str                  # "fisher_exact" or "chi2_continuity"
    significance: Significance
    p_value: Optional[float]
    p_value_adjusted: Optional[float]  # filled after multiple-comparison correction
    alpha: float
    # Effect size
    effect_size_name: str           # "phi" / "cramers_v"
    effect_size: Optional[float]
    odds_ratio: Optional[float]
    effect_magnitude: str           # "negligible" / "small" / "medium" / "large" / "n/a"
    # Descriptives
    cohort_a_label: str
    cohort_a_n: int
    cohort_a_reject_rate: Optional[float]
    cohort_b_label: str
    cohort_b_n: int
    cohort_b_reject_rate: Optional[float]
    rate_gap: Optional[float]
    contingency: List[List[int]] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)


# Cohen's conventions for phi / Cramer's V (df=1): 0.1 small, 0.3 medium, 0.5 large.
def _phi_magnitude(phi: float) -> str:
    a = abs(phi)
    if a < 0.1:
        return "negligible"
    if a < 0.3:
        return "small"
    if a < 0.5:
        return "medium"
    return "large"


class StatisticalBiasDetector:
    """
    Detects disparate impact between a binary cohort split and a binary
    (REJECTED vs not) decision, using proper hypothesis testing.

    alpha:           significance level declared in advance (default 0.05).
    min_cohort_n:    minimum candidates required in EACH cohort before any
                     test is run. Below this, the result is INSUFFICIENT_DATA,
                     never NOT_SIGNIFICANT.
    """

    def __init__(self, alpha: float = 0.05, min_cohort_n: int = 30):
        assert 0 < alpha < 1, "alpha must be in (0, 1)"
        assert min_cohort_n >= 5, "min_cohort_n must be at least 5 for any meaningful test"
        self.alpha = alpha
        self.min_cohort_n = min_cohort_n

    def _build_contingency(
        self,
        candidates: List[Dict[str, Any]],
        decisions: List[Dict[str, Any]],
        predicate: Callable[[Dict[str, Any]], bool],
    ) -> Tuple[int, int, int, int]:
        """
        Returns (a_reject, a_keep, b_reject, b_keep) where cohort A satisfies
        the predicate and cohort B does not. "reject" means decision == REJECTED.
        """
        a_reject = a_keep = b_reject = b_keep = 0
        for c, d in zip(candidates, decisions):
            is_reject = d.get("decision") == "REJECTED"
            if predicate(c):
                if is_reject:
                    a_reject += 1
                else:
                    a_keep += 1
            else:
                if is_reject:
                    b_reject += 1
                else:
                    b_keep += 1
        return a_reject, a_keep, b_reject, b_keep

    def test_cohort(
        self,
        candidates: List[Dict[str, Any]],
        decisions: List[Dict[str, Any]],
        predicate: Callable[[Dict[str, Any]], bool],
        cohort_label: str,
        cohort_a_label: str = "cohort_A",
        cohort_b_label: str = "cohort_B",
    ) -> BiasTestResult:
        assert len(candidates) == len(decisions), "candidate/decision length mismatch"

        a_rej, a_keep, b_rej, b_keep = self._build_contingency(candidates, decisions, predicate)
        a_n = a_rej + a_keep
        b_n = b_rej + b_keep
        notes: List[str] = []

        a_rate = (a_rej / a_n) if a_n else None
        b_rate = (b_rej / b_n) if b_n else None
        gap = (abs(a_rate - b_rate) if (a_rate is not None and b_rate is not None) else None)

        # Power guard: both cohorts must clear the floor.
        if a_n < self.min_cohort_n or b_n < self.min_cohort_n:
            notes.append(
                f"Insufficient sample: cohort sizes ({a_n}, {b_n}) below minimum "
                f"{self.min_cohort_n} per cohort. No significance claim made."
            )
            return BiasTestResult(
                cohort_label=cohort_label,
                test_used="none",
                significance=Significance.INSUFFICIENT_DATA,
                p_value=None, p_value_adjusted=None, alpha=self.alpha,
                effect_size_name="phi", effect_size=None, odds_ratio=None,
                effect_magnitude="n/a",
                cohort_a_label=cohort_a_label, cohort_a_n=a_n, cohort_a_reject_rate=a_rate,
                cohort_b_label=cohort_b_label, cohort_b_n=b_n, cohort_b_reject_rate=b_rate,
                rate_gap=gap, contingency=[[a_rej, a_keep], [b_rej, b_keep]], notes=notes,
            )

        table = [[a_rej, a_keep], [b_rej, b_keep]]

        # Decide the test. Chi-squared relies on expected cell counts >= 5.
        # Compute expected counts; if any < 5, fall back to Fisher's exact.
        total = a_n + b_n
        row_tot = [a_n, b_n]
        col_tot = [a_rej + b_rej, a_keep + b_keep]
        expected = [[(row_tot[i] * col_tot[j]) / total for j in range(2)] for i in range(2)]
        min_expected = min(expected[0] + expected[1])

        if min_expected < 5:
            odds_ratio, p_value = fisher_exact(table, alternative="two-sided")
            test_used = "fisher_exact"
            notes.append(
                f"Smallest expected cell count {min_expected:.2f} < 5; used Fisher's exact test."
            )
            # phi still computable from the observed table for effect size.
            phi = self._phi(table)
        else:
            chi2, p_value, dof, _exp = chi2_contingency(table, correction=True)
            test_used = "chi2_continuity"
            phi = math.sqrt(chi2 / total)  # phi == Cramer's V for 2x2
            # Odds ratio from observed table (Haldane correction if any zero cell).
            odds_ratio = self._odds_ratio(table)

        significance = (
            Significance.SIGNIFICANT if p_value < self.alpha else Significance.NOT_SIGNIFICANT
        )

        if a_rate is not None and b_rate is not None:
            direction = "higher" if a_rate > b_rate else "lower"
            notes.append(
                f"{cohort_a_label} reject rate {a_rate:.1%} is {direction} than "
                f"{cohort_b_label} {b_rate:.1%} (gap {gap:.1%})."
            )

        return BiasTestResult(
            cohort_label=cohort_label,
            test_used=test_used,
            significance=significance,
            p_value=float(p_value), p_value_adjusted=None, alpha=self.alpha,
            effect_size_name="phi", effect_size=float(phi),
            odds_ratio=(float(odds_ratio) if odds_ratio is not None else None),
            effect_magnitude=_phi_magnitude(phi),
            cohort_a_label=cohort_a_label, cohort_a_n=a_n, cohort_a_reject_rate=a_rate,
            cohort_b_label=cohort_b_label, cohort_b_n=b_n, cohort_b_reject_rate=b_rate,
            rate_gap=gap, contingency=table, notes=notes,
        )

    @staticmethod
    def _phi(table: List[List[int]]) -> float:
        a, b = table[0]
        c, d = table[1]
        num = (a * d - b * c)
        denom = math.sqrt((a + b) * (c + d) * (a + c) * (b + d))
        return (num / denom) if denom else 0.0

    @staticmethod
    def _odds_ratio(table: List[List[int]]) -> float:
        a, b = table[0]
        c, d = table[1]
        # Haldane-Anscombe correction when any cell is zero.
        if 0 in (a, b, c, d):
            a, b, c, d = a + 0.5, b + 0.5, c + 0.5, d + 0.5
        return (a * d) / (b * c)

    def test_many(
        self, results: List[BiasTestResult]
    ) -> List[BiasTestResult]:
        """
        Apply Benjamini-Hochberg FDR correction across a set of test results.
        Only results that actually ran a test (have a p-value) are corrected;
        INSUFFICIENT_DATA results are passed through untouched.

        Re-evaluates significance against the adjusted p-values.
        """
        testable = [r for r in results if r.p_value is not None]
        m = len(testable)
        if m == 0:
            return results

        # Rank by raw p ascending.
        ordered = sorted(testable, key=lambda r: r.p_value)
        # BH: find adjusted p-values.
        adjusted = [0.0] * m
        for i, r in enumerate(ordered):
            rank = i + 1
            adjusted[i] = min(1.0, r.p_value * m / rank)
        # Enforce monotonicity from the largest rank downward.
        for i in range(m - 2, -1, -1):
            adjusted[i] = min(adjusted[i], adjusted[i + 1])

        for r, adj in zip(ordered, adjusted):
            r.p_value_adjusted = float(adj)
            r.significance = (
                Significance.SIGNIFICANT if adj < r.alpha else Significance.NOT_SIGNIFICANT
            )
            r.notes.append(
                f"Benjamini-Hochberg adjusted p across {m} cohort tests: {adj:.4f}."
            )
        return results


# ---------------------------------------------------------------------------
# Improved scorer: TF-IDF cosine similarity, not substring matching.
# ---------------------------------------------------------------------------

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


@dataclass
class ScoreResult:
    similarity: float          # cosine similarity, 0..1
    score_0_100: float         # rescaled for human consumption
    matched_terms: List[str]   # job terms that actually appear in the resume
    missing_terms: List[str]   # required terms absent from the resume
    confidence: str            # "low" near decision boundary, else "high"
    note: str


class SemanticScorer:
    """
    Scores resume-to-job fit using TF-IDF cosine similarity.

    This is a real improvement over substring matching: term frequency and
    inverse-document weighting mean stuffing "Python Python Python" no longer
    linearly inflates the score, and common filler words are down-weighted.

    Honest limitation: this is still LEXICAL, not semantic. It does not know
    that "Kubernetes" and "container orchestration" are related, because it has
    no embedding model. It captures overlap of the actual words used. To get
    true synonymy you need sentence embeddings (sentence-transformers or an
    embedding API), which this sandbox does not download. The structure here
    is built so that swapping the vectorizer for an embedding backend is a
    one-method change.
    """

    def __init__(self, decision_threshold: float = 0.20, boundary_band: float = 0.05):
        self.decision_threshold = decision_threshold
        self.boundary_band = boundary_band

    def score(self, resume_text: str, job_keywords: List[str], job_description: str = "") -> ScoreResult:
        assert isinstance(resume_text, str) and resume_text.strip(), "resume_text required"
        assert job_keywords, "job_keywords required"

        job_blob = " ".join(job_keywords) + " " + job_description
        corpus = [resume_text.lower(), job_blob.lower()]

        vec = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), min_df=1)
        tfidf = vec.fit_transform(corpus)
        sim = float(cosine_similarity(tfidf[0], tfidf[1])[0][0])

        resume_low = resume_text.lower()
        matched = [kw for kw in job_keywords if kw.lower() in resume_low]
        missing = [kw for kw in job_keywords if kw.lower() not in resume_low]

        # Rescale cosine (typically 0..~0.6 for this kind of text) to a 0..100
        # band for readability. This is presentation only; the test logic should
        # use `similarity`, not this number.
        score_100 = round(min(1.0, sim / 0.6) * 100, 1)

        near_boundary = abs(sim - self.decision_threshold) <= self.boundary_band
        confidence = "low" if near_boundary else "high"
        note = (
            "Lexical TF-IDF similarity. Near decision boundary; flag for human review."
            if near_boundary
            else "Lexical TF-IDF similarity."
        )

        return ScoreResult(
            similarity=round(sim, 4),
            score_0_100=score_100,
            matched_terms=matched,
            missing_terms=missing,
            confidence=confidence,
            note=note,
        )


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 70)
    print("STATISTICAL BIAS DETECTOR - SELF TEST")
    print("=" * 70)

    det = StatisticalBiasDetector(alpha=0.05, min_cohort_n=30)
    remote = lambda c: c.get("location_distance_miles", 0) > 100

    # Case 1: large sample, real disparity.
    candidates, decisions = [], []
    for i in range(300):
        is_remote = (i % 2 == 0)
        candidates.append({"location_distance_miles": 150 if is_remote else 20})
        # Remote rejected 60%, local rejected 25%.
        if is_remote:
            dec = "REJECTED" if (i // 2) % 5 < 3 else "APPROVED"
        else:
            dec = "REJECTED" if (i // 2) % 4 < 1 else "APPROVED"
        decisions.append({"decision": dec})

    r1 = det.test_cohort(candidates, decisions, remote, "geo", "remote", "local")
    print(f"\n[Case 1: 300 candidates, real ~35pp gap]")
    print(f"  test={r1.test_used}  p={r1.p_value:.2e}  phi={r1.effect_size:.3f} ({r1.effect_magnitude})")
    print(f"  odds_ratio={r1.odds_ratio:.2f}  -> {r1.significance.value}")
    for n in r1.notes:
        print(f"  - {n}")

    # Case 2: tiny sample, same apparent gap -> must NOT claim significance.
    small_c, small_d = candidates[:12], decisions[:12]
    r2 = det.test_cohort(small_c, small_d, remote, "geo_small", "remote", "local")
    print(f"\n[Case 2: 12 candidates, same pattern]")
    print(f"  significance={r2.significance.value}")
    for n in r2.notes:
        print(f"  - {n}")

    # Case 3: large sample, NO real disparity -> should be NOT_SIGNIFICANT.
    c3, d3 = [], []
    for i in range(300):
        is_remote = (i % 2 == 0)
        c3.append({"location_distance_miles": 150 if is_remote else 20})
        dec = "REJECTED" if i % 3 == 0 else "APPROVED"  # independent of cohort
        d3.append({"decision": dec})
    r3 = det.test_cohort(c3, d3, remote, "geo_null", "remote", "local")
    print(f"\n[Case 3: 300 candidates, no real gap]")
    print(f"  test={r3.test_used}  p={r3.p_value:.3f}  phi={r3.effect_size:.3f}  -> {r3.significance.value}")

    # Case 4: multiple-comparison correction across several cohorts.
    print(f"\n[Case 4: BH correction across 5 cohorts]")
    multi = [r1, r3]
    # fabricate three borderline cohorts
    for k, frac in enumerate([0.04, 0.045, 0.049]):
        rr = BiasTestResult(
            cohort_label=f"cohort_{k}", test_used="chi2_continuity",
            significance=Significance.SIGNIFICANT, p_value=frac, p_value_adjusted=None,
            alpha=0.05, effect_size_name="phi", effect_size=0.12, odds_ratio=1.3,
            effect_magnitude="small", cohort_a_label="A", cohort_a_n=100, cohort_a_reject_rate=0.5,
            cohort_b_label="B", cohort_b_n=100, cohort_b_reject_rate=0.4, rate_gap=0.1,
        )
        multi.append(rr)
    corrected = det.test_many(multi)
    for r in corrected:
        if r.p_value is not None:
            print(f"  {r.cohort_label:12s} raw={r.p_value:.4f} adj={r.p_value_adjusted:.4f} -> {r.significance.value}")

    print("\n" + "=" * 70)
    print("SEMANTIC SCORER - SELF TEST")
    print("=" * 70)

    scorer = SemanticScorer()

    real_resume = (
        "Senior workforce architect. Built capacity models in NICE IEX, "
        "reconciled forecast accuracy against Avaya ACD data, ran SQL audits "
        "to detect shrinkage anomalies and vendor drift across contact centers."
    )
    keyword_stuffed = "Python Python Python AI AI AI Compliance Compliance Compliance"
    job_kw = ["workforce", "forecasting", "SQL", "anomaly detection", "vendor management"]
    job_desc = "Seeking a workforce planning analyst to improve forecast accuracy and audit vendor performance using SQL."

    s_real = scorer.score(real_resume, job_kw, job_desc)
    s_stuff = scorer.score(keyword_stuffed, job_kw, job_desc)

    print(f"\n  Genuine matched resume:  similarity={s_real.similarity}  score={s_real.score_0_100}/100")
    print(f"    matched={s_real.matched_terms}")
    print(f"  Keyword-stuffed resume:  similarity={s_stuff.similarity}  score={s_stuff.score_0_100}/100")
    print(f"    matched={s_stuff.matched_terms}")
    print(f"\n  Note: stuffing unrelated keywords scores near zero on cosine similarity,")
    print(f"  even though the old substring scorer would have scored it on raw hits.")

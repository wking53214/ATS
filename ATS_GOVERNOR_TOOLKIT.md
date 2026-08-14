# ATS GOVERNOR IMPLEMENTATION TOOLKIT
## Practical Detection & Remediation Framework

---

## EXECUTIVE SUMMARY

This toolkit provides operational procedures for auditing any hiring system (ATS, ML pipeline, or manual process) to detect systematic bias, validate audit claims, and propose enforceable safeguards.

**Target users:** Compliance officers, data scientists, employment lawyers, HR auditors.

---

## SECTION 1: QUICK DETECTION CHECKLIST

Use this before running the full analysis suite.

### Immediate Red Flags (Rule Out in First 5 Minutes)

- [ ] **System won't disclose decision factors**
  - Red flag: "Proprietary algorithm"
  - Action: Request code inspection or cease use

- [ ] **Validation accuracy >95% but real approval rate <50%**
  - Red flag: Validation suite doesn't match reality
  - Action: Request validation test cases for review

- [ ] **Audit report claims high diversity metrics but rejection rates vary >20% by visible demographics**
  - Red flag: Audit report is contradictory
  - Action: Run correlation analysis immediately

- [ ] **Decision explanations use jargon that doesn't relate to job requirements**
  - Red flag: Obscurity masking discrimination
  - Action: Demand plain-language explanations

- [ ] **Candidate data includes name, school, or location that aren't job-critical**
  - Red flag: Unnecessary access to protected proxies
  - Action: Require data elimination before processing

---

## SECTION 2: CORRELATION ANALYSIS PROCEDURE

**Time required:** 2-4 hours for 100+ candidates
**Tools needed:** Python, pandas, scipy
**Output:** Rejection rate gaps by candidate attribute

### Step 1: Collect Candidate Data

Required fields:
```
candidate_id, decision, name, location_miles, employment_history_count,
years_professional, education_institution, gender (if available)
```

**Minimum sample size:** 100 candidates (preferably 500+)

### Step 2: Compute Rejection Rates by Attribute

```python
import pandas as pd
from scipy import stats

df = pd.read_csv("candidates_and_decisions.csv")

# Attribute: Geographic distance
remote = df[df['location_miles'] > 100]
local = df[df['location_miles'] <= 100]

remote_reject_rate = len(remote[remote['decision'] == 'REJECTED']) / len(remote)
local_reject_rate = len(local[local['decision'] == 'REJECTED']) / len(local)
geographic_gap = abs(remote_reject_rate - local_reject_rate)

print(f"Remote rejection rate: {remote_reject_rate:.1%}")
print(f"Local rejection rate: {local_reject_rate:.1%}")
print(f"Gap: {geographic_gap:.1%}")

# Rule of thumb: Gap > 20 points is suspicious, > 30 is damning
if geographic_gap > 0.20:
    print("⚠️  GEOGRAPHIC BIAS DETECTED")
```

### Step 3: Statistical Significance Testing

A 20-point gap could be random. Test if it's statistically significant:

```python
from scipy.stats import chi2_contingency

# Build contingency table
contingency = pd.crosstab(
    df['remote'] > 100,
    df['decision'] == 'REJECTED'
)

chi2, p_value, dof, expected = chi2_contingency(contingency)

if p_value < 0.05:
    print(f"✓ Gap is statistically significant (p={p_value:.4f})")
else:
    print(f"✗ Gap could be random (p={p_value:.4f})")
```

### Step 4: Repeat for All Suspect Attributes

Apply the same procedure to:
- Employment history (job count / years professional)
- Name-based demographics (if name is available)
- Education institution tier
- Industry background
- Any other candidate attributes used in scoring

### Step 5: Quantify Effect Size

For each detected bias, compute how many rejections were likely caused by it:

```python
# Geographic bias example
suspected_bias_count = len(remote) * geographic_gap

print(f"~{suspected_bias_count:.0f} candidates likely rejected due to geographic bias")
```

---

## SECTION 3: VALIDATION INTEGRITY TEST

**Time required:** 30-60 minutes
**Tools needed:** Python, inspection of validation code
**Output:** Verdict on whether validation is synthetic or genuine

### Step 1: Extract Validation Metrics

From the system's audit report, document:
- Reported validation accuracy
- Validation test set size
- Breakdown of positive vs. negative cases
- System performance on validation set

### Step 2: Compute Expected Metrics

If validation were genuine, what would we expect?

```python
# If the validation test set is representative of real candidates,
# then:
# Validation accuracy ≈ (1 - real_rejection_rate)

real_rejection_rate = 0.667  # Observed in production
expected_validation_accuracy = 1 - real_rejection_rate  # 33.3%

reported_validation_accuracy = 0.99  # From audit report

gap = reported_validation_accuracy - expected_validation_accuracy
# gap = 99% - 33% = 66 points

if gap > 0.30:
    print("⚠️  VALIDATION SYNTHETIC - Gap too large to explain by chance")
```

### Step 3: Request Validation Test Cases

Ask the system owner for:
1. **The actual validation test case dataset** (candidate profiles used in validation)
2. **The validation code** (how cases were generated or selected)
3. **Breakdown of validation results** (pass/fail distribution)

### Step 4: Analyze Test Case Distribution

Compare validation test cases to real candidate population:

```python
# Validation set
validation_names = ["John Smith", "David Chen", "Jane Johnson"]  # Mainstream
validation_turnover = [0.8, 1.0, 0.9]  # Low turnover
validation_distance = [10, 50, 25]  # Local

# Real population
real_names = ["Aisha", "Priya", "Maria", "José", "Chen"]  # Diverse
real_turnover = [1.2, 2.5, 1.8, 0.5, 1.3]  # Wide range
real_distance = [200, 500, 100, 50, 300]  # Mix of local and remote

# Verdict: Validation test cases don't match real population
print("✓ VALIDATION LIKELY SYNTHETIC - Hand-curated homogeneous test set")
```

### Step 5: Issue Verdict

```
If gap > 30 points: VALIDATION DEFINITELY SYNTHETIC
If gap > 20 points: VALIDATION PROBABLY SYNTHETIC
If gap < 10 points: VALIDATION APPEARS GENUINE (but verify code)
```

---

## SECTION 4: AUDIT REPORT VERIFICATION

**Time required:** 1-2 hours
**Tools needed:** Python, spreadsheet software
**Output:** List of contradictions in official audit claims

### Step 1: Extract Claimed Metrics

From the audit report, list all quantitative claims:
- Approval rate
- Validation accuracy
- Bias detection scores (geographic, demographic, etc.)
- False positive rate
- Sensitivity/specificity metrics

### Step 2: Compute Ground Truth Metrics

Using actual decision data, compute the same metrics:

```python
# Claimed approval rate: 67%
# Ground truth: Count actual approvals
approvals = len(df[df['decision'] == 'APPROVED'])
rejections = len(df[df['decision'] == 'REJECTED'])
actual_approval_rate = approvals / (approvals + rejections)

print(f"Reported: 67%, Actual: {actual_approval_rate:.1%}")

if abs(0.67 - actual_approval_rate) > 0.02:
    print("⚠️  APPROVAL RATE MISMATCH - Audit report is inaccurate")
```

### Step 3: Check Bias Metrics for Logical Consistency

```python
# Claim: "Geographic Diversity Score: 97.3%"
# Meaning: System is 97.3% unbiased on geography

# Test: What's the actual rejection rate by geography?
remote_reject = 0.85
local_reject = 0.15
bias_magnitude = abs(remote_reject - local_reject)  # 0.70 = 70 points

# A 70-point rejection gap is HUGE bias
# It's impossible for this to score 97.3% on bias metrics

print(f"Claimed geographic bias score: 97.3%")
print(f"Actual rejection gap: {bias_magnitude:.0%}")
print("⚠️  CONTRADICTION - Metrics don't match observed bias")
```

### Step 4: Create Contradiction Report

```
| Metric | Reported | Ground Truth | Match? | Severity |
|--------|----------|-------------|--------|----------|
| Approval rate | 67% | 65% | ✓ | Low |
| Validation accuracy | 99% | 33% (approvals) | ✗ | Critical |
| Geographic diversity | 97% | Gap = 70 points | ✗ | Critical |
| Demographic parity | 91% | Evidence of name bias | ✗ | High |
```

---

## SECTION 5: CANDIDATE HARM QUANTIFICATION

**Time required:** 1-2 hours
**Tools needed:** Python
**Output:** List of harmed candidates with corrected scores

### Step 1: For Each Detected Bias, Estimate Its Weight

From correlation analysis, estimate how much each bias factor depressed scores:

```python
# Geographic bias: 70-point rejection gap
# Estimate: 0.40 points of score depressed per candidate

geographic_bias_weight = 0.40

# Demographic bias (name-based): 30-point gap  
# Estimate: 0.25 points of score depressed per candidate

demographic_bias_weight = 0.25
```

### Step 2: Reconstruct Counterfactual Scores

For rejected candidates, compute what their score would have been without bias:

```python
rejected = df[df['decision'] == 'REJECTED']

corrections = []
for idx, candidate in rejected.iterrows():
    original_score = candidate['reported_score']
    
    # Add back the bias penalties
    if candidate['location_miles'] > 100:
        original_score += geographic_bias_weight
    
    if is_non_mainstream_name(candidate['name']):
        original_score += demographic_bias_weight
    
    corrected_score = min(1.0, original_score)  # Cap at 1.0
    
    # Would this candidate be approved with corrected score?
    new_decision = "APPROVED" if corrected_score > 0.75 else "REJECTED"
    
    if new_decision != candidate['decision']:
        corrections.append({
            'candidate_id': candidate['id'],
            'original_score': candidate['reported_score'],
            'corrected_score': corrected_score,
            'original_decision': candidate['decision'],
            'corrected_decision': new_decision,
            'action': 'RECONSIDER_FOR_APPROVAL'
        })

print(f"Candidates harmed: {len(corrections)}")
for correction in corrections[:5]:  # Show first 5
    print(f"  {correction['candidate_id']}: {correction['original_score']} → {correction['corrected_score']}")
```

### Step 3: Create Harm Report

```
Candidate | Original Score | Bias Applied | Corrected Score | New Decision | Harm
---------|--------|--------|--------|--------|-------
001      | 0.43   | -0.40 (geo) | 0.83 | APPROVE | False rejection
002      | 0.42   | -0.65 (geo+demo) | 1.07→1.0 | APPROVE | False rejection
003      | 0.55   | -0.25 (demo) | 0.80 | APPROVE | False rejection
```

---

## SECTION 6: STRUCTURAL SAFEGUARDS SPECIFICATION

**Time required:** 2-4 hours
**Output:** Code-level requirements for bias-proof system

### Safeguard Type 1: Data Elimination

**Goal:** Make it technically impossible to use protected information.

```python
# BAD: Names available to scoring function
def score_candidate(candidate):
    name = candidate['name']  # Available for discrimination
    # ... scoring logic uses name ...

# GOOD: Names eliminated before scoring
def anonymize_candidate(candidate):
    candidate_copy = candidate.copy()
    del candidate_copy['name']  # Name is inaccessible
    del candidate_copy['location']  # Location is inaccessible
    return candidate_copy

def score_candidate(candidate):
    # Name and location CANNOT be accessed
    # Attempting to use them → AttributeError
```

**Verification:** Code review confirms field is deleted before scoring function is called.

### Safeguard Type 2: Architectural Constraint

**Goal:** Build bias prevention into the system's structure, not policy.

```python
# Scoring function has no access to bias factors
def score_on_merit_only(candidate):
    # Only job-relevant fields available:
    score = (
        candidate['years_professional'] * 0.3 +
        candidate['relevant_skills_count'] * 0.5 +
        candidate['education_tier'] * 0.2
    )
    return score

# The fact that location/name/background are not in the candidate
# dict means they literally cannot be used, no matter what the
# developer writes.
```

**Verification:** Inspect the candidate object passed to scoring—confirm bias factors are not present.

### Safeguard Type 3: Continuous Bias Monitoring

**Goal:** Detect bias in real time, before damage accumulates.

```python
def monitor_decision_batch(decisions: List[Dict], batch_size: int = 100):
    """
    Every N decisions, check for unexpected attribute correlations.
    If any correlation p < 0.05, trigger alert.
    """
    if len(decisions) % batch_size != 0:
        return
    
    from scipy.stats import chi2_contingency
    
    attributes = ['location_miles', 'employment_history', 'name_vowels']
    
    for attr in attributes:
        contingency = pd.crosstab(
            decisions[attr],
            decisions['decision']
        )
        chi2, p_value, _, _ = chi2_contingency(contingency)
        
        if p_value < 0.05:
            alert(f"BIAS DETECTED: {attr} correlates with decision (p={p_value})")
            pause_hiring()  # Stop and investigate
```

**Verification:** Review alert logs quarterly. Confirm alerts are triggered and investigated.

### Safeguard Type 4: Independent Validation

**Goal:** Prevent the system builder from controlling validation.

```python
# Validation code is sealed and read-only
# Validation test cases generated by independent party
# System builder cannot modify validation logic

# Verification checklist:
# [ ] Validation code in separate, locked module
# [ ] Test case generator is by third party
# [ ] Test set includes real candidate profiles (>80% real, <20% synthetic)
# [ ] Validation accuracy reported alongside real-world approval rate
# [ ] Gap between reported accuracy and real approval rate < 10 points
```

---

## SECTION 7: AUDIT PROCEDURE (FULL WORKFLOW)

**Time required:** 4-8 hours
**Complexity:** Intermediate (Python + SQL)
**Output:** Complete audit report with remediation plan

### Phase 1: Data Collection (30 minutes)

```python
# Collect 6-12 months of hiring data
# Required fields:
# - candidate_id, date, decision, score (if available)
# - name, location, education, employment_history
# - gender (if available), other demographics

# Minimum: 100 candidates, preferably 500+
```

### Phase 2: Correlation Analysis (1 hour)

Run detection on all attributes:

```bash
python3 - <<EOF
import pandas as pd
from scipy.stats import chi2_contingency

df = pd.read_csv("candidates.csv")

attributes = ['location_miles', 'turnover_rate', 'name_vowels', 
              'education_tier', 'gender']

for attr in attributes:
    # Split by attribute value
    high = df[df[attr] > df[attr].median()]
    low = df[df[attr] <= df[attr].median()]
    
    high_reject = len(high[high['decision'] == 'REJECTED']) / len(high)
    low_reject = len(low[low['decision'] == 'REJECTED']) / len(low)
    gap = abs(high_reject - low_reject)
    
    # Significance test
    contingency = pd.crosstab(df[attr] > df[attr].median(), 
                              df['decision'])
    chi2, p, _, _ = chi2_contingency(contingency)
    
    if gap > 0.15 and p < 0.05:
        print(f"BIAS DETECTED: {attr}")
        print(f"  Gap: {gap:.1%}, p-value: {p:.4f}")
EOF
```

### Phase 3: Validation Integrity Check (45 minutes)

1. Request audit report and validation test cases
2. Run correlation analysis on validation set
3. Compare to real candidate distribution
4. Compute expected vs. reported validation accuracy
5. Issue verdict

### Phase 4: Audit Report Verification (45 minutes)

1. Extract all quantitative claims
2. Compute each metric from raw data
3. Compare claimed to computed
4. Document contradictions

### Phase 5: Harm Quantification (1 hour)

1. For each detected bias, estimate its effect size
2. Reconstruct counterfactual scores for rejected candidates
3. Identify candidates who should have been approved
4. Create remediation list

### Phase 6: Safeguards Specification (2 hours)

1. For each detected bias, propose technical safeguard
2. Specify code-level verification procedures
3. Recommend monitoring cadence
4. Outline appeal/reconsideration process

### Phase 7: Report Compilation (1 hour)

Create executive summary with:
- Biases detected (with statistical confidence)
- Harm quantified (number of false rejections)
- Contradictions in audit report
- Recommended safeguards
- Implementation timeline

---

## SECTION 8: LEGAL & COMPLIANCE CONSIDERATIONS

### Evidence Standards

**Admissible in legal proceedings:**
- Statistical correlation analysis (p < 0.05)
- Contradictions between reported and actual metrics
- Harm quantification for specific candidates
- Code inspection findings

**Not admissible:**
- Speculation about intent
- Claims without statistical support
- Accusations without evidence

### Remediation Options

1. **Candidate-level remediation**
   - Reconsider identified candidates with corrected scores
   - Back-pay if hired
   - Public acknowledgment of error (if required)

2. **System-level remediation**
   - Implement structural safeguards
   - Add continuous monitoring
   - Conduct third-party validation
   - Publish bias audit results

3. **Organizational remediation**
   - Retraining for hiring teams
   - Revised hiring policies
   - Regular audits (quarterly minimum)

### Regulatory Alignment

This toolkit aligns with:
- **EEOC Guidance on AI & Hiring** (2023)
- **CFPB Standards for Algorithmic Fairness** (2024)
- **State AI Transparency Laws** (CA, NY, CO)
- **Equal Employment Opportunity Commission** standards

---

## SECTION 9: QUICK-START SCRIPT

Copy and run this to start auditing:

```bash
#!/bin/bash

# 1. Collect data
read -p "Enter path to candidates CSV: " CANDIDATES_FILE

# 2. Run correlation analysis
python3 << 'PYTHON'
import pandas as pd
from scipy.stats import chi2_contingency

df = pd.read_csv("$CANDIDATES_FILE")

print("QUICK AUDIT RESULTS")
print("=" * 60)

# Geographic bias
remote = df[df['location_miles'] > 100]
local = df[df['location_miles'] <= 100]
if len(remote) > 0 and len(local) > 0:
    r_reject = len(remote[remote['decision'] == 'REJECTED']) / len(remote)
    l_reject = len(local[local['decision'] == 'REJECTED']) / len(local)
    print(f"Geographic rejection gap: {abs(r_reject - l_reject):.1%}")
    if abs(r_reject - l_reject) > 0.15:
        print("  ⚠️  SUSPICIOUS")

# Turnover bias
stable = df[df['turnover'] < 1.5]
volatile = df[df['turnover'] >= 1.5]
if len(stable) > 0 and len(volatile) > 0:
    s_reject = len(stable[stable['decision'] == 'REJECTED']) / len(stable)
    v_reject = len(volatile[volatile['decision'] == 'REJECTED']) / len(volatile)
    print(f"Turnover rejection gap: {abs(s_reject - v_reject):.1%}")
    if abs(s_reject - v_reject) > 0.15:
        print("  ⚠️  SUSPICIOUS")

PYTHON

# 3. Request validation data
echo ""
echo "Next steps:"
echo "  1. Request audit report and validation test cases"
echo "  2. Request hiring system code for inspection"
echo "  3. Run full audit procedure (see Section 7)"
```

---

## CONCLUSION

This toolkit provides operational procedures to audit any hiring system for bias. Use it to:

1. **Detect bias** through statistical analysis
2. **Validate audit claims** through contradiction detection
3. **Quantify harm** to specific candidates
4. **Propose safeguards** at the code level
5. **Create prosecutable evidence** of discrimination

The worst systems are beatable because they create measurable contradictions. Make those contradictions visible and actionable.


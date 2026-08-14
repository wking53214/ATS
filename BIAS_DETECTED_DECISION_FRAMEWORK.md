# ATS GOVERNOR DECISION FRAMEWORK
## What To Do When Bias Is Detected

---

## QUICK REFERENCE

When Governor's audit detects bias, follow this decision tree:

```
BIAS DETECTED
  │
  ├─ CRITICAL (gap > 30%, audit fraud found)?
  │  └─ → IMMEDIATE ACTION: Pause all hiring
  │  └─ → Run full audit
  │  └─ → Alert board of directors
  │  └─ → Engage legal counsel
  │  └─ → Begin remediation
  │
  ├─ SIGNIFICANT (gap 20-30%, some contradictions)?
  │  └─ → PAUSE NEW HIRING
  │  └─ → Investigate within 48 hours
  │  └─ → Implement safeguards
  │  └─ → Resume with monitoring
  │
  ├─ SUSPICIOUS (gap 15-20%, contradictions minor)?
  │  └─ → CONTINUE with enhanced monitoring
  │  └─ → Investigate within 1 week
  │  └─ → Plan safeguard implementation
  │  └─ → Weekly audits instead of daily
  │
  └─ NONE (gap < 15%, audit consistent)?
     └─ → Continue normal operations
     └─ → Standard audit schedule
```

---

## LEVEL 1: SUSPICIOUS BIAS (Gap 15-20%)

**Indicators:**
- Rejection rate gap between groups: 15-20%
- Minor contradictions in audit report (0-1)
- No statistical fraud evidence
- Affects 5-15 candidates

**Decision: INVESTIGATE & PLAN**

### Immediate Actions (Today)
- [ ] Flag in daily monitoring report
- [ ] Notify hiring team lead
- [ ] Document the gap (create audit ticket)
- [ ] Schedule investigation meeting

### Week 1
- [ ] Verify gap is statistically real (p < 0.10)
- [ ] Interview hiring managers about criteria
- [ ] Check if gap aligns with job requirements
- [ ] Draft preliminary remediation plan

### Week 2
- [ ] Implement light safeguards
  - Add mandatory documentation of decision rationale
  - Require second review for borderline candidates
  - Flag candidates from underrepresented groups for explicit consideration
- [ ] Increase monitoring frequency (daily instead of weekly)
- [ ] Plan structural safeguards (geographic blind scoring, etc.)

### Decision Point (End of Week 2)
- **If gap explained by job requirements** → Continue with enhanced monitoring
- **If gap unexplained or growing** → Move to SIGNIFICANT level
- **If safeguards already improving bias** → Continue current path

---

## LEVEL 2: SIGNIFICANT BIAS (Gap 20-30%)

**Indicators:**
- Rejection rate gap between groups: 20-30%
- Multiple audit contradictions (2+)
- Some evidence of systemic bias
- Affects 15-40 candidates

**Decision: PAUSE & REMEDIATE**

### Hour 0 (When Detected)
- [ ] **PAUSE ALL NEW HIRING IMMEDIATELY**
- [ ] Create critical ticket
- [ ] Alert compliance officer
- [ ] Send notification: "Hiring paused pending bias investigation"

### Hours 0-4
- [ ] Run full Governor audit
- [ ] Engage legal counsel (outside counsel recommended)
- [ ] Notify HR leadership
- [ ] Determine root cause (code review if ATS/AI-based)

### Day 1
- [ ] If code-based bias found: Disable the biased factor immediately
- [ ] If human-based bias: Retrain hiring managers, change evaluation criteria
- [ ] Begin candidate remediation process:
  - [ ] Identify all harmed candidates (from Governor's correction list)
  - [ ] Review their applications with corrected scoring
  - [ ] Make corrected hiring decisions
  - [ ] Document the process for EEOC if needed

### Days 2-5
- [ ] Implement structural safeguards
  - [ ] Geographic blind scoring (remove location before evaluation)
  - [ ] Name anonymization (hash names at ingress)
  - [ ] Skill-based only evaluation (remove proxy factors)
- [ ] Code review for biased logic
- [ ] New validation suite with diverse test cases
- [ ] Continuous monitoring setup

### Day 7
- [ ] Testing: Run corrected system on test data
- [ ] Verify safeguards actually work
- [ ] Final audit before resuming

### Decision Point (Day 7)
- **If safeguards successful** → Resume hiring with Governor oversight
- **If safeguards insufficient** → Escalate to Level 3
- **If external system vendor** → Begin vendor remediation or replacement process

---

## LEVEL 3: CRITICAL BIAS (Gap > 30%)

**Indicators:**
- Rejection rate gap between groups: > 30%
- Falsified audit report (gap to reality > 30 points)
- Clear evidence of intentional discrimination
- Affects 40+ candidates
- Multiple bias types detected

**Decision: NUCLEAR OPTION**

### Hour 0 (When Detected)
- [ ] **PAUSE ALL HIRING IMMEDIATELY**
- [ ] Lock candidate database (no further decisions)
- [ ] Notify CEO, General Counsel, Board Chair
- [ ] Contact outside employment law firm
- [ ] Begin document preservation (no deletions)

### Hours 0-8
- [ ] Full Governor audit with legal packaging
- [ ] Prepare for EEOC complaint (assume it will happen)
- [ ] Identify all affected candidates (full remediation list)
- [ ] Calculate damages estimate
- [ ] Determine root cause (rogue system, negligence, intentional?)

### Day 1
- [ ] Emergency board meeting
- [ ] Legal strategy session:
  - [ ] Proactive disclosure to EEOC (sometimes better than complaint)
  - [ ] Voluntary remediation plan
  - [ ] Candidate compensation framework
- [ ] Disable system entirely (not just the biased factor)
- [ ] Begin hiring under manual process with oversight

### Days 2-7
- [ ] Candidate outreach:
  - [ ] Contact all harmed candidates
  - [ ] Offer reconsideration with corrected scoring
  - [ ] Offer back-wages + damages if rejected
  - [ ] Document consent for EEOC process
- [ ] System replacement:
  - [ ] Either rebuild with proper safeguards OR
  - [ ] Replace with vendor system that passes Governor audit
- [ ] Root cause investigation:
  - [ ] If vendor system: Demand fixes, consider replacement
  - [ ] If internal system: Who designed it? Why no safeguards? Intent vs negligence?
  - [ ] If human bias: What training was/wasn't provided?

### Week 2
- [ ] Internal investigation complete
- [ ] Remediation plan finalized
- [ ] Legal review of all communications
- [ ] Prepare public statement (if needed)

### Week 4
- [ ] New hiring system operational
- [ ] Passes Governor audit on test data
- [ ] All harmed candidates remediated
- [ ] Settlement agreements signed (if litigation agreed)

### Long-term
- [ ] Quarterly Governor audits
- [ ] Annual external audit by independent firm
- [ ] Board-level governance of hiring system changes
- [ ] Policy changes to prevent recurrence

---

## SPECIAL CASE: AUDIT REPORT FALSIFICATION

If Governor detects contradictions between claimed and actual metrics:

**This indicates fraud.**

### Immediate Response
- [ ] Secure all audit reports
- [ ] Preserve all decision data (chain of custody)
- [ ] Notify legal immediately
- [ ] **Do not share results internally without legal review**

### Legal Implications
Falsifying audit reports:
- Violates EEOC record-keeping requirements (federal crime)
- Evidence of discriminatory intent (allows punitive damages)
- Potential title for SEC disclosure (material risk)
- May constitute fraud (criminal liability for executives)

### Process
1. **Pause hiring** (minimum 48 hours, usually longer)
2. **External audit** (hire independent firm to verify)
3. **Legal investigation** (preserve all communications)
4. **Board notification** (fraud is a governance issue)
5. **Potential disclosure** (SEC, EEOC, state regulators)

---

## CANDIDATE REMEDIATION FRAMEWORK

When Governor identifies harmed candidates, use this process:

### Step 1: Identify Harmed Candidates
Governor provides:
- Candidate ID
- Original decision (REJECTED)
- Bias detected (geographic, demographic, volatility)
- Correction factor (how much score was unfairly penalized)
- Corrected decision (SHOULD HAVE BEEN APPROVED)

### Step 2: Re-evaluate with Corrected Score
For each harmed candidate:
1. Pull original application
2. Apply corrected score (remove bias penalty)
3. Make new decision based on corrected score
4. If corrected decision is APPROVED:
   - Offer position (if still available)
   - Offer back-wages (from original decision date to current)
   - Offer emotional distress damages if candidate declines position

### Step 3: Document for Legal
For each candidate:
- Original decision: REJECTED (score X)
- Bias detected: [type] (penalty -Y)
- Corrected score: X+Y = Z
- Corrected decision: APPROVED
- Offer: Position + back-wages OR settlement
- Acceptance: [Y/N]

### Step 4: Communicate
**Email template:**

```
Subject: Hiring Decision Review - [Candidate Name]

Dear [Name],

We have completed a comprehensive audit of our hiring practices and 
identified systematic bias in our evaluation process. Our analysis 
indicates that your application was impacted by this bias.

Original Decision: [DATE] - REJECTED
Reason: [YOUR ORIGINAL REASON]

Upon correcting for the identified bias, your qualifications clearly 
meet our standards.

We would like to:
[ ] Offer you the [POSITION] role at [SALARY]
    - Start date: [DATE]
    - Back-wages from [ORIGINAL DATE]: $[AMOUNT]
    - Signing bonus (for inconvenience): $[AMOUNT]

[ ] If the position is no longer available, offer settlement:
    - Back-wages: $[AMOUNT]
    - Emotional distress damages: $[AMOUNT]
    - Total: $[AMOUNT]

We apologize for this error and are committed to preventing it 
from happening again. We've implemented safeguards to ensure fair 
evaluation of all candidates.

Please respond within 10 business days.

Sincerely,
[HIRING MANAGER]
```

---

## DAMAGE CALCULATION FRAMEWORK

For settlements or litigation, calculate damages:

### Lost Wages (Primary Damage)
```
Days from rejection to offer: D
Annual salary (what they would have earned): S
Daily wage: S / 250 working days
Lost wages: D * (S / 250)

Example:
- Rejected: January 1
- Audit completed: July 1 (6 months = 130 working days)
- Annual salary: $100,000
- Daily wage: $400
- Lost wages: 130 * $400 = $52,000
```

### Emotional Distress Damages
```
Multiplier based on:
- Visibility of discrimination (obvious or hidden?)
- Duration of discrimination (how many rejected candidates?)
- Harm to reputation (did they tell others they were rejected?)

Guidelines:
- Suspected/minor bias: 0.5-1.0x back-wages
- Clear bias: 1.0-2.0x back-wages
- Obvious/intentional discrimination: 2.0-5.0x back-wages

Example (for clear bias scenario):
- Back-wages: $52,000
- Emotional distress multiplier: 1.5x
- Emotional distress: $78,000
- Total: $130,000
```

### Punitive Damages (If Fraud/Intent Proven)
```
Applicable when:
- Audit report was falsified (fraud)
- Discrimination was intentional
- Company knowingly discriminated

Amount: Typically 1-3x back-wages + emotional distress

Example (if fraud proven):
- Back-wages + emotional distress: $130,000
- Punitive damages (2x): $260,000
- Total: $390,000
```

---

## ESCALATION MATRIX

| Scenario | Level | Action | Timeline |
|----------|-------|--------|----------|
| Gap 15-20%, minor issues | SUSPICIOUS | Investigate, plan safeguards | 1-2 weeks |
| Gap 20-30%, multiple issues | SIGNIFICANT | Pause hiring, remediate | 3-7 days |
| Gap 30%+, audit fraud | CRITICAL | Pause all hiring, legal counsel | Immediate |
| Multiple biases detected | CRITICAL | All of above + board notice | Immediate |
| Falsified audit report | CRITICAL | Lock data, engage legal | Immediate |

---

## WHAT NOT TO DO

**When Governor detects bias, DO NOT:**

- [ ] **Ignore the alert.** It's statistical. Ignoring it is continuing discrimination.
- [ ] **Delete audit logs.** That's destroying evidence (federal crime).
- [ ] **Modify the audit report.** Same as above.
- [ ] **Threaten the compliance team.** Whistleblower retaliation is federal crime.
- [ ] **Blame candidates.** "They just weren't good fits." Governor measured objectively.
- [ ] **Claim unfair to bias the other way.** Eliminating bias isn't unfair; perpetuating it is.
- [ ] **Continue hiring while investigating.** Each decision could be another false rejection.
- [ ] **Negotiate with candidates under table.** Make the process transparent and documented.

---

## EXAMPLE: CRITICAL BIAS INCIDENT

**Day 1, 9 AM: Governor detects 100% geographic bias**

```
ALERT: Geographic bias detected
Gap: 100% (remote candidates: 100% rejected, local: 0% rejected)
Affected: Candidates 002, 003, 005
Audit fraud: Reported approval rate 90%, actual 40%
Recommendation: IMMEDIATE_PAUSE_AND_INVESTIGATE
```

**9:15 AM: Compliance officer receives alert**
- Pulls the Governor report
- Sees 100% gap, audit fraud, 3 affected candidates
- Escalates to CEO

**10 AM: Emergency call**
- CEO, General Counsel, CHRO, Compliance Officer
- Decision: Full audit, pause hiring
- Assign: External legal firm, IT forensics on ATS

**2 PM: Full audit results**
- Geographic bias: 100% confirmed (p < 0.001)
- Name-based bias: 66.7% (Candidates 002, 003 both harmed)
- Audit report: Completely falsified
- Verdict: Prosecutable fraud + disparate impact

**4 PM: Candidate remediation outreach**
- Candidate 002: Offered position + $80K back-wages
  - Accepts position
- Candidate 003: Position filled, offered $100K settlement
  - Accepts settlement
- Candidate 005: Offered position + $75K back-wages
  - Negotiating

**Day 2: System remediation**
- ATS disabled
- Location data removed from candidate records
- Manual hiring process with oversight activated

**Day 7: New system deployed**
- Governor-verified ATS (geographic blind scoring)
- Passes audit on test data
- Resume hiring

**Month 1: Settlements finalized**
- Candidates receive compensation
- Candidates hired offer accepted
- Investigation complete

**Ongoing: Safeguards & governance**
- Daily Governor audits
- Monthly board reporting
- Quarterly external audits

---

## CONCLUSION

When Governor finds bias, **act decisively.** The longer you wait:
- More false rejections occur
- More damages accumulate
- Legal exposure increases
- EEOC presumption of intentionality grows

**The best outcome?** Pause hiring, investigate thoroughly, fix systematically, remediate candidates, implement safeguards, and resume with confidence.

**The worst outcome?** Ignore the alert, continue discriminating, face EEOC lawsuit with Governor evidence, pay 3-5x damages, and lose public trust.

Choose the first path.


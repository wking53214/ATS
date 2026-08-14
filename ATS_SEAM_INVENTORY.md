# ATS Seam Inventory (v1)

Scope: files and named interfaces at the ATS root only. [OBSERVED]

Method: static inspection of readable source, text, configuration examples, documentation, and file metadata. The two PDF files were identified but their text was not readable in the available environment. [OBSERVED]

## Phase 1: Component enumeration

C1 — ats_governor_production.py; executable module containing ATSGovernorProduction, StreamingBiasMonitor, SafeguardVerifier, LegalEvidencePackager, DecisionFunctionInverter, AuditReportValidator, and BiasNeutralizationEngine. [OBSERVED]

C2 — counter_system.py; executable module containing CounterATS, DecisionFunctionInverter, SyntheticValidationBreaker, AuditReportValidator, and BiasNeutralizationEngine. [OBSERVED]

C3 — ats_kernel_bridge.py; executable bridge module containing CandidateSignals, ATSKernelAdapter, forensic policy factories, manifest construction, ATSGovernorKernel, and a module entry point. [OBSERVED]

C4 — ATS_from_Perplexity.txt; text artifact containing Python source for SynapsisGSA and its component classes. [OBSERVED]

C5 — ats_kernel_bridge-2a17c60df701cc62.txt; text artifact with the same SHA-256 digest as C3. [OBSERVED]

C6 — ats_kernel_bridge-2a17c60df701cc62.md; Markdown artifact containing a formatted bridge variant; its digest differs from C3. [OBSERVED]

C7 — README.md; project documentation containing component names, deployment flow, requirements, and operational references. [OBSERVED]

C8 — ATS_GOVERNOR_COMPLETE_PACKAGE.md; package documentation containing quick-start, deployment, checklist, and legal-disclaimer sections. [OBSERVED]

C9 — ATS_GOVERNOR_INTEGRATION.md; integration documentation containing pipeline, alerting, audit, archive, and deployment references. [OBSERVED]

C10 — ATS_GOVERNOR_TOOLKIT.md; operational toolkit documentation containing candidate fields, statistical checks, validation checks, and workflow descriptions. [OBSERVED]

C11 — ATS_RED_TEAM_ANALYSIS.md; analysis documentation containing attack-vector, inversion, validation, audit, harm, and test descriptions. [OBSERVED]

C12 — BIAS_DETECTED_DECISION_FRAMEWORK.md; decision-framework documentation containing bias-level routing and remediation descriptions. [OBSERVED]

C13 — ats_threat_model.md; threat-model documentation containing attack patterns, methodology, and documented record schemas. [OBSERVED]

C14 — ATSA (Application Tracking System Auditor) - Google Gemini.pdf; PDF artifact, identified as an eight-page PDF file. [OBSERVED]

C15 — ATS_HiddenBias_CounterATS_Determ_v01 - Google Gemini.pdf; PDF artifact, identified as an eight-page PDF file. [OBSERVED]

C16 — documented hiring-pipeline input interface; the documentation names candidate data, hiring decisions, audit reports, and a pipeline/scoring/decision flow, but no local service implementation was found. [DOCUMENTED]

C17 — gov4_kernel dependency interface; C3 imports EventStore, ExecutionRuntime, GovernanceAuditor, GovernanceChassis, GovernanceCoreReducer, Manifest, NormalizedEvent, Policy, PolicyVM, Provenance, Regime, TrafficPayload, Verdict, WAL, canonical, and critical_requires_escalation from this module. The module was not present in ATS. [OBSERVED]

C18 — worst_system dependency interface; C2's module entry point imports WorstATS from this module. The module was not present in ATS. [OBSERVED]

C19 — secondary bridge dependency set; C3's module documentation names ats_governor_fixed.py, ats_statistics.py, and ats_embeddings.py. These files were not present in ATS. [OBSERVED]

C20 — bridge WAL persistence path /tmp/ats_kernel_bridge.log; C3 constructs a WAL with this default path. [OBSERVED]

C21 — documented operational sinks; documentation names Slack, PagerDuty, JIRA, email, databases, encrypted legal archives, and board notification as integration or deployment endpoints. No local implementation of these endpoints was found. [DOCUMENTED]

C22 — documented threat-model schemas CandidateRecord, AuditReportRecord, and GovernorFinding. [DOCUMENTED]

C23 — bridge event contract; C3 defines CandidateSignals and constructs NormalizedEvent-compatible deltas, Provenance, Verdict, and TrafficPayload values for C17. [OBSERVED]

C24 — text-artifact governance contract; C4 defines SystemConfig and AuditLogger record fields and uses them across SynapsisGSA components. [OBSERVED]

TOTAL COMPONENT COUNT: 24. The 15 root files were enumerated completely. External interfaces, named schemas, missing dependencies, and the explicitly configured persistence path were enumerated only where they were named or directly observed. [OBSERVED]

## Phase 2: Seam extraction

SEAM ID: S1
NAME: Decision ingestion
TYPE: DATA; secondary STATE [OBSERVED]
SIDE A: C16 [OBSERVED]
SIDE B: C1 / StreamingBiasMonitor [OBSERVED]
WHAT CROSSES: A candidate object and a decision string cross through ingest_decision(candidate, decision). [OBSERVED]
CONTRACT: The method appends a dictionary containing candidate and decision to decision_buffer and triggers batch analysis when the buffer length is divisible by batch_size. [OBSERVED]
ENFORCEMENT: Python method invocation and a deque are the only observed enforcement; no input schema validation is present in the method. [OBSERVED]
LOCATION: ats_governor_production.py, StreamingBiasMonitor.ingest_decision. [OBSERVED]
ORIGIN: README and integration documents describe a scoring/decision stream entering a governor monitor. [DOCUMENTED]
DEPENDS ON: None confirmed. [NO EVIDENCE]
FAILURE MODE: Missing fields can reach later analysis functions that access candidate attributes by key; the observed code can therefore raise a key-related exception or compute from incomplete data. [OBSERVED]
CONFIDENCE: high — the method, buffer write, and batch trigger are directly readable. [OBSERVED]

SEAM ID: S2
NAME: Streaming decision buffer to batch analyzer
TYPE: STATE; secondary TIME [OBSERVED]
SIDE A: C1 / StreamingBiasMonitor.decision_buffer [OBSERVED]
SIDE B: C1 / StreamingBiasMonitor.analyze_batch [OBSERVED]
WHAT CROSSES: Buffered decision dictionaries cross into a batch analysis operation. [OBSERVED]
CONTRACT: Analysis is attempted at each multiple of batch_size, and analyze_batch returns without analysis when fewer than ten decisions are present. [OBSERVED]
ENFORCEMENT: deque(maxlen=1000), the modulo batch-size check, and the minimum-count conditional hold the boundary. [OBSERVED]
LOCATION: ats_governor_production.py, StreamingBiasMonitor.__init__, ingest_decision, and analyze_batch. [OBSERVED]
ORIGIN: The batch size and minimum-count behavior are coded values; no external requirement producing those values is identified. [NO EVIDENCE]
DEPENDS ON: S1 [OBSERVED]
FAILURE MODE: Records beyond the deque maximum are discarded from the in-memory buffer, and batches below the minimum are not analyzed. [OBSERVED]
CONFIDENCE: high — buffer size, trigger, and minimum are directly readable. [OBSERVED]

SEAM ID: S3
NAME: Geographic rejection-gap detection
TYPE: DATA; secondary TRUST [OBSERVED]
SIDE A: C1 / StreamingBiasMonitor.analyze_batch [OBSERVED]
SIDE B: C1 / geographic gap calculation [OBSERVED]
WHAT CROSSES: Candidate location_distance_miles values and REJECTED decisions cross into a remote/local rejection-rate comparison. [OBSERVED]
CONTRACT: Remote is distance greater than 100 miles; local is distance at or below 100 miles; an absolute rejection-rate gap greater than 0.15 produces a signature. [OBSERVED]
ENFORCEMENT: Hard-coded predicates, rejection counts, and threshold comparisons in _compute_rejection_gap_by and analyze_batch. [OBSERVED]
LOCATION: ats_governor_production.py, StreamingBiasMonitor.analyze_batch and _compute_rejection_gap_by. [OBSERVED]
ORIGIN: README and toolkit documentation describe geographic bias and a geographic gap threshold. [DOCUMENTED]
DEPENDS ON: S2 [OBSERVED]
FAILURE MODE: A missing or nonnumeric location value prevents the predicate from completing; a detected gap produces an AuditEvent and may enter critical_alerts. [OBSERVED]
CONFIDENCE: high — the grouping predicate and thresholds are directly readable. [OBSERVED]

SEAM ID: S4
NAME: Employment-volatility rejection-gap detection
TYPE: DATA; secondary TRUST [OBSERVED]
SIDE A: C1 / StreamingBiasMonitor.analyze_batch [OBSERVED]
SIDE B: C1 / employment-volatility gap calculation [OBSERVED]
WHAT CROSSES: employment_history length, years_professional, and REJECTED decisions cross into a stable/volatile comparison. [OBSERVED]
CONTRACT: Volatile is employment-history length divided by max(years_professional, 1) greater than 1.5; a gap greater than 0.15 produces a signature. [OBSERVED]
ENFORCEMENT: Hard-coded ratio, group predicate, and threshold checks. [OBSERVED]
LOCATION: ats_governor_production.py, StreamingBiasMonitor.analyze_batch and _compute_rejection_gap_by. [OBSERVED]
ORIGIN: README and toolkit documentation name employment volatility as a demographic proxy or bias signal. [DOCUMENTED]
DEPENDS ON: S2 [OBSERVED]
FAILURE MODE: Missing or incompatible employment fields prevent the ratio or predicate from completing; a detected gap produces an alert event. [OBSERVED]
CONFIDENCE: high — the ratio and thresholds are directly readable. [OBSERVED]

SEAM ID: S5
NAME: Name-proxy rejection-gap detection
TYPE: DATA; secondary TRUST [OBSERVED]
SIDE A: C1 / StreamingBiasMonitor.analyze_batch [OBSERVED]
SIDE B: C1 / name-proxy gap calculation [OBSERVED]
WHAT CROSSES: Candidate name values and REJECTED decisions cross into a vowel-ratio group comparison. [OBSERVED]
CONTRACT: The proxy group is vowel_ratio(name) greater than 0.4; a gap greater than 0.15 creates a CRITICAL, action-required signature. [OBSERVED]
ENFORCEMENT: _vowel_ratio and hard-coded threshold branches. [OBSERVED]
LOCATION: ats_governor_production.py, StreamingBiasMonitor.analyze_batch and _vowel_ratio. [OBSERVED]
ORIGIN: README and toolkit documentation name name-based or demographic proxy detection. [DOCUMENTED]
DEPENDS ON: S2 [OBSERVED]
FAILURE MODE: A missing or non-string name prevents vowel-ratio processing; a detected gap is stored as a critical alert. [OBSERVED]
CONFIDENCE: high — the function and branch are directly readable. [OBSERVED]

SEAM ID: S6
NAME: Audit event to alert state
TYPE: CONTROL; secondary STATE [OBSERVED]
SIDE A: C1 / StreamingBiasMonitor [OBSERVED]
SIDE B: C1 / ATSGovernorProduction.alert_log and critical_alerts [OBSERVED]
WHAT CROSSES: AuditEvent fields timestamp, event_type, severity, details, and action_required cross into alert collections. [OBSERVED]
CONTRACT: process_hiring_decision stores the event as a dictionary in alert_log and stores CRITICAL or action-required events in critical_alerts. [OBSERVED]
ENFORCEMENT: The ATSGovernorProduction.process_hiring_decision branch controls the two list writes. [OBSERVED]
LOCATION: ats_governor_production.py, ATSGovernorProduction.process_hiring_decision. [OBSERVED]
ORIGIN: README describes alerts and pause/full-audit routing after monitor findings. [DOCUMENTED]
DEPENDS ON: S1, S3, S4, S5 [OBSERVED]
FAILURE MODE: If an event is not returned or is not marked with the expected severity/action flag, it is not entered into the corresponding collection. [INFERRED]
CONFIDENCE: high — the event construction and list conditions are directly readable. [OBSERVED]

SEAM ID: S7
NAME: Safeguard verification inputs
TYPE: TRUST; secondary DATA [OBSERVED]
SIDE A: C1 / ATSGovernorProduction caller [OBSERVED]
SIDE B: C1 / SafeguardVerifier [OBSERVED]
WHAT CROSSES: Scoring-function source text, candidate data at scoring, and validation context cross into verification methods. [OBSERVED]
CONTRACT: Geographic code is checked for listed location patterns, candidate keys are checked for name fields, and independent validation returns a NEEDS_VERIFICATION result with unverified checks. [OBSERVED]
ENFORCEMENT: String-pattern scans, key inspection, and fixed result construction. [OBSERVED]
LOCATION: ats_governor_production.py, SafeguardVerifier.verify_geographic_blind_scoring, verify_name_anonymization, and verify_independent_validation. [OBSERVED]
ORIGIN: Integration and toolkit documents describe geographic blinding, anonymization, and independent validation as safeguards. [DOCUMENTED]
DEPENDS ON: None confirmed. [NO EVIDENCE]
FAILURE MODE: A pattern absent from source text or a name-free key set returns IMPLEMENTED even though runtime behavior outside the inspected input is not checked. [OBSERVED]
CONFIDENCE: high — verifier branches and return values are directly readable. [OBSERVED]

SEAM ID: S8
NAME: Full-audit orchestration
TYPE: CONTROL; secondary TIME [OBSERVED]
SIDE A: C16 [OBSERVED]
SIDE B: C1 / ATSGovernorProduction.run_full_audit [OBSERVED]
WHAT CROSSES: Candidate arrays, decision arrays, and an optional audit report cross into sequential monitor, inversion, validation, packaging, and neutralization steps. [OBSERVED]
CONTRACT: The method runs the listed stages, serializes a report, and chooses IMMEDIATE_PAUSE_AND_INVESTIGATE when biases and contradictions are both present; otherwise it chooses CONTINUE_WITH_MONITORING. [OBSERVED]
ENFORCEMENT: Direct Python call sequence and conditional recommendation. [OBSERVED]
LOCATION: ats_governor_production.py, ATSGovernorProduction.run_full_audit. [OBSERVED]
ORIGIN: Package and integration documents describe a full audit after alerts and legal evidence packaging. [DOCUMENTED]
DEPENDS ON: S3, S4, S5, S7 [OBSERVED]
FAILURE MODE: Missing report data skips AuditReportValidator; a missing class or malformed candidate/decision data interrupts the sequence. [OBSERVED]
CONFIDENCE: high — the orchestration sequence is directly readable. [OBSERVED]

SEAM ID: S9
NAME: Counter-system decision ingestion
TYPE: DATA; secondary STATE [OBSERVED]
SIDE A: C16 [OBSERVED]
SIDE B: C2 / CounterATS [OBSERVED]
WHAT CROSSES: Candidate arrays and decision arrays cross into DecisionFunctionInverter.ingest_decisions. [OBSERVED]
CONTRACT: The arrays are assigned to the inverter without an observed schema or length validation. [OBSERVED]
ENFORCEMENT: Attribute assignment in Python. [OBSERVED]
LOCATION: counter_system.py, DecisionFunctionInverter.ingest_decisions and CounterATS.audit. [OBSERVED]
ORIGIN: README and package documentation describe candidate and decision arrays as audit inputs. [DOCUMENTED]
DEPENDS ON: None confirmed. [NO EVIDENCE]
FAILURE MODE: Inconsistent array lengths or missing fields are available to later detection methods. [OBSERVED]
CONFIDENCE: high — assignment and caller are directly readable. [OBSERVED]

SEAM ID: S10
NAME: Counter geographic pattern detection
TYPE: DATA; secondary TRUST [OBSERVED]
SIDE A: C2 / DecisionFunctionInverter [OBSERVED]
SIDE B: C2 / geographic pattern result [OBSERVED]
WHAT CROSSES: Candidate location_distance_miles and decision values cross into remote/local rejection-rate comparison. [OBSERVED]
CONTRACT: Remote is greater than 100 miles, local is at most 100 miles, and a gap greater than 0.30 creates a BiasSignature. [OBSERVED]
ENFORCEMENT: Direct list comprehensions, counts, and threshold comparison. [OBSERVED]
LOCATION: counter_system.py, DecisionFunctionInverter.detect_correlated_rejection_patterns. [OBSERVED]
ORIGIN: The red-team and toolkit documents describe geographic inversion and gap detection. [DOCUMENTED]
DEPENDS ON: S9 [OBSERVED]
FAILURE MODE: Missing location data or no group members affects the rate calculation; a qualifying gap appends a signature. [OBSERVED]
CONFIDENCE: high — predicates and output construction are directly readable. [OBSERVED]

SEAM ID: S11
NAME: Counter employment-volatility pattern detection
TYPE: DATA; secondary TRUST [OBSERVED]
SIDE A: C2 / DecisionFunctionInverter [OBSERVED]
SIDE B: C2 / employment-volatility pattern result [OBSERVED]
WHAT CROSSES: Employment-history length, years_professional, and decision values cross into stable/volatile rejection-rate comparison. [OBSERVED]
CONTRACT: Stable is at most 1.5 and volatile is greater than 1.5 for the history/year ratio; a gap greater than 0.20 creates a BiasSignature. [OBSERVED]
ENFORCEMENT: Direct ratio, group, count, and threshold operations. [OBSERVED]
LOCATION: counter_system.py, DecisionFunctionInverter.detect_correlated_rejection_patterns. [OBSERVED]
ORIGIN: The red-team and toolkit documents describe employment volatility as an examined pattern. [DOCUMENTED]
DEPENDS ON: S9 [OBSERVED]
FAILURE MODE: Missing or incompatible employment fields interrupt the ratio calculation; a qualifying gap appends a signature. [OBSERVED]
CONFIDENCE: high — predicates and output construction are directly readable. [OBSERVED]

SEAM ID: S12
NAME: Counter name-proxy pattern detection
TYPE: DATA; secondary TRUST [OBSERVED]
SIDE A: C2 / DecisionFunctionInverter [OBSERVED]
SIDE B: C2 / name-proxy pattern result [OBSERVED]
WHAT CROSSES: Candidate names and decision values cross into a vowel-ratio group comparison. [OBSERVED]
CONTRACT: The group boundary is vowel_ratio(name) greater than 0.4 and a gap greater than 0.20 creates a BiasSignature. [OBSERVED]
ENFORCEMENT: Direct character counting, group construction, and threshold comparison. [OBSERVED]
LOCATION: counter_system.py, DecisionFunctionInverter.detect_correlated_rejection_patterns. [OBSERVED]
ORIGIN: The README, toolkit, and red-team documents name name or demographic proxy analysis. [DOCUMENTED]
DEPENDS ON: S9 [OBSERVED]
FAILURE MODE: Missing or non-string names interrupt ratio calculation; a qualifying gap appends a signature. [OBSERVED]
CONFIDENCE: high — the proxy calculation is directly readable. [OBSERVED]

SEAM ID: S13
NAME: Synthetic-validation circularity check
TYPE: TRUST; secondary DATA [OBSERVED]
SIDE A: C16 [OBSERVED]
SIDE B: C2 / SyntheticValidationBreaker [OBSERVED]
WHAT CROSSES: System validation accuracy and real-world rejection rate cross into a difference calculation. [OBSERVED]
CONTRACT: The method compares validation accuracy with one minus rejection rate and labels the result suspicious when the difference exceeds 0.30. [OBSERVED]
ENFORCEMENT: Numeric subtraction and threshold branch in analyze_validation_circularity. [OBSERVED]
LOCATION: counter_system.py, SyntheticValidationBreaker.analyze_validation_circularity. [OBSERVED]
ORIGIN: The red-team analysis and package documentation describe synthetic validation and circularity checks. [DOCUMENTED]
DEPENDS ON: None confirmed. [NO EVIDENCE]
FAILURE MODE: Non-numeric inputs prevent the calculation; a difference at or below the threshold returns an appears-genuine label. [OBSERVED]
CONFIDENCE: high — input use and threshold are directly readable. [OBSERVED]

SEAM ID: S14
NAME: Audit-report reconciliation
TYPE: TRUST; secondary DATA [OBSERVED]
SIDE A: C16 / audit report and decision data [OBSERVED]
SIDE B: C2 / AuditReportValidator [OBSERVED]
WHAT CROSSES: Claimed approval rate, observed approval rate, candidate count, and claimed geographic diversity cross into contradiction checks. [OBSERVED]
CONTRACT: Approval-rate mismatch above 0.02 creates a contradiction; geographic diversity above 0.95 creates a contradiction. [OBSERVED]
ENFORCEMENT: Numeric comparisons in validate_audit_report. [OBSERVED]
LOCATION: counter_system.py, AuditReportValidator.validate_audit_report. [OBSERVED]
ORIGIN: Integration, toolkit, and red-team documents describe audit-report reconciliation. [DOCUMENTED]
DEPENDS ON: S9 [OBSERVED]
FAILURE MODE: Missing report keys or empty candidate data interrupt validation; a contradiction is returned as a dictionary rather than silently changing the report. [OBSERVED]
CONFIDENCE: high — validation conditions and output are directly readable. [OBSERVED]

SEAM ID: S15
NAME: Bias signatures to neutralization recommendations
TYPE: CONTROL; secondary DATA [OBSERVED]
SIDE A: C2 / detected BiasSignature list [OBSERVED]
SIDE B: C2 / BiasNeutralizationEngine [OBSERVED]
WHAT CROSSES: Bias type, affected candidates, correlation strength, hidden factor, and evidence confidence cross into correction and safeguard recommendations. [OBSERVED]
CONTRACT: The engine computes correction_factor as correlation_strength multiplied by evidence_confidence and returns recommendation dictionaries. [OBSERVED]
ENFORCEMENT: BiasSignature fields and deterministic dictionary construction. [OBSERVED]
LOCATION: counter_system.py, BiasNeutralizationEngine.apply_corrections and propose_system_safeguards. [OBSERVED]
ORIGIN: The decision framework and package documentation describe remediation and safeguards after findings. [DOCUMENTED]
DEPENDS ON: S10, S11, S12, S14 [OBSERVED]
FAILURE MODE: A signature with absent or nonnumeric confidence fields prevents correction-factor calculation; recommendation output does not itself change an external decision. [OBSERVED]
CONFIDENCE: high — the data flow and formula are directly readable. [OBSERVED]

SEAM ID: S16
NAME: Counter-audit result to caller
TYPE: DATA; secondary CONTROL [OBSERVED]
SIDE A: C2 / CounterATS [OBSERVED]
SIDE B: C16 [OBSERVED]
WHAT CROSSES: Verdicts, findings, contradictions, corrections, safeguards, and a summary cross as a returned dictionary. [OBSERVED]
CONTRACT: CounterATS.audit returns the assembled result and sets a summary recommendation to DISABLE_SYSTEM_AND_IMPLEMENT_SAFEGUARDS. [OBSERVED]
ENFORCEMENT: Python dictionary construction and return. [OBSERVED]
LOCATION: counter_system.py, CounterATS.audit. [OBSERVED]
ORIGIN: Package and decision-framework documents describe findings, safeguards, and system-level recommendations. [DOCUMENTED]
DEPENDS ON: S9, S10, S11, S12, S13, S14, S15 [OBSERVED]
FAILURE MODE: The total_candidates_affected expression uses set().union over affected-candidate lists and can fail when the list of biases is empty. [OBSERVED]
CONFIDENCE: high — return structure and the union expression are directly readable. [OBSERVED]

SEAM ID: S17
NAME: CandidateSignals event construction
TYPE: DATA; secondary IDENTITY [OBSERVED]
SIDE A: C16 [OBSERVED]
SIDE B: C3 / CandidateSignals and ATSKernelAdapter [OBSERVED]
WHAT CROSSES: Candidate ID, job ID, scores, decision, confidence, algorithm version, location distance, explanation fields, and resume counts cross into a typed dataclass. [OBSERVED]
CONTRACT: CandidateSignals stores the named fields and to_event_delta serializes them with verdict and evaluated_at. [OBSERVED]
ENFORCEMENT: Dataclass construction and explicit dictionary mapping. [OBSERVED]
LOCATION: ats_kernel_bridge.py, CandidateSignals and ATSKernelAdapter.to_event_delta. [OBSERVED]
ORIGIN: C3's module documentation states that the adapter maps ATS decisions into normalized events. [DOCUMENTED]
DEPENDS ON: None confirmed. [NO EVIDENCE]
FAILURE MODE: A caller that omits a required dataclass field fails at construction; an incompatible field value reaches the explicit mapping. [OBSERVED]
CONFIDENCE: high — the dataclass and mapping are directly readable. [OBSERVED]

SEAM ID: S18
NAME: Adapter commit to governance ledger
TYPE: PERSISTENCE; secondary DATA, IDENTITY [OBSERVED]
SIDE A: C3 / ATSKernelAdapter [OBSERVED]
SIDE B: C17 / EventStore and Provenance [OBSERVED]
WHAT CROSSES: Entity ID, event type hiring_decision, event delta, actor ID, policy ID, and justification cross into EventStore.append. [OBSERVED]
CONTRACT: commit calls EventStore.append with candidate_id, event type, delta, and a Provenance object built with external actor, policy, and justification fields. [OBSERVED]
ENFORCEMENT: Explicit method call and constructed Provenance value; the imported ledger supplies any further enforcement. [OBSERVED]
LOCATION: ats_kernel_bridge.py, ATSKernelAdapter.build_provenance and commit. [OBSERVED]
ORIGIN: C3's module documentation describes the bridge as an integration with a governance kernel and lists provenance as part of the dependency chain. [DOCUMENTED]
DEPENDS ON: S17, S40 [OBSERVED]
FAILURE MODE: The bridge cannot import or commit when the required external module is unavailable; ledger behavior beyond the call is not readable in ATS. [OBSERVED]
CONFIDENCE: high — the call signature and import are directly readable. [OBSERVED]

SEAM ID: S19
NAME: Signal state to forensic policy VM
TYPE: CONTROL; secondary DATA, TRUST [OBSERVED]
SIDE A: C3 / ATSKernelAdapter and ATSKernelGovernor [OBSERVED]
SIDE B: C17 / PolicyVM [OBSERVED]
WHAT CROSSES: A subset of CandidateSignals plus initial Verdict.ALLOW crosses into PolicyVM.step. [OBSERVED]
CONTRACT: The state includes coverage, density, confidence, similarity, word count, location distance, and verdict; policy evaluation returns a verdict and state. [OBSERVED]
ENFORCEMENT: Explicit vm_state construction and PolicyVM.step call. [OBSERVED]
LOCATION: ats_kernel_bridge.py, ATSGovernorKernel.evaluate_candidate. [OBSERVED]
ORIGIN: C3's module docstring describes forensic policies and a governance-kernel bridge. [DOCUMENTED]
DEPENDS ON: S17, S40 [OBSERVED]
FAILURE MODE: A missing PolicyVM dependency prevents evaluation; a policy may change the returned verdict according to the imported VM behavior, which is not locally readable. [OBSERVED]
CONFIDENCE: high — state fields and call site are directly readable; imported VM behavior is not available. [OBSERVED]

SEAM ID: S20
NAME: Forensic policy registration and evaluation
TYPE: TRUST; secondary CONTROL [OBSERVED]
SIDE A: C3 / policy factory functions [OBSERVED]
SIDE B: C17 / PolicyVM [OBSERVED]
WHAT CROSSES: Four policy objects cross into PolicyVM construction: keyword stuffing, low confidence, synthetic alignment, and geographic anomaly. [OBSERVED]
CONTRACT: The factories define ISOLATE or THROTTLE outcomes for their listed predicates, with some branches preserving an existing ISOLATE verdict. [OBSERVED]
ENFORCEMENT: Policy object construction in C3 and PolicyVM construction/evaluation in C17. [OBSERVED]
LOCATION: ats_kernel_bridge.py, make_keyword_stuffing_policy, make_low_confidence_policy, make_synthetic_alignment_policy, make_geo_anomaly_policy, build_forensic_policy_vm. [OBSERVED]
ORIGIN: C3's module docstring calls these policies forensic policies; no separate source requirement is identified. [DOCUMENTED]
DEPENDS ON: S19, S40 [OBSERVED]
FAILURE MODE: If PolicyVM construction or evaluation is unavailable, no bridge verdict is produced; policy priority or composition behavior is not locally determinable. [OBSERVED]
CONFIDENCE: high — policy predicates are directly readable, while VM internals are unavailable. [OBSERVED]

SEAM ID: S21
NAME: Manifest invariants to transition auditor
TYPE: TRUST; secondary CONTROL [OBSERVED]
SIDE A: C3 / build_ats_manifest [OBSERVED]
SIDE B: C17 / GovernanceAuditor and GovernanceChassis [OBSERVED]
WHAT CROSSES: Manifest ID, version, invariant functions, and a candidate transition cross into runtime materialization and audit verification. [OBSERVED]
CONTRACT: The local invariants require escalation_logged after ISOLATE and nonempty provenance justification for a hiring decision. [OBSERVED]
ENFORCEMENT: Manifest construction in C3 and verify_transition through imported governance objects. [OBSERVED]
LOCATION: ats_kernel_bridge.py, build_ats_manifest and ATSGovernorKernel.evaluate_candidate. [OBSERVED]
ORIGIN: C3's module docstring identifies manifest invariants as a bridge component. [DOCUMENTED]
DEPENDS ON: S18, S19, S40 [OBSERVED]
FAILURE MODE: A failed verification causes the bridge to append an escalation_logged event and verify again; imported auditor behavior is unavailable. [OBSERVED]
CONFIDENCE: high — local invariant functions and invocation are directly readable. [OBSERVED]

SEAM ID: S22
NAME: Invalid transition to escalation event
TYPE: CONTROL; secondary PERSISTENCE, IDENTITY [OBSERVED]
SIDE A: C3 / GovernanceAuditor result [OBSERVED]
SIDE B: C17 / EventStore [OBSERVED]
WHAT CROSSES: Candidate ID, escalation_logged event type, empty delta, and manifest_enforcer provenance cross into the ledger when the initial transition is invalid. [OBSERVED]
CONTRACT: The branch appends escalation_logged, rematerializes state, and re-verifies the transition. [OBSERVED]
ENFORCEMENT: Conditional branch on valid_transition and explicit EventStore.append call. [OBSERVED]
LOCATION: ats_kernel_bridge.py, ATSKernelGovernor.evaluate_candidate. [OBSERVED]
ORIGIN: The local manifest invariant explicitly requires escalation for ISOLATE transitions. [OBSERVED]
DEPENDS ON: S18, S21, S40 [OBSERVED]
FAILURE MODE: If append or re-verification fails, evaluate_candidate cannot complete; the escalation event itself is not available without C17. [OBSERVED]
CONFIDENCE: high — the conditional branch and append payload are directly readable. [OBSERVED]

SEAM ID: S23
NAME: ATS metrics to governance traffic payload
TYPE: DATA; secondary CONTROL [OBSERVED]
SIDE A: C3 / CandidateSignals and verdict [OBSERVED]
SIDE B: C17 / TrafficPayload and GovernanceChassis [OBSERVED]
WHAT CROSSES: keyword_score, verdict, keyword_density, resume_word_count, and semantic_similarity are repurposed as latency, abort_rate, reentry_rate, load_depth, and determinism_index. [OBSERVED]
CONTRACT: The bridge constructs TrafficPayload and calls GovernanceChassis.step, preserving the mapped values in a regime/energy/entropy result used in the WAL record. [OBSERVED]
ENFORCEMENT: Explicit field mapping and imported chassis call. [OBSERVED]
LOCATION: ats_kernel_bridge.py, ATSGovernorKernel.evaluate_candidate. [OBSERVED]
ORIGIN: C3's source comments identify this as metric repurposing for the governance chassis. [DOCUMENTED]
DEPENDS ON: S17, S19, S40 [OBSERVED]
FAILURE MODE: A missing TrafficPayload or GovernanceChassis import prevents this stage; semantic interpretation of the repurposed metrics is not locally specified. [OBSERVED]
CONFIDENCE: high — mapping and call are directly readable. [OBSERVED]

SEAM ID: S24
NAME: Governance decision to WAL persistence
TYPE: PERSISTENCE; secondary DATA, TIME [OBSERVED]
SIDE A: C3 / ATSGovernorKernel [OBSERVED]
SIDE B: C20 / WAL file path [OBSERVED]
WHAT CROSSES: Timestamp, candidate/job IDs, verdict, policy flags, block hash, ledger sequence, manifest status, escalation state, chassis values, and algorithm version cross into a WAL record. [OBSERVED]
CONTRACT: A WAL is constructed with a default path and append is called once per evaluated candidate. [OBSERVED]
ENFORCEMENT: Imported WAL object and explicit record dictionary. [OBSERVED]
LOCATION: ats_kernel_bridge.py, ATSGovernorKernel.__init__ and evaluate_candidate; default /tmp/ats_kernel_bridge.log. [OBSERVED]
ORIGIN: The source contains the default path and WAL calls; no external origin is identified. [NO EVIDENCE]
DEPENDS ON: S18, S19, S23, S40 [OBSERVED]
FAILURE MODE: The WAL path may be unavailable or append may fail; the local in-memory decisions list is updated after the append call. [OBSERVED]
CONFIDENCE: high — path, record fields, and append call are directly readable. [OBSERVED]

SEAM ID: S25
NAME: Ledger and WAL state to audit replay
TYPE: PERSISTENCE; secondary DATA [OBSERVED]
SIDE A: C17 / EventStore and C20 / WAL [OBSERVED]
SIDE B: C3 / replay_audit_trail and callers [OBSERVED]
WHAT CROSSES: Entity-scoped event sequence, event type, delta, provenance, and block hash cross into a replay list. [OBSERVED]
CONTRACT: replay_audit_trail calls EventStore.stream_for and returns selected event fields; WAL replay is performed by the module entry-point harness through the imported WAL object. [OBSERVED]
ENFORCEMENT: Explicit stream_for call and field selection. [OBSERVED]
LOCATION: ats_kernel_bridge.py, ATSGovernorKernel.replay_audit_trail and module entry-point harness. [OBSERVED]
ORIGIN: C3's module docstring names audit replay as part of the bridge behavior. [DOCUMENTED]
DEPENDS ON: S18, S24, S40 [OBSERVED]
FAILURE MODE: If the ledger or WAL is unavailable, replay cannot return the recorded sequence; imported replay semantics are not locally readable. [OBSERVED]
CONFIDENCE: high — local replay call and selected fields are directly readable. [OBSERVED]

SEAM ID: S26
NAME: Bridge entry-point cases to ledger/WAL harness
TYPE: CONTROL; secondary PERSISTENCE [OBSERVED]
SIDE A: C16 / module invocation [OBSERVED]
SIDE B: C3 / module entry-point harness [OBSERVED]
WHAT CROSSES: Generated CandidateSignals cases cross through evaluate_candidate, then expected verdicts and replay checks cross into printed harness results. [OBSERVED]
CONTRACT: The harness creates thirty cases, evaluates them, closes the WAL, replays it, and checks memory and ledger-chain conditions. [OBSERVED]
ENFORCEMENT: if __name__ == "__main__" control flow and explicit assertions/checks in the module body. [OBSERVED]
LOCATION: ats_kernel_bridge.py, module entry point and _make_signals. [OBSERVED]
ORIGIN: The bridge source contains the harness; no separate origin requirement is identified. [NO EVIDENCE]
DEPENDS ON: S17, S18, S24, S25, S40 [OBSERVED]
FAILURE MODE: The entry point fails at import when C17 is absent, before its cases can run. [OBSERVED]
CONFIDENCE: high — the entry point and import failure are directly observed. [OBSERVED]

SEAM ID: S27
NAME: SystemConfig to Synapsis components
TYPE: DATA; secondary STATE [OBSERVED]
SIDE A: C24 / SystemConfig [OBSERVED]
SIDE B: C4 / SynapsisGSA components [OBSERVED]
WHAT CROSSES: Approval threshold, rejection floor, historical DAR, confidence floor, minimum words, stuffing limits, repeat limits, and filler limits cross into component initialization and routing. [OBSERVED]
CONTRACT: SystemConfig defines defaults used by MasterGovernanceControl, ResumeSubstanceValidator, and TandemAlphaBetaBridge decisions. [OBSERVED]
ENFORCEMENT: Dataclass-like class fields and direct attribute reads. [OBSERVED]
LOCATION: ATS_from_Perplexity.txt, SystemConfig and SynapsisGSA.__init__/process_candidate_ingress. [OBSERVED]
ORIGIN: The text artifact defines the configuration values; no external source for their values is identified. [NO EVIDENCE]
DEPENDS ON: None confirmed. [NO EVIDENCE]
FAILURE MODE: A changed or missing configuration attribute changes routing comparisons or interrupts component execution. [OBSERVED]
CONFIDENCE: high — definitions and reads are directly readable. [OBSERVED]

SEAM ID: S28
NAME: AuditLogger record chain
TYPE: PERSISTENCE; secondary TRUST, TIME [OBSERVED]
SIDE A: C4 / Synapsis components [OBSERVED]
SIDE B: C24 / AuditLogger.entries [OBSERVED]
WHAT CROSSES: Module name, action, details, timestamp, sequence, previous hash, and current hash cross into an in-memory ordered audit list. [OBSERVED]
CONTRACT: record canonicalizes details, hashes a sorted JSON body with SHA-256, links prev_hash and seq, and verify_chain recomputes links and hashes. [OBSERVED]
ENFORCEMENT: AuditLogger.record, verify_chain, and head_hash. [OBSERVED]
LOCATION: ATS_from_Perplexity.txt, AuditLogger. [OBSERVED]
ORIGIN: The text artifact describes an append-and-verify audit logger in its source comments and method names. [DOCUMENTED]
DEPENDS ON: S27 [OBSERVED]
FAILURE MODE: Editing or deleting an entry causes the observed chain verification checks to fail; entries are in memory and no durable backend is shown. [OBSERVED]
CONFIDENCE: high — hash construction and verification are directly readable. [OBSERVED]

SEAM ID: S29
NAME: Job-description text to requirements
TYPE: DATA; secondary CONTROL [OBSERVED]
SIDE A: C16 / job-description input [OBSERVED]
SIDE B: C4 / JDRequirementExtractor and SkillOntology [OBSERVED]
WHAT CROSSES: JD text crosses into normalized requirements and canonical/surface phrase mappings. [OBSERVED]
CONTRACT: The extractor returns requirement records and logs REQUIREMENTS_DERIVED_FROM_JD or a no-requirements event. [OBSERVED]
ENFORCEMENT: Regex/phrase processing and explicit AuditLogger calls. [OBSERVED]
LOCATION: ATS_from_Perplexity.txt, SkillOntology and JDRequirementExtractor. [OBSERVED]
ORIGIN: The text artifact names JD extraction and ontology normalization as module behavior. [DOCUMENTED]
DEPENDS ON: S28 [OBSERVED]
FAILURE MODE: Text that yields no recognized requirements enters the no-requirements path; malformed text or logger failure interrupts processing. [OBSERVED]
CONFIDENCE: high — method inputs, outputs, and logging are directly readable. [OBSERVED]

SEAM ID: S30
NAME: Resume text to substance classification
TYPE: TRUST; secondary DATA [OBSERVED]
SIDE A: C16 / candidate resume input [OBSERVED]
SIDE B: C4 / ResumeSubstanceValidator [OBSERVED]
WHAT CROSSES: Resume text crosses into word count, skill density, repeat count, filler ratio, quantified evidence, and a SUBSTANTIVE/LOW_SUBSTANCE/KEYWORD_STUFFING classification. [OBSERVED]
CONTRACT: The validator applies configured minimum words, stuffing density, repeat, and filler thresholds and returns a structured assessment. [OBSERVED]
ENFORCEMENT: String processing, ontology matching, numeric thresholds, and explicit classification branches. [OBSERVED]
LOCATION: ATS_from_Perplexity.txt, ResumeSubstanceValidator. [OBSERVED]
ORIGIN: The text artifact source comments identify heuristic resume-substance and authenticity checks. [DOCUMENTED]
DEPENDS ON: S27, S29 [OBSERVED]
FAILURE MODE: Missing or non-text resume content prevents the text metrics from being computed; the classification is still heuristic according to the artifact's own description. [DOCUMENTED]
CONFIDENCE: high — implementation and source description are directly readable. [OBSERVED]

SEAM ID: S31
NAME: Industry registration to domain vectors
TYPE: DATA; secondary STATE [OBSERVED]
SIDE A: C16 / industry input [OBSERVED]
SIDE B: C4 / DomainTranspiler [OBSERVED]
WHAT CROSSES: Industry name, canonical requirements, and candidate ontology cross into registered industry mappings and parallel vector mappings. [OBSERVED]
CONTRACT: register_industry stores an industry map; transpile maps canonical requirements to the registered domain map and logs the operation. [OBSERVED]
ENFORCEMENT: Dictionary storage, explicit registration, and mapping methods. [OBSERVED]
LOCATION: ATS_from_Perplexity.txt, DomainTranspiler.register_industry and transpile. [OBSERVED]
ORIGIN: The text artifact names domain transpilation and industry registration as components. [DOCUMENTED]
DEPENDS ON: S28, S29 [OBSERVED]
FAILURE MODE: An unregistered industry has no mapped domain vector in the observed dictionary path; logging or mapping can therefore return an empty/partial result. [INFERRED]
CONFIDENCE: high — registration and lookup code are directly readable. [OBSERVED]

SEAM ID: S32
NAME: Alpha/beta evaluation to tandem decision
TYPE: CONTROL; secondary DATA [OBSERVED]
SIDE A: C4 / SynapsisGSA candidate processing [OBSERVED]
SIDE B: C4 / TandemAlphaBetaBridge [OBSERVED]
WHAT CROSSES: Candidate ontology, JD requirements, resume substance classification, and capability-overlap values cross into TANDEM_APPROVAL, HUMAN_REVIEW, or TANDEM_REJECTION. [OBSERVED]
CONTRACT: No requirements returns human review; substantive resume plus beta at or above approval returns tandem approval; beta above rejection floor routes to governance; otherwise tandem rejection. [OBSERVED]
ENFORCEMENT: Explicit alpha/beta calculations and threshold branches. [OBSERVED]
LOCATION: ATS_from_Perplexity.txt, TandemAlphaBetaBridge.evaluate. [OBSERVED]
ORIGIN: The text artifact identifies tandem alpha/beta evaluation as a module. [DOCUMENTED]
DEPENDS ON: S27, S29, S30, S31 [OBSERVED]
FAILURE MODE: Missing requirements, ontology, or substance fields changes branch selection or interrupts evaluation. [OBSERVED]
CONFIDENCE: high — branch conditions and outputs are directly readable. [OBSERVED]

SEAM ID: S33
NAME: Mid-band decision to human-review route
TYPE: CONTROL; secondary IDENTITY [OBSERVED]
SIDE A: C4 / MasterGovernanceControl [OBSERVED]
SIDE B: C21 / documented human-review destination [DOCUMENTED]
WHAT CROSSES: A mid-band decision, priority, and historical DAR context cross into an ESCALATE_HUMAN_REVIEW_HIGH or ESCALATE_HUMAN_REVIEW_STANDARD result. [OBSERVED]
CONTRACT: The control routes mid-band cases to one of the two human-review labels using priority and historical DAR context. [OBSERVED]
ENFORCEMENT: MasterGovernanceControl.route_mid_band branch logic. [OBSERVED]
LOCATION: ATS_from_Perplexity.txt, MasterGovernanceControl.route_mid_band; human-review destination is documented in package and integration materials. [OBSERVED]
ORIGIN: The source method names human review explicitly; the documents describe human-review routing. [DOCUMENTED]
DEPENDS ON: S27, S32 [OBSERVED]
FAILURE MODE: The local result is a label; no local implementation of the external human-review destination was found. [OBSERVED]
CONFIDENCE: medium — the local routing label is direct, while the external destination is documentary only. [OBSERVED]

SEAM ID: S34
NAME: Synthetic packet to reality-anchor gate
TYPE: TRUST; secondary DATA [OBSERVED]
SIDE A: C4 / GammaRedTeam [OBSERVED]
SIDE B: C4 / RealityAnchorGate [OBSERVED]
WHAT CROSSES: Synthetic packet keys, IDs, vectors, origin, and format validity cross into accepted or rejected gate state. [OBSERVED]
CONTRACT: The gate allows only id, vectors, and origin keys, limits packets to ten, checks ID and origin patterns, and buffers accepted packets. [OBSERVED]
ENFORCEMENT: Key-set comparison, length limit, regular expressions, deque buffer, and AuditLogger record. [OBSERVED]
LOCATION: ATS_from_Perplexity.txt, RealityAnchorGate.validate_synthetic_packet and GammaRedTeam. [OBSERVED]
ORIGIN: The text artifact names a reality-anchor gate and adversarial cycle. [DOCUMENTED]
DEPENDS ON: S28 [OBSERVED]
FAILURE MODE: Extra keys, too many vectors, or invalid ID/origin causes a rejected result and a rejection log entry. [OBSERVED]
CONFIDENCE: high — gate conditions and outcomes are directly readable. [OBSERVED]

SEAM ID: S35
NAME: Candidate ingress orchestration
TYPE: CONTROL; secondary DATA, TIME [OBSERVED]
SIDE A: C16 / candidate and JD inputs [OBSERVED]
SIDE B: C4 / SynapsisGSA.process_candidate_ingress [OBSERVED]
WHAT CROSSES: Candidate data and JD text cross through requirements extraction, resume validation, ontology extraction, domain transpilation, tandem evaluation, resolution mapping, and transparency output. [OBSERVED]
CONTRACT: The method maps tandem decisions to HIRED, HUMAN_REVIEW, or REJECTED and returns candidate ID, intermediate results, resolution, and transparency directive. [OBSERVED]
ENFORCEMENT: Explicit sequential method calls and dictionary return. [OBSERVED]
LOCATION: ATS_from_Perplexity.txt, SynapsisGSA.process_candidate_ingress. [OBSERVED]
ORIGIN: The text artifact's class and method names document this orchestration path. [DOCUMENTED]
DEPENDS ON: S27, S28, S29, S30, S31, S32 [OBSERVED]
FAILURE MODE: Any failed component call interrupts the pipeline; the returned resolution is derived from the tandem result through explicit branches. [OBSERVED]
CONFIDENCE: high — the sequence and output are directly readable. [OBSERVED]

SEAM ID: S36
NAME: Transparency directive to downstream caller
TYPE: DATA; secondary IDENTITY [OBSERVED]
SIDE A: C4 / SynapsisGSA [OBSERVED]
SIDE B: C21 / documented downstream operational interface [DOCUMENTED]
WHAT CROSSES: An instruction, a message, an audit hash, and message length cross in the transparency directive. [OBSERVED]
CONTRACT: _transparency_directive returns a dictionary containing instruction, message, audit_hash, and length; the local code does not transmit it to an external endpoint. [OBSERVED]
ENFORCEMENT: Dictionary construction and inclusion in process_candidate_ingress output. [OBSERVED]
LOCATION: ATS_from_Perplexity.txt, SynapsisGSA._transparency_directive and process_candidate_ingress. [OBSERVED]
ORIGIN: The text artifact names transparency as a returned directive; external delivery is documented but not locally implemented. [DOCUMENTED]
DEPENDS ON: S28, S35 [OBSERVED]
FAILURE MODE: A downstream caller that does not preserve the returned fields has no local enforcement preventing their omission. [INFERRED]
CONFIDENCE: medium — local output is direct, while downstream handling is not present. [OBSERVED]

SEAM ID: S37
NAME: Documented records to implemented audit inputs
TYPE: DATA; secondary IDENTITY [DOCUMENTED]
SIDE A: C22 / CandidateRecord and AuditReportRecord [DOCUMENTED]
SIDE B: C1 and C2 [OBSERVED]
WHAT CROSSES: Documented candidate identifiers, features, decisions, scores, timestamps, report metrics, and counts correspond to fields read by the implemented analyzers. [DOCUMENTED]
CONTRACT: C13 documents these record shapes, while C1 and C2 directly read candidate dictionaries, decisions, and audit-report fields. [OBSERVED]
ENFORCEMENT: No parser or schema validator connecting the documented records to C1 or C2 was found. [OBSERVED]
LOCATION: ats_threat_model.md schemas; ats_governor_production.py and counter_system.py analyzer methods. [OBSERVED]
ORIGIN: The threat model documents the schemas; the analyzers use corresponding field names. [DOCUMENTED]
DEPENDS ON: S1, S9 [OBSERVED]
FAILURE MODE: Field-name or shape differences are detected only when later Python access/calculation fails or produces a different result. [INFERRED]
CONFIDENCE: medium — both ends are readable, but no connecting validator is present. [OBSERVED]

SEAM ID: S38
NAME: Documented operational sinks
TYPE: PERSISTENCE; secondary CONTROL [DOCUMENTED]
SIDE A: C1 and C2 [OBSERVED]
SIDE B: C21 / Slack, PagerDuty, JIRA, email, databases, legal archive, and board notification endpoints [DOCUMENTED]
WHAT CROSSES: Alerts, audit reports, legal evidence packages, remediation output, and archival records are described as crossing to operational destinations. [DOCUMENTED]
CONTRACT: Documentation describes these destinations and connection requirements; local code returns dictionaries, JSON, or strings and does not implement the named transports. [OBSERVED]
ENFORCEMENT: No local transport, database client, webhook, or archive implementation was found. [OBSERVED]
LOCATION: README.md, ATS_GOVERNOR_INTEGRATION.md, ATS_GOVERNOR_COMPLETE_PACKAGE.md, and C1/C2 packaging methods. [OBSERVED]
ORIGIN: The integration and deployment documents name the external destinations. [DOCUMENTED]
DEPENDS ON: S6, S8, S16 [OBSERVED]
FAILURE MODE: Without an external connector, the local result remains in memory or returned serialization and does not reach the named destination. [INFERRED]
CONFIDENCE: medium — destinations are documented and local outputs are observed, but no connector is present. [OBSERVED]

SEAM ID: S39
NAME: Hiring-decision audit input
TYPE: DATA; secondary TIME [OBSERVED]
SIDE A: C16 / candidate, decision, and optional audit-report source [OBSERVED]
SIDE B: C1 / ATSGovernorProduction.run_full_audit [OBSERVED]
WHAT CROSSES: Lists of candidates and decisions, plus an optional audit report, cross into a full-audit result. [OBSERVED]
CONTRACT: C1 accepts candidates, decisions, and audit_report=None, then produces bias signatures, contradictions, evidence packaging, corrections, and a recommendation. [OBSERVED]
ENFORCEMENT: Python function parameters and direct calls to internal analyzer classes. [OBSERVED]
LOCATION: ats_governor_production.py, ATSGovernorProduction.run_full_audit. [OBSERVED]
ORIGIN: The package and integration documents describe full audits over candidate, decision, and audit-report data. [DOCUMENTED]
DEPENDS ON: S8, S37 [OBSERVED]
FAILURE MODE: A missing optional report skips that validation stage; malformed required inputs interrupt the run. [OBSERVED]
CONFIDENCE: high — signature and body are directly readable. [OBSERVED]

SEAM ID: S40
NAME: Bridge module loading to missing governance dependency
TYPE: CONTROL; secondary TRUST [OBSERVED]
SIDE A: C3 [OBSERVED]
SIDE B: C17 and C19 [OBSERVED]
WHAT CROSSES: Python import resolution requests gov4_kernel and the dependency modules named in C3's documentation. [OBSERVED]
CONTRACT: C3 requires the imported names at module load time before ATSKernelAdapter or ATSGovernorKernel can be constructed. [OBSERVED]
ENFORCEMENT: Top-level import statements. [OBSERVED]
LOCATION: ats_kernel_bridge.py, imports near the module header. [OBSERVED]
ORIGIN: C3's module docstring explicitly lists the governance-kernel dependency chain. [DOCUMENTED]
DEPENDS ON: None confirmed. [NO EVIDENCE]
FAILURE MODE: Importing C3 in ATS raises ModuleNotFoundError for gov4_kernel because C17 is absent; the bridge cannot start. [OBSERVED]
CONFIDENCE: high — the import statement, absent file, and exception were directly observed. [OBSERVED]

SEAM ID: S41
NAME: Counter entry point to WorstATS fixture
TYPE: CONTROL; secondary IDENTITY [OBSERVED]
SIDE A: C2 / module entry point [OBSERVED]
SIDE B: C18 / worst_system.WorstATS [OBSERVED]
WHAT CROSSES: Module execution requests the WorstATS class for the counter-system demonstration. [OBSERVED]
CONTRACT: The import occurs in the if __name__ == "__main__" block and is required by that demonstration path. [OBSERVED]
ENFORCEMENT: Top-level module import inside the entry-point block. [OBSERVED]
LOCATION: counter_system.py, module entry point near the end of the file. [OBSERVED]
ORIGIN: The source comment identifies the import as testing the counter-system against the worst system. [DOCUMENTED]
DEPENDS ON: None confirmed. [NO EVIDENCE]
FAILURE MODE: Running counter_system.py as a script raises ModuleNotFoundError because worst_system.py is absent. [OBSERVED]
CONFIDENCE: high — the import and missing file were directly observed. [OBSERVED]

SEAM ID: S42
NAME: Production module entry point
TYPE: CONTROL; secondary TIME [OBSERVED]
SIDE A: C16 / Python module invocation [OBSERVED]
SIDE B: C1 / ats_governor_production.__main__ [OBSERVED]
WHAT CROSSES: The interpreter's script invocation crosses into sample candidate/decision/audit-report construction and report printing. [OBSERVED]
CONTRACT: The __main__ block instantiates ATSGovernorProduction, runs run_full_audit, and prints the report. [OBSERVED]
ENFORCEMENT: if __name__ == "__main__" branch. [OBSERVED]
LOCATION: ats_governor_production.py, module entry point. [OBSERVED]
ORIGIN: The source contains the entry-point block; no separate origin requirement is identified. [NO EVIDENCE]
DEPENDS ON: S8 [OBSERVED]
FAILURE MODE: Errors in sample data or audit orchestration prevent the demonstration from producing output. [INFERRED]
CONFIDENCE: high — entry-point statements are directly readable. [OBSERVED]

SEAM ID: S43
NAME: Text-artifact entry point
TYPE: CONTROL; secondary TIME [OBSERVED]
SIDE A: C16 / Python execution of text source [OBSERVED]
SIDE B: C4 / SynapsisGSA.run_red_blue_tests [OBSERVED]
WHAT CROSSES: Module execution invokes the red/blue test routine in the text artifact. [OBSERVED]
CONTRACT: The source has a __main__ path that calls run_red_blue_tests; the file extension is .txt rather than .py. [OBSERVED]
ENFORCEMENT: The source-level __main__ branch exists, but no local launcher for the .txt artifact was found. [OBSERVED]
LOCATION: ATS_from_Perplexity.txt, final module-entry block and run_red_blue_tests. [OBSERVED]
ORIGIN: The text artifact includes the entry-point code; no separate origin requirement is identified. [NO EVIDENCE]
DEPENDS ON: S28, S30, S34 [OBSERVED]
FAILURE MODE: A normal Python module discovery or script command does not automatically treat the .txt filename as a Python module; an explicit execution method is required. [INFERRED]
CONFIDENCE: high — file extension and source entry point are directly observed. [OBSERVED]

## Phase 3: Coverage report

Components with no confirmed runtime seam:

- C5 has no confirmed runtime seam because its bytes are identical to C3 and no code references the copy by that filename. [OBSERVED]
- C6 has no confirmed runtime seam because it is a formatted/documentary artifact and no code reference to it was found. [OBSERVED]
- C7, C8, C9, C10, C11, and C12 have documented relationships represented in S37 and S38, but no separate executable boundary from each document into a runtime component was confirmed. [OBSERVED]
- C13 has a documented schema seam represented in S37; no schema loader was found. [OBSERVED]
- C14 and C15 could not be connected to runtime components because their text was not readable in the available environment. [OBSERVED]
- C19 has documented names but no local import or executable implementation was found. [OBSERVED]
- C20 is a persistence target rather than a standalone source module; its runtime seam is represented in S24 and S25. [OBSERVED]
- C22, C23, and C24 are schema/contract components and are represented through S17, S18, S27, S28, and S37. [OBSERVED]

Parts not accessible or not readable:

- The textual contents of C14 and C15 could not be extracted because no usable PDF text extractor or installed Python PDF library was available. [OBSERVED]
- The implementation of C17, C18, and C19 was not present in ATS. [OBSERVED]
- The implementations behind the documented C21 operational sinks were not present in ATS. [OBSERVED]
- No ATS test files were present at the root during inspection. [OBSERVED]

Suspected but unconfirmed seams:

- A possible PDF-to-documentation or PDF-to-runtime relationship may exist, but no readable evidence connects C14 or C15 to another component. [INFERRED]
- A possible external human-review transport may exist for S33, but only the local review labels and documentation were observed. [INFERRED]

## Phase 4: Speculative section (quarantined)

- The PDFs may contain requirements or source material that would add seams if their text were available. [INFERRED]
- The missing governance-kernel and demonstration dependencies may contain additional enforcement or persistence boundaries not visible in ATS. [INFERRED]

Nothing in this speculative section is used as a finding above.

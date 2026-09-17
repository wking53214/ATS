# ATS Oscillation Detection Integration

## Overview

Oscillation Detection in the ATS system identifies repeated normalized events within audit trails, decisions, and findings. This is a **non-authoritative diagnostic signal** that enables detection of potential infinite loops, repeated decision patterns, or anomalous audit behavior.

The detector:
- ✓ Monitors all audit trail events
- ✓ Tracks repeated normalized outputs (decisions, findings, alerts)
- ✓ Exposes oscillation_detected as a diagnostic signal
- ✓ Has NO independent governance authority
- ✓ Does NOT modify decisions, scores, or policy

## What It Detects

**Repeated Events:**
- Same decision made multiple times: `"Candidate C001: APPROVED"` → `"Candidate C001: APPROVED"`
- Duplicate findings: `"Geographic bias detected"` → `"geographic bias detected"`
- Cyclic alerts: Same alert generated repeatedly within a batch

**What It Normalizes:**
- Whitespace: `"Bias detected"` ≡ `" bias detected "`
- Case: `"BIAS DETECTED"` ≡ `"bias detected"`
- Punctuation is preserved (deliberate, not removed)

**What It Does NOT Detect:**
- Semantic equivalence (no LLM/embeddings)
- True cycles like A→B→A (only recurrence, not full cycle)
- Cross-session contamination (reset at batch boundaries)

## Architecture

### Components

**OscillationDetector** (`ats_oscillation_detector.py`)
- Bounded deque-based history (default 64 items)
- Deterministic normalization (strip + lowercase)
- Lifecycle methods: `observe()`, `reset()`, `get_diagnostics()`

**Integration Point: CryptoAuditTrail** (`ats_governor_fixed.py`)
- Instantiates OscillationDetector in `__init__`
- Calls `detector.observe()` in `log()` method
- Adds `oscillation_detected` to every event
- Provides `reset_oscillation_detector()` and `get_oscillation_diagnostics()`

### Event Flow

```
User Action
    │
    ▼
Governor Decision / Audit Event
    │
    ▼
CryptoAuditTrail.log()
    │
    ├─────────────────────────────────────┐
    │                                       │
    ▼                                       ▼
OscillationDetector.observe()      Governance / Decision Logic
    │                              (unchanged)
    ├─→ oscillation_detected=True/False
    │
    ▼
Event logged with oscillation_detected flag
    │
    └─→ Audit trail + diagnostic signal
```

### Lifecycle Management

Oscillation history is scoped to **batch boundaries**:

```python
# Start of hiring round
governor.audit_trail.reset_oscillation_detector()

# Process candidates
for candidate in candidates:
    result = governor.process_hiring_decision(candidate, decision)
    # Each decision logged with oscillation detection

# Get diagnostics
diag = governor.audit_trail.get_oscillation_diagnostics()
print(diag)  # {"history_size": 42, "is_potentially_oscillating": True, ...}
```

## Governance Safety Guarantees

### The Detector Is Non-Authoritative

✓ Oscillation detection:
- Reports observations
- Exposes diagnostic signals
- Enables visibility into patterns

✗ Oscillation detection does NOT:
- Approve/reject candidates
- Modify decision scores
- Bypass governance controls
- Alter bias detection policy
- Execute remediation actions
- Change severity levels
- Mutate audit records (except adding oscillation_detected flag)

### Event Immutability

Oscillation detection only adds a new field (`oscillation_detected: bool`) to audit events. All other fields remain unchanged:

```python
# Before oscillation integration:
event = {
    "sequence": 1,
    "timestamp": "...",
    "event_type": "DECISION",
    "severity": "INFO",
    "details": "Candidate C001: APPROVED",
    "previous_hash": "...",
    "hash": "...",
    "hmac": "..."
}

# After oscillation integration:
event = {
    ...same as above...,
    "oscillation_detected": False  # ← NEW FIELD ONLY
}
```

### Hash Chain Integrity

The oscillation flag is included in the event JSON before hashing, so it contributes to the hash chain but does not break it. Hash verification still works:

```python
integrity = audit_trail.verify_integrity()
# Returns: {"status": "VALID", "valid": True, "violations": []}
# Even with oscillation_detected in all events
```

## Usage Examples

### Monitor Events for Oscillation

```python
from ats_governor_fixed import CryptoAuditTrail

audit_trail = CryptoAuditTrail()

# Log events; oscillation is tracked automatically
audit_trail.log("DECISION", "Candidate C001: APPROVED")
audit_trail.log("DECISION", "Candidate C001: APPROVED")  # Repeat!
audit_trail.log("ALERT", "Geographic bias detected")

# Events now have oscillation_detected flag
for event in audit_trail.events:
    if event["oscillation_detected"]:
        print(f"Repeated event: {event['event_type']}")
    # Output: Repeated event: DECISION
```

### Reset at Batch Boundaries

```python
# Start new hiring round
audit_trail.reset_oscillation_detector()

# Process new batch without prior history contamination
for candidate in next_batch:
    result = governor.process_hiring_decision(candidate, decision)
```

### Get Oscillation Diagnostics

```python
diag = audit_trail.get_oscillation_diagnostics()
print(diag)
# {
#     "history_size": 42,
#     "max_history": 64,
#     "event_type_repetitions": {"DECISION": 3, "ALERT": 1},
#     "is_potentially_oscillating": True
# }
```

### Use Oscillation Signal in Governance

```python
# In governance response logic (NOT in OscillationDetector):
if audit_trail.get_oscillation_diagnostics()["is_potentially_oscillating"]:
    # Trigger investigation/escalation
    logger.warning("Potential oscillation in audit trail; review batch")
    # This is a policy decision, NOT made by OscillationDetector
```

## Test Coverage

**23 tests** covering:

### Detector Functionality (12 tests)
- First observation returns False
- Exact repeat returns True
- Normalization (whitespace, case, combined)
- Distinct outputs return False
- Reset clears history
- Bounded history eviction
- History snapshots
- Constructor validation
- Event type tracking
- Decision dict canonical comparison

### Audit Trail Integration (8 tests)
- Events include oscillation_detected
- Repeated events flagged
- Different events not flagged
- Normalized repeats detected
- Reset works in audit trail
- Diagnostics available
- Hash chain unaffected
- Audit report includes oscillation status

### Governance Neutrality (3 tests)
- Oscillation doesn't change event_type
- Oscillation doesn't change severity
- Oscillation is purely informational

## Performance Characteristics

| Metric | Value |
|--------|-------|
| Time per observe() | O(1) amortized |
| Space per detector | O(max_history) = O(64) |
| Default max_history | 64 entries |
| Memory per entry | ~100–200 bytes (normalized string) |
| Total overhead | ~6–12 KB per audit trail |

## Known Limitations

1. **Not semantic equivalence**: `"Good candidate"` ≠ `"Excellent candidate"` (detected as different)
2. **Not full cycle detection**: Detects A→A, not A→B→A
3. **Normalized only**: Capital letters and punctuation matter after normalization
4. **No ML/embeddings**: Deterministic string matching only
5. **Bounded history**: Oldest observations are evicted at max_history limit

## Deployment Checklist

- [ ] Import `OscillationDetector` in `ats_governor_fixed.py` ✓
- [ ] Instantiate detector in `CryptoAuditTrail.__init__` ✓
- [ ] Call `detector.observe()` in `log()` method ✓
- [ ] Add `oscillation_detected` to events ✓
- [ ] Provide reset method for batch boundaries ✓
- [ ] Provide diagnostics method ✓
- [ ] Add 23 unit tests ✓
- [ ] All tests passing ✓
- [ ] Documentation complete ✓
- [ ] No governance changes ✓
- [ ] No decision logic affected ✓

## Questions & Answers

**Q: Can oscillation detection reject a candidate?**
A: No. The detector only reports observations. Decision-making remains with the Governor.

**Q: Will oscillation_detected break existing audit parsing?**
A: No. It's an additional field. Existing code ignores it; new code can read it.

**Q: What if I have a legitimately repeated decision (e.g., same candidate, same result)?**
A: This is correctly flagged as oscillation. Use diagnostics to investigate; the governance system decides response.

**Q: Can I disable oscillation detection?**
A: Yes. Don't call `detector.observe()` in the log method, or instantiate with max_history=0.

**Q: Does oscillation detection slow down auditing?**
A: Negligibly. O(1) string comparison per event; ~microseconds overhead per log call.

## See Also

- `ats_oscillation_detector.py` — Implementation
- `test_ats_oscillation_detector.py` — Full test suite
- `ats_governor_fixed.py` — Integration point
- `ats_seam_inventory.md` — Architecture overview

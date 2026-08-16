# REQ-001: Complete behavior
Status: active
Must: Return a stable result
Must-Not: Return an unstable result
Acceptance:
- A test covers the result.

# REQ-002: Code without a test
Status: active
Must: Log an event

# REQ-003: Orphan behavior
Status: active
Must: Remain traceable

# REQ-004: Broken dependency
Status: active
Depends-On: REQ-MISSING

# REQ-005: Contradictory behavior
Status: active
Must: expose the secret
Must-Not: expose the secret

# REQ-006: Cycle first
Status: active
Depends-On: REQ-007

# REQ-007: Cycle second
Status: active
Depends-On: REQ-006

# REQ-CORE-001: Authorize transfers
Status: active
Priority: must
Must: Reject a transfer when authorization fails
Must-Not: Continue after authorization fails
Acceptance:
- An unauthorized transfer returns a rejected decision.

# REQ-TRANSFER-001: Execute an authorized transfer
Status: active
Priority: must
Depends-On: REQ-CORE-001
Must: Move the requested amount exactly once
Must-Not: Create a negative balance
Acceptance:
- A valid transfer updates both balances atomically.

# REQ-AUDIT-001: Record the transfer outcome
Status: active
Priority: should
Depends-On: REQ-TRANSFER-001
Must: Record an immutable outcome event
Must-Not: Store raw credentials
Acceptance:
- Every accepted or rejected transfer produces one audit event.

from .authorization import authorized


def transfer(balance, amount):
    """Apply a valid debit exactly once. @spec REQ-TRANSFER-001"""
    if not authorized(balance, amount):
        return balance, "rejected"
    return balance - amount, "accepted"


def audit_message(status):
    """Produce a small audit value. @spec REQ-AUDIT-001"""
    return "transfer:%s" % status

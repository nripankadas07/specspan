def authorized(balance, amount):
    """Return whether a transfer can proceed. @spec REQ-CORE-001"""
    return amount > 0 and balance >= amount

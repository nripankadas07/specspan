from src.authorization import authorized
from src.transfer import transfer


def test_authorization_boundary():
    """@spec REQ-CORE-001"""
    assert authorized(100, 100)
    assert not authorized(99, 100)


def test_transfer_once():
    """@spec REQ-TRANSFER-001"""
    assert transfer(100, 40) == (60, "accepted")

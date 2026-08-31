import pytest
from app.core.config import Settings
from app.core.single_instance import SingleInstanceManager


def test_single_instance_lock_acquisition_and_release() -> None:
    test_port = 49950
    mgr1 = SingleInstanceManager(port=test_port, settings=Settings())
    assert mgr1.acquire() is True

    # Second instance on same port detects primary
    mgr2 = SingleInstanceManager(port=test_port, settings=Settings())
    assert mgr2.acquire() is False

    # Release primary instance
    mgr1.release()

    # Now second instance can acquire
    assert mgr2.acquire() is True
    mgr2.release()

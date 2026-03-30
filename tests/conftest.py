import pytest
from bitemporalorm.registry import registry


@pytest.fixture(autouse=True)
def isolate_registry():
    """Snapshot the registry before each test, clear it, restore after."""
    snap = registry.snapshot()
    registry.clear()
    yield
    registry.restore(snap)

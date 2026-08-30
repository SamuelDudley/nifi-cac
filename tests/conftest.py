import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "flows" / "telemetry"))

import pytest

import flow as telemetry


@pytest.fixture
def snapshot():
    return telemetry.build()

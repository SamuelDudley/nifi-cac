from pathlib import Path

import pytest

from nificac.cli import load

REPO = Path(__file__).resolve().parents[1]
TELEMETRY = REPO / "flows" / "telemetry"


@pytest.fixture
def build_telemetry():
    """Build the example flow from source, never from cached bytecode."""
    return lambda: load(TELEMETRY)


@pytest.fixture
def snapshot(build_telemetry):
    return build_telemetry()

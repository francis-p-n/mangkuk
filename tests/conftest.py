"""Shared paths and import wiring.

Everything here is resolved from this file's own location, never from the
working directory. The suite has to pass whether it is run as `pytest` from the
repo root, `pytest tests` from somewhere else, or by an IDE that picks its own
directory.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
SAMPLE_SUBMISSION = DATA_DIR / "sample_submission.json"

sys.path.insert(0, str(ROOT / "src"))


@pytest.fixture(scope="session")
def data_dir() -> Path:
    return DATA_DIR


@pytest.fixture(scope="session")
def sample_submission() -> Path:
    return SAMPLE_SUBMISSION


@pytest.fixture(autouse=True)
def _unpaced_agent_limiter():
    """No pacing in the suite, and a fresh budget for every test.

    The limiter exists to keep a real run inside a provider's per-minute
    allowance. A test driving a stub server has no allowance to respect, and
    waiting six seconds between calls to prove something about grounding turns
    a seventeen-second suite into a two-minute one - which is how a suite stops
    being run.

    Fresh per test because the budget is a property of a run: without this the
    first test to make calls quietly spends the allowance for every test after
    it, and the failures land somewhere unrelated to the cause.
    """
    from sdoc.agents.clients import reset_limiter

    reset_limiter(rpm=0, budget=10_000)
    yield
    reset_limiter(rpm=0, budget=10_000)

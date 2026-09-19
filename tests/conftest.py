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

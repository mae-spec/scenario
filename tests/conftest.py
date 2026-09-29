from pathlib import Path

import pytest

from app.screenplay import parse_file

FIX = Path(__file__).parent / "fixtures"


@pytest.fixture
def v1():
    return parse_file("v1.fountain", (FIX / "v1.fountain").read_bytes())


@pytest.fixture
def v2():
    return parse_file("v2.fountain", (FIX / "v2.fountain").read_bytes())


@pytest.fixture
def fixture_bytes():
    return lambda name: (FIX / name).read_bytes()

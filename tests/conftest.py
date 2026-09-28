from collections.abc import Iterator

import pytest

from evra.logging_setup import shutdown_logging


@pytest.fixture(autouse=True)
def _reset_logging() -> Iterator[None]:
    yield
    shutdown_logging()  # release log files so Windows can delete tmp dirs

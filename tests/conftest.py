from collections.abc import Iterator

import pytest

from evra.logging_setup import shutdown_logging


@pytest.fixture(autouse=True)
def _reset_logging() -> Iterator[None]:
    yield
    shutdown_logging()  # release log files so Windows can delete tmp dirs


from evra.modelstore import is_ready, load_catalog  # noqa: E402
from evra.paths import resolve_paths  # noqa: E402


def requires_models(*ids: str) -> pytest.MarkDecorator:
    """Skip unless these catalogue models are downloaded (run `uv run evra models --download`)."""
    catalogue = load_catalog()
    models_dir = resolve_paths().models_dir
    missing = [i for i in ids if not is_ready(catalogue[i], models_dir)]
    return pytest.mark.skipif(bool(missing), reason=f"models not downloaded: {missing}")

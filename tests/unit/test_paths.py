import os
import sys
from pathlib import Path

import pytest

from evra.paths import REPO_ROOT, AppPaths, is_source_checkout, resolve_paths


def test_under_puts_everything_below_root(tmp_path: Path) -> None:
    paths = AppPaths.under(tmp_path)
    assert paths.db_path == tmp_path / "data" / "evra.db"
    assert paths.settings_file == tmp_path / "config" / "settings.toml"
    assert paths.models_dir == tmp_path / "data" / "models"
    assert paths.log_dir == tmp_path / "logs"


def test_ensure_creates_directories(tmp_path: Path) -> None:
    paths = AppPaths.under(tmp_path)
    paths.ensure()
    for d in (paths.data_dir, paths.config_dir, paths.log_dir, paths.models_dir):
        assert d.is_dir()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows layout")
def test_for_user_uses_localappdata_on_windows() -> None:
    paths = AppPaths.for_user()
    local = Path(os.environ["LOCALAPPDATA"])
    assert paths.data_dir == local / "Evra"
    assert paths.db_path == local / "Evra" / "evra.db"


def _fake_checkout(root: Path) -> Path:
    (root / ".git").mkdir(parents=True)
    (root / "pyproject.toml").write_text('[project]\nname = "evra"\n', encoding="utf-8")
    return root


def test_source_checkout_keeps_data_inside_repo(tmp_path: Path) -> None:
    repo = _fake_checkout(tmp_path / "GEN AI" / "Evra")
    assert is_source_checkout(repo)
    paths = resolve_paths(repo_root=repo)
    assert paths == AppPaths.under(repo / ".data")
    assert paths.db_path == repo / ".data" / "data" / "evra.db"


def test_installed_build_uses_user_dirs(tmp_path: Path) -> None:
    not_a_repo = tmp_path / "site-packages"
    not_a_repo.mkdir()
    assert not is_source_checkout(not_a_repo)
    assert resolve_paths(repo_root=not_a_repo) == AppPaths.for_user()


def test_explicit_data_dir_wins(tmp_path: Path) -> None:
    repo = _fake_checkout(tmp_path / "repo")
    assert resolve_paths(tmp_path / "custom", repo_root=repo) == AppPaths.under(tmp_path / "custom")


def test_real_repo_is_detected_as_checkout() -> None:
    assert is_source_checkout(REPO_ROOT)
    assert (REPO_ROOT / "BUILD.md").exists()


def test_spill_dir_is_under_data(tmp_path: Path) -> None:
    assert AppPaths.under(tmp_path).spill_dir == tmp_path / "data" / "spill"

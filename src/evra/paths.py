"""Where Evra keeps its files (BUILD.md §4.5, §8.2, D23)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import platformdirs

from evra.constants import APP_NAME


@dataclass(frozen=True)
class AppPaths:
    data_dir: Path
    config_dir: Path
    log_dir: Path

    @property
    def models_dir(self) -> Path:
        return self.data_dir / "models"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "evra.db"

    @property
    def spill_dir(self) -> Path:
        return self.data_dir / "spill"

    @property
    def settings_file(self) -> Path:
        return self.config_dir / "settings.toml"

    @classmethod
    def for_user(cls) -> AppPaths:
        return cls(
            data_dir=Path(platformdirs.user_data_dir(APP_NAME, appauthor=False)),
            config_dir=Path(platformdirs.user_config_dir(APP_NAME, appauthor=False)),
            log_dir=Path(platformdirs.user_log_dir(APP_NAME, appauthor=False)),
        )

    @classmethod
    def under(cls, root: Path) -> AppPaths:
        """All paths below one root — for tests and portable runs."""
        return cls(data_dir=root / "data", config_dir=root / "config", log_dir=root / "logs")

    def ensure(self) -> None:
        for directory in (self.data_dir, self.config_dir, self.log_dir, self.models_dir):
            directory.mkdir(parents=True, exist_ok=True)


# src/evra/paths.py -> parents[2] is the repository root in a source checkout.
REPO_ROOT = Path(__file__).resolve().parents[2]


def is_source_checkout(repo_root: Path = REPO_ROOT) -> bool:
    return (repo_root / "pyproject.toml").is_file() and (repo_root / ".git").exists()


def resolve_paths(data_dir: Path | None = None, *, repo_root: Path = REPO_ROOT) -> AppPaths:
    """Explicit dir > `<repo>/.data` when running from source > per-user OS dirs."""
    if data_dir is not None:
        return AppPaths.under(data_dir)
    if is_source_checkout(repo_root):
        return AppPaths.under(repo_root / ".data")
    return AppPaths.for_user()

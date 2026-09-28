"""Model catalogue (models.yaml) and first-use downloads (BUILD.md §4.5).

Downloads resume, every file is checked against its SHA-256, and only the listed files are
taken out of an archive. A `.verified` marker records a model that passed its checks.
"""

from __future__ import annotations

import hashlib
import shutil
import tarfile
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import yaml

from evra.paths import REPO_ROOT

CATALOG = REPO_ROOT / "models.yaml"
MARKER = ".verified"
Fetcher = Callable[[str, Path], None]


class ModelError(RuntimeError):
    pass


@dataclass(frozen=True)
class ModelFile:
    name: str
    sha256: str


@dataclass(frozen=True)
class ModelSpec:
    id: str
    url: str
    archive: str | None
    licence: str
    files: tuple[ModelFile, ...]
    size_mb: int
    attribution: str

    def directory(self, models_dir: Path) -> Path:
        return models_dir / self.id


def load_catalog(path: Path = CATALOG) -> dict[str, ModelSpec]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    specs: dict[str, ModelSpec] = {}
    for m in raw.get("models") or []:
        source = m["source"]
        specs[m["id"]] = ModelSpec(
            id=m["id"],
            url=source["url"],
            archive=source.get("archive"),
            licence=m["licence"],
            files=tuple(ModelFile(f["name"], f["sha256"]) for f in m["files"]),
            size_mb=int(m.get("size_mb", 0)),
            attribution=m.get("attribution", ""),
        )
    return specs


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def is_ready(spec: ModelSpec, models_dir: Path) -> bool:
    target = spec.directory(models_dir)
    return (target / MARKER).is_file() and all((target / f.name).is_file() for f in spec.files)


def http_fetch(url: str, dest: Path) -> None:
    """Download `url` to `dest`, continuing a partial `.part` file with an HTTP Range request."""
    part = dest.with_name(dest.name + ".part")
    have = part.stat().st_size if part.exists() else 0
    headers = {"Range": f"bytes={have}-"} if have else {}
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=60) as response:
        mode = "ab" if have and response.status == 206 else "wb"
        with part.open(mode) as out:
            shutil.copyfileobj(response, out, 1 << 20)
    part.replace(dest)


def _verify(spec: ModelSpec, target: Path) -> bool:
    return all(
        (target / f.name).is_file() and sha256_of(target / f.name) == f.sha256 for f in spec.files
    )


def _extract(archive: Path, spec: ModelSpec, target: Path) -> None:
    wanted = {f.name for f in spec.files}
    with tarfile.open(archive, mode="r:bz2") as tar:
        for member in tar.getmembers():
            name = Path(member.name).name
            if member.isfile() and name in wanted:
                source = tar.extractfile(member)
                if source is None:
                    continue
                with source, (target / name).open("wb") as out:
                    shutil.copyfileobj(source, out, 1 << 20)


def ensure_model(spec: ModelSpec, models_dir: Path, fetch: Fetcher = http_fetch) -> Path:
    """Make sure the model is on disk and verified; download it if needed."""
    target = spec.directory(models_dir)
    if is_ready(spec, models_dir):
        return target
    target.mkdir(parents=True, exist_ok=True)
    if not _verify(spec, target):
        if spec.archive == "tar.bz2":
            archive = models_dir / f"{spec.id}.download"
            fetch(spec.url, archive)
            try:
                _extract(archive, spec, target)
            finally:
                archive.unlink(missing_ok=True)
        elif spec.archive is None:
            fetch(spec.url, target / spec.files[0].name)
        else:
            raise ModelError(f"{spec.id}: unsupported archive type {spec.archive!r}")
        for f in spec.files:
            path = target / f.name
            if not path.is_file() or sha256_of(path) != f.sha256:
                path.unlink(missing_ok=True)
                raise ModelError(f"{spec.id}: {f.name} failed its checksum")
    (target / MARKER).write_text("ok\n", encoding="utf-8")
    return target

import hashlib
import io
import tarfile
from pathlib import Path

import pytest

from evra import modelstore
from evra.modelstore import (
    CATALOG,
    ModelError,
    ModelFile,
    ModelSpec,
    ensure_model,
    http_fetch,
    is_ready,
    load_catalog,
)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _archive(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:bz2") as tar:
        for name, data in {**files, "model-dir/test_wavs/x.wav": b"skip me"}.items():
            info = tarfile.TarInfo(name if "/" in name else f"model-dir/{name}")
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def _spec(files: dict[str, bytes], archive: str | None) -> ModelSpec:
    return ModelSpec(
        id="m",
        url="https://example/m",
        archive=archive,
        licence="MIT",
        files=tuple(ModelFile(n, _sha(d)) for n, d in files.items()),
        size_mb=1,
        attribution="",
    )


def test_real_catalogue_parses() -> None:
    catalogue = load_catalog(CATALOG)
    assert {"silero-vad", "parakeet-tdt-0.6b-v3-int8"} <= catalogue.keys()
    assert catalogue["parakeet-tdt-0.6b-v3-int8"].archive == "tar.bz2"


def test_archive_is_downloaded_extracted_verified_and_marked(tmp_path: Path) -> None:
    files = {"a.onnx": b"AAA", "tokens.txt": b"t"}
    calls: list[str] = []

    def fetch(url: str, dest: Path) -> None:
        calls.append(url)
        dest.write_bytes(_archive(files))

    spec = _spec(files, "tar.bz2")
    target = ensure_model(spec, tmp_path, fetch)
    assert (target / "a.onnx").read_bytes() == b"AAA"
    assert not (target / "x.wav").exists()  # only listed files are extracted
    assert is_ready(spec, tmp_path)
    assert not list(tmp_path.glob("*.download"))
    ensure_model(spec, tmp_path, fetch)
    assert len(calls) == 1  # second call: nothing to do


def test_single_file_model(tmp_path: Path) -> None:
    spec = _spec({"vad.onnx": b"VAD"}, None)
    target = ensure_model(spec, tmp_path, lambda url, dest: dest.write_bytes(b"VAD"))
    assert (target / "vad.onnx").read_bytes() == b"VAD"


def test_existing_correct_files_are_adopted_without_download(tmp_path: Path) -> None:
    spec = _spec({"vad.onnx": b"VAD"}, None)
    (tmp_path / "m").mkdir()
    (tmp_path / "m" / "vad.onnx").write_bytes(b"VAD")

    def no_fetch(url: str, dest: Path) -> None:
        raise AssertionError("should not download")

    ensure_model(spec, tmp_path, no_fetch)
    assert is_ready(spec, tmp_path)


def test_checksum_mismatch_is_fatal_and_removes_the_file(tmp_path: Path) -> None:
    spec = _spec({"vad.onnx": b"VAD"}, None)
    with pytest.raises(ModelError, match="checksum"):
        ensure_model(spec, tmp_path, lambda url, dest: dest.write_bytes(b"EVIL"))
    assert not (tmp_path / "m" / "vad.onnx").exists()
    assert not is_ready(spec, tmp_path)


def test_http_fetch_resumes_a_partial_download(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dest = tmp_path / "file.bin"
    (tmp_path / "file.bin.part").write_bytes(b"hello ")
    seen: dict[str, str] = {}

    class FakeResponse(io.BytesIO):
        status = 206

        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, *args: object) -> None: ...

    def fake_urlopen(request: object, timeout: float) -> FakeResponse:
        seen["range"] = request.get_header("Range")  # type: ignore[attr-defined]
        return FakeResponse(b"world")

    monkeypatch.setattr(modelstore.urllib.request, "urlopen", fake_urlopen)
    http_fetch("https://example/file", dest)
    assert seen["range"] == "bytes=6-"
    assert dest.read_bytes() == b"hello world"

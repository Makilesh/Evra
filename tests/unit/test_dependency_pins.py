"""Dependency pins that protect against known breakage."""

from __future__ import annotations

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_sherpa_onnx_is_pinned_to_the_same_version_as_its_dlls() -> None:
    # sherpa-onnx-core carries the onnxruntime DLLs; a mismatch loads System32's copy and crashes.
    deps = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"][
        "dependencies"
    ]
    pins = {d.split("==")[0].strip(): d.split("==")[1].strip() for d in deps if "==" in d}
    assert "sherpa-onnx" in pins, "sherpa-onnx must be pinned with =="
    assert pins["sherpa-onnx"] == pins["sherpa-onnx-core"]

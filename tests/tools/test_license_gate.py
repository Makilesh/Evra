import json
from pathlib import Path

import pytest

from tools.license_gate import (
    Component,
    Policy,
    evaluate,
    licence_ok,
    model_components,
    npm_components,
    python_components,
    render_register,
)

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def policy() -> Policy:
    return Policy.load(ROOT / "tools" / "license_policy.yaml")


def _c(licence: str, *, runtime: bool = True, name: str = "pkg") -> Component:
    return Component(kind="python", name=name, version="1.0", licence=licence, runtime=runtime)


@pytest.mark.parametrize(
    ("expr", "ok"),
    [
        ("MIT", True),
        ("MIT License", True),
        ("Apache Software License; BSD License", True),
        ("MIT OR GPL-3.0-only", True),
        ("MIT AND GPL-3.0-only", False),
        ("GPL-3.0-only", False),
        ("AGPL-3.0", False),
        ("CC-BY-NC-4.0", False),
        ("UNKNOWN", False),
        ("", False),
        ("(MIT OR Apache-2.0)", True),
    ],
)
def test_licence_expressions(policy: Policy, expr: str, ok: bool) -> None:
    assert licence_ok(expr, policy.allowed_runtime, policy.aliases) is ok


def test_mpl_is_dev_only(policy: Policy) -> None:
    assert evaluate(_c("MPL-2.0", runtime=False), policy) is None
    reason = evaluate(_c("MPL-2.0", runtime=True), policy)
    assert reason is not None and "runtime" in reason


def test_lgpl_only_for_listed_packages(policy: Policy) -> None:
    listed = Policy(
        allowed_runtime=policy.allowed_runtime,
        allowed_dev_extra=policy.allowed_dev_extra,
        lgpl_allowed={"pyside6": "dynamically linked Qt"},
        aliases=policy.aliases,
        overrides=policy.overrides,
    )
    assert evaluate(_c("LGPL-3.0-only", name="pyside6"), listed) is None
    assert evaluate(_c("LGPL-3.0-only", name="other"), listed) is not None


def test_override_replaces_metadata(policy: Policy) -> None:
    overridden = Policy(
        allowed_runtime=policy.allowed_runtime,
        allowed_dev_extra=policy.allowed_dev_extra,
        lgpl_allowed=policy.lgpl_allowed,
        aliases=policy.aliases,
        overrides={"python": {"weird": {"licence": "MIT", "source": "https://x"}}, "npm": {}},
    )
    assert evaluate(_c("UNKNOWN", name="weird"), overridden) is None


def test_python_components_marks_runtime() -> None:
    data = json.dumps(
        [
            {"Name": "Pydantic", "Version": "2.0", "License": "MIT"},
            {"Name": "pytest", "Version": "9.0", "License": "MIT License"},
        ]
    )
    comps = {c.name: c for c in python_components(data, runtime_names={"pydantic"})}
    assert comps["pydantic"].runtime is True
    assert comps["pytest"].runtime is False


def test_npm_components_from_lockfile() -> None:
    lock = {
        "packages": {
            "": {"name": "evra-frontend"},
            "node_modules/react": {"version": "19.3.0", "license": "MIT"},
            "node_modules/vitest": {"version": "5.0.1", "license": "MIT", "dev": True},
            "node_modules/@scope/pkg": {"version": "1.0.0"},
        }
    }
    comps = {c.name: c for c in npm_components(lock)}
    assert comps["react"].runtime is True
    assert comps["vitest"].runtime is False
    assert comps["@scope/pkg"].licence == ""


def test_model_components_and_register() -> None:
    catalogue = {
        "models": [
            {
                "id": "vad",
                "source": {"type": "url", "url": "https://example"},
                "licence": "MIT",
                "files": [],
                "size_mb": 2,
                "loaded": "during_meeting",
                "attribution": "Silero VAD (MIT).",
            }
        ]
    }
    [model] = model_components(catalogue)
    assert model.kind == "model" and model.runtime is True
    register = render_register([model, _c("MIT", name="pydantic")])
    assert "Silero VAD (MIT)." in register
    assert "| pydantic | 1.0 | MIT |" in register


def test_register_shows_overridden_licence(policy: Policy) -> None:
    overridden = Policy(
        allowed_runtime=policy.allowed_runtime,
        allowed_dev_extra=policy.allowed_dev_extra,
        lgpl_allowed=policy.lgpl_allowed,
        aliases=policy.aliases,
        overrides={"python": {"weird": {"licence": "MIT", "source": "https://x"}}, "npm": {}},
    )
    register = render_register([_c("UNKNOWN", name="weird")], overridden)
    assert "| weird | 1.0 | MIT |" in register
    assert "UNKNOWN" not in register

"""User settings persisted as TOML (BUILD.md §5.5, §6.2, §8.1)."""

from __future__ import annotations

import os
import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Literal

import structlog
import tomli_w
from pydantic import BaseModel, ConfigDict, Field, ValidationError

log = structlog.get_logger(__name__)

Mode = Literal["one_on_one", "meeting"]
Situation = Literal["call_headphones", "call_speakers", "in_person", "hybrid"]
Retention = Literal["7d", "30d", "90d", "forever"]
Theme = Literal["system", "light", "dark"]


class LlmSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    provider: Literal["ollama"] = "ollama"
    model: str = ""  # chosen by the M3 bake-off (BUILD.md D4)
    ollama_url: str = "http://127.0.0.1:11434"


class Settings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    default_mode: Mode = "one_on_one"
    default_situation: Situation = "call_headphones"
    live_transcript: bool = True
    audio_retention: Retention = "30d"
    theme: Theme = "system"
    llm: LlmSettings = Field(default_factory=LlmSettings)


def load_settings(path: Path) -> Settings:
    """Load settings; a corrupt or invalid file is moved aside and defaults are used."""
    if not path.exists():
        return Settings()
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        return Settings.model_validate(data)
    except (tomllib.TOMLDecodeError, ValidationError, UnicodeDecodeError):
        backup = path.with_suffix(".toml.bad")
        path.replace(backup)
        log.warning("settings_invalid_reset", backup=str(backup))
        return Settings()


def save_settings(path: Path, settings: Settings) -> None:
    """Write atomically: temp file, then replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".toml.tmp")
    tmp.write_text(tomli_w.dumps(settings.model_dump()), encoding="utf-8")
    tmp.replace(path)


def debug_enabled(environ: Mapping[str, str] | None = None) -> bool:
    """EVRA_DEBUG=1 is the only environment variable Evra reads."""
    env = os.environ if environ is None else environ
    return env.get("EVRA_DEBUG", "") == "1"

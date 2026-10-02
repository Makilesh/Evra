"""Microphones by name (M3c, BUILD.md §5.1).

Windows lists each microphone once per host API (MME, DirectSound, WASAPI, WDM-KS), so a bare
name is ambiguous to sounddevice ("Multiple input devices found"), and MME cuts names at 31
characters. Evra lists the mics of the default input's host API — the one `MicSource(None)`
records from — shows each with its full name when another host API has it, and resolves a
stored name back to that host API's device index.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from evra.capture.sources import MicUnavailableError

MME_NAME_LIMIT = 31
PSEUDO_DEVICES = frozenset({"Microsoft Sound Mapper - Input", "Primary Sound Capture Driver"})
PICK_AGAIN = "Pick the microphone again in Evra, or check that it is connected and turned on."


@dataclass(frozen=True)
class MicList:
    default: str
    mics: tuple[str, ...]


def _sounddevice() -> Any:
    import sounddevice

    return sounddevice


def _full_name(name: str, names: list[str]) -> str:
    if len(name) != MME_NAME_LIMIT:
        return name
    longer = [n for n in names if len(n) > len(name) and n.startswith(name)]
    return min(longer, key=len) if longer else name


def _entries(sd: Any) -> tuple[list[tuple[int, str]], str]:
    """(device index, display name) of each mic on the default input's host API, and the
    default mic's display name."""
    try:
        default = sd.query_devices(kind="input")
    except Exception:  # no input device at all (sounddevice raises ValueError/PortAudioError)
        return [], ""
    devices = list(sd.query_devices())
    names = [str(d["name"]) for d in devices if d["max_input_channels"] > 0]
    entries = [
        (index, _full_name(str(d["name"]), names))
        for index, d in enumerate(devices)
        if d["hostapi"] == default["hostapi"]
        and d["max_input_channels"] > 0
        and str(d["name"]) not in PSEUDO_DEVICES
    ]
    return entries, _full_name(str(default["name"]), names)


def list_mics(backend: Any = None) -> MicList:
    entries, default = _entries(backend or _sounddevice())
    return MicList(default, tuple(dict.fromkeys(name for _, name in entries)))


def resolve_mic(name: str, backend: Any = None) -> int | None:
    """Device index for a mic name from `list_mics` (or a unique part of one); None = default."""
    wanted = " ".join(name.split()).lower()
    if not wanted:
        return None
    entries, _ = _entries(backend or _sounddevice())
    exact = [index for index, full in entries if full.lower() == wanted]
    if exact:
        return exact[0]
    partial = [index for index, full in entries if wanted in full.lower()]
    if len(partial) == 1:
        return partial[0]
    if partial:
        raise MicUnavailableError(f"several microphones match {name!r}", PICK_AGAIN)
    raise MicUnavailableError(f"microphone {name!r} is not connected", PICK_AGAIN)

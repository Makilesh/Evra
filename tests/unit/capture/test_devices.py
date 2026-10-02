from typing import Any

import pytest

from evra.capture.devices import MicList, list_mics, resolve_mic
from evra.capture.sources import MicUnavailableError

APIS = [{"name": "MME"}, {"name": "Windows DirectSound"}, {"name": "Windows WASAPI"}]
DEVICES: list[dict[str, Any]] = [
    {"name": "Microsoft Sound Mapper - Input", "hostapi": 0, "max_input_channels": 2},
    {"name": "Headset (realme Buds Air7)", "hostapi": 0, "max_input_channels": 1},
    {"name": "Microphone Array (Realtek(R) Au", "hostapi": 0, "max_input_channels": 2},
    {"name": "Speakers (Realtek(R) Audio)", "hostapi": 0, "max_input_channels": 0},
    {"name": "Primary Sound Capture Driver", "hostapi": 1, "max_input_channels": 2},
    {"name": "Headset (realme Buds Air7)", "hostapi": 1, "max_input_channels": 1},
    {"name": "Microphone Array (Realtek(R) Audio)", "hostapi": 1, "max_input_channels": 2},
    {"name": "Microphone Array (Realtek(R) Audio)", "hostapi": 2, "max_input_channels": 2},
]


class FakeSd:
    """sounddevice's query API, shaped like the dev machine (spikes/mic_names.py)."""

    def __init__(self, devices: list[dict[str, Any]] = DEVICES, default: int | None = 1) -> None:
        self.devices, self.default = devices, default

    def query_devices(self, device: int | None = None, kind: str | None = None) -> Any:
        if device is None and kind == "input":
            if self.default is None:
                raise ValueError("No input device matching")
            return self.devices[self.default]
        if device is None:
            return self.devices
        return self.devices[device]

    def query_hostapis(self) -> list[dict[str, str]]:
        return APIS


def test_mics_of_the_default_host_api_with_full_names() -> None:
    assert list_mics(FakeSd()) == MicList(
        default="Headset (realme Buds Air7)",
        mics=("Headset (realme Buds Air7)", "Microphone Array (Realtek(R) Audio)"),
    )


def test_no_input_device_at_all_lists_nothing() -> None:
    assert list_mics(FakeSd(default=None)) == MicList("", ())


def test_resolve_by_full_name_case_insensitively_or_a_unique_part() -> None:
    sd = FakeSd()
    assert resolve_mic("Microphone Array (Realtek(R) Audio)", sd) == 2
    assert resolve_mic("headset (realme buds air7)", sd) == 1
    assert resolve_mic("realtek", sd) == 2


def test_an_empty_name_means_the_windows_default() -> None:
    assert resolve_mic("", FakeSd()) is None
    assert resolve_mic("   ", FakeSd()) is None


def test_a_mic_that_is_gone_says_how_to_fix_it() -> None:
    with pytest.raises(MicUnavailableError) as caught:
        resolve_mic("Headset (Mivi Roam 2)", FakeSd())
    assert "not connected" in str(caught.value)
    assert caught.value.hint


def test_a_name_matching_several_mics_is_refused() -> None:
    devices = [
        {"name": "USB Mic A", "hostapi": 0, "max_input_channels": 1},
        {"name": "USB Mic B", "hostapi": 0, "max_input_channels": 1},
    ]
    with pytest.raises(MicUnavailableError, match="several"):
        resolve_mic("usb mic", FakeSd(devices, default=0))

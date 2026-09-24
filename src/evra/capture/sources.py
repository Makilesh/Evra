"""What a capture source must provide (BUILD.md §5.1), and the errors users can act on."""

from __future__ import annotations

from typing import Protocol

from evra.audio.ringbuffer import ChunkRing

MIC_PRIVACY_HINT = (
    "Check Windows Settings > Privacy & security > Microphone "
    "(ms-settings:privacy-microphone) and allow desktop apps to use the microphone."
)
NO_OUTPUT_HINT = "Connect speakers or headphones and make them the default output device."
DEVICE_BUSY_HINT = (
    "Another app may be using the output device exclusively: close it, or turn off "
    "exclusive mode in Sound settings > device properties > Advanced, then retry."
)


class CaptureError(RuntimeError):
    def __init__(self, message: str, hint: str = "") -> None:
        super().__init__(message)
        self.hint = hint


class MicUnavailableError(CaptureError):
    pass


class LoopbackUnavailableError(CaptureError):
    pass


class AudioSource(Protocol):
    name: str
    ring: ChunkRing
    native_rate: int
    native_channels: int
    latency_ns: int
    pads_silence: bool
    overflows: int  # times the device reported lost input (overrun)

    def start(self) -> None: ...

    def stop(self) -> None: ...

    def reopen(self) -> None: ...

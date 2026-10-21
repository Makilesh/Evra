"""The meeting timeline format (BUILD.md §5.1): 16 kHz mono int16 in 10 ms frames."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

import numpy as np
import numpy.typing as npt

SAMPLE_RATE: Final = 16_000
FRAME_MS: Final = 10
FRAME_SAMPLES: Final = SAMPLE_RATE * FRAME_MS // 1000
NS: Final = 1_000_000_000
MIC: Final = 0
SYSTEM: Final = 1
Channel = Literal[0, 1]
Int16Array = npt.NDArray[np.int16]
Float32Array = npt.NDArray[np.float32]


@dataclass(frozen=True)
class Frames:
    channel: Channel
    pcm: Int16Array  # FRAME_SAMPLES samples
    t_capture_ns: int  # monotonic time of pcm[0]
    index: int  # sample index of pcm[0] on the meeting timeline

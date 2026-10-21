"""Speaker labels before diarization. In 1:1 mode (D18) the mic is the owner and the system
audio is the other person."""

from __future__ import annotations

LABELS = {0: "You", 1: "Them"}
PARTICIPANTS_1ON1 = "You (the owner of this note), Them (the other person on the call)"


def speaker_label(channel: int) -> str:
    return LABELS.get(channel, f"Channel {channel}")

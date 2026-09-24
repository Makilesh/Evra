from pathlib import Path

import numpy as np
import pytest

from evra.audio.frames import MIC, SYSTEM, Frames
from evra.audio.keys import new_meeting_key
from evra.audio.spill import SpillError, SpillWriter, read_channel, read_segment


def _frames(channel: int, count: int, start: int = 0) -> list[Frames]:
    out = []
    for k in range(count):
        pcm = np.full(160, (k % 100) + 1, dtype=np.int16)
        index = (start + k) * 160
        out.append(Frames(channel, pcm, index * 62_500, index))  # type: ignore[arg-type]
    return out


def test_round_trip_both_channels_across_segments(tmp_path: Path) -> None:
    key = new_meeting_key()
    writer = SpillWriter(tmp_path, "m1", key, segment_samples=16_000)  # 1 s segments
    frames = _frames(MIC, 250) + _frames(SYSTEM, 130)
    for f in frames:
        writer.write(f)
    segments = writer.close()
    assert [s.channel for s in segments].count(MIC) == 3  # 1 s + 1 s + 0.5 s
    assert segments[0].start_ms == 0 and segments[0].end_ms == 1000
    mic = read_channel(tmp_path, key, MIC)
    expected = np.concatenate([f.pcm for f in frames if f.channel == MIC])
    np.testing.assert_array_equal(mic, expected)
    assert len(read_channel(tmp_path, key, SYSTEM)) == 130 * 160


def test_no_plaintext_on_disk(tmp_path: Path) -> None:
    writer = SpillWriter(tmp_path, "m1", new_meeting_key(), segment_samples=1_600)
    marker = np.frombuffer(b"EVRAPLAINTEXT!!!" * 20, dtype=np.int16)
    writer.write(Frames(MIC, marker, 0, 0))
    [seg] = writer.close()
    assert b"EVRAPLAINTEXT" not in seg.path.read_bytes()


def test_tampered_segment_fails(tmp_path: Path) -> None:
    key = new_meeting_key()
    writer = SpillWriter(tmp_path, "m1", key)
    for f in _frames(MIC, 10):
        writer.write(f)
    [seg] = writer.close()
    raw = bytearray(seg.path.read_bytes())
    raw[-5] ^= 0xFF
    seg.path.write_bytes(bytes(raw))
    with pytest.raises(SpillError, match="authentication"):
        read_segment(seg.path, key)


def test_wrong_key_fails(tmp_path: Path) -> None:
    writer = SpillWriter(tmp_path, "m1", new_meeting_key())
    writer.write(_frames(MIC, 1)[0])
    [seg] = writer.close()
    with pytest.raises(SpillError):
        read_segment(seg.path, new_meeting_key())


def test_not_a_spill_file(tmp_path: Path) -> None:
    bad = tmp_path / "0_00000.spill"
    bad.write_bytes(b"hello")
    with pytest.raises(SpillError, match="not a spill file"):
        read_segment(bad, new_meeting_key())


def test_header_is_authenticated_metadata(tmp_path: Path) -> None:
    key = new_meeting_key()
    writer = SpillWriter(tmp_path, "m-42", key)
    for f in _frames(SYSTEM, 3, start=10):
        writer.write(f)
    [seg] = writer.close()
    header, pcm = read_segment(seg.path, key)
    assert header["meeting_id"] == "m-42" and header["channel"] == SYSTEM
    assert header["start_ms"] == 100 and len(pcm) == 480
    assert not list(tmp_path.glob("*.tmp"))

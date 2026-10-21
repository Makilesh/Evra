import numpy as np
import numpy.typing as npt
import pytest

from evra.audio.convert import ToMono16k, float_to_int16


def _sine(
    rate: int, seconds: float, channels: int = 1, freq: float = 440.0
) -> npt.NDArray[np.float32]:
    t = np.arange(int(rate * seconds)) / rate
    mono = (0.5 * np.sin(2 * np.pi * freq * t)).astype(np.float32)
    return np.repeat(mono[:, None], channels, axis=1)


def _peak_hz(x: npt.NDArray[np.int16], rate: int) -> float:
    spectrum = np.abs(np.fft.rfft(x.astype(np.float64)))
    return float(np.fft.rfftfreq(len(x), 1 / rate)[int(np.argmax(spectrum))])


def _stream(conv: ToMono16k, audio: npt.NDArray[np.float32], block: int) -> npt.NDArray[np.int16]:
    return np.concatenate([conv.process(audio[i : i + block]) for i in range(0, len(audio), block)])


def test_48k_stereo_in_10ms_chunks_becomes_16k_mono() -> None:
    out = _stream(ToMono16k(48_000, 2), _sine(48_000, 2.0, channels=2), 480)
    assert out.dtype == np.int16
    assert abs(len(out) - 32_000) < 200
    assert abs(_peak_hz(out[2000:], 16_000) - 440) < 5


def test_44k1_mono_rational_ratio() -> None:
    out = _stream(ToMono16k(44_100, 1), _sine(44_100, 2.0), 441)
    assert abs(len(out) - 32_000) < 200
    assert abs(_peak_hz(out[2000:], 16_000) - 440) < 5


def test_chunk_size_does_not_change_the_output() -> None:
    audio = _sine(48_000, 1.0, channels=2)
    a = _stream(ToMono16k(48_000, 2), audio, 480)
    b = _stream(ToMono16k(48_000, 2), audio, 1_111)
    n = min(len(a), len(b)) - 200
    assert np.max(np.abs(a[:n].astype(np.int32) - b[:n])) <= 2


def test_16k_mono_passes_through_exactly() -> None:
    audio = _sine(16_000, 0.1)
    np.testing.assert_array_equal(ToMono16k(16_000, 1).process(audio), float_to_int16(audio[:, 0]))


def test_downmix_averages_channels() -> None:
    chunk = np.array([[0.5, -0.5], [1.0, 0.0]], dtype=np.float32)
    np.testing.assert_array_equal(ToMono16k(16_000, 2).process(chunk), [0, 16384])


def test_clipping_and_rounding() -> None:
    np.testing.assert_array_equal(
        float_to_int16(np.array([2.0, -2.0, 0.5], dtype=np.float32)), [32767, -32767, 16384]
    )


def test_empty_chunk_gives_empty_output() -> None:
    assert len(ToMono16k(48_000, 2).process(np.zeros((0, 2), dtype=np.float32))) == 0


def test_wrong_channel_count_rejected() -> None:
    with pytest.raises(ValueError, match="channels"):
        ToMono16k(48_000, 2).process(np.zeros((10, 1), dtype=np.float32))

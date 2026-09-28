import wave

import numpy as np

from evra.asr.parakeet import PARAKEET_ID
from evra.audio.convert import ToMono16k
from evra.paths import REPO_ROOT, resolve_paths
from evra.workers.asr import AsrClient
from evra.workers.supervisor import Worker
from tests.conftest import requires_models


def test_client_sends_pcm_and_rebuilds_segments() -> None:
    client = AsrClient(Worker("asr-test", "tests.unit.workers.fake_handlers:fake_asr"))
    try:
        client.warm_up()
        [seg] = client.transcribe(np.zeros(16_000, dtype=np.int16))
        assert seg.text == "hello there" and seg.end_ms == 1000
        assert [w.text for w in seg.words] == ["hello", "there"]
    finally:
        client.stop()


@requires_models(PARAKEET_ID)
def test_real_parakeet_in_a_worker_process() -> None:
    with wave.open(str(REPO_ROOT / "spikes" / "test_wavs" / "en.wav")) as w:
        rate = w.getframerate()
        pcm = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2")
    audio = ToMono16k(rate, 1).process((pcm / 32768.0).astype(np.float32))
    client = AsrClient.for_models(resolve_paths().models_dir)
    try:
        [seg] = client.transcribe(audio, timeout_s=120)
        assert "country" in seg.text.lower()
    finally:
        client.stop()

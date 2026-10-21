import time

import pytest

from evra.audio.keys import KeyringKeyStore, new_meeting_key

pytestmark = pytest.mark.hardware


def test_real_microphone_delivers_chunks() -> None:
    from evra.capture.mic import MicSource

    mic = MicSource()
    mic.start()
    time.sleep(1.0)
    mic.stop()
    assert len(mic.ring.drain()) > 20


def test_real_loopback_opens() -> None:
    from evra.capture.windows import LoopbackSource

    src = LoopbackSource()
    src.start()
    time.sleep(1.0)
    src.stop()
    assert src.native_rate > 0 and src.native_channels > 0


def test_default_output_id_is_available() -> None:
    from evra.capture.windows import default_output_id

    assert default_output_id()


def test_credential_manager_round_trip() -> None:
    store = KeyringKeyStore(service="Evra-test")
    key = new_meeting_key()
    store.set("hw", key)
    try:
        assert store.get("hw") == key
    finally:
        store.delete("hw")
    assert store.get("hw") is None

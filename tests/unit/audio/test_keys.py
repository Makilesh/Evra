from collections.abc import Iterator

import keyring
import keyring.backend
import keyring.errors
import pytest

from evra.audio.keys import KeyringKeyStore, MemoryKeyStore, new_meeting_key


class _DictKeyring(keyring.backend.KeyringBackend):
    priority = 1  # type: ignore[assignment]

    def __init__(self) -> None:
        super().__init__()
        self.store: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        return self.store.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self.store[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        if (service, username) not in self.store:
            raise keyring.errors.PasswordDeleteError("missing")
        del self.store[(service, username)]


@pytest.fixture
def fake_keyring() -> Iterator[_DictKeyring]:
    previous = keyring.get_keyring()
    fake = _DictKeyring()
    keyring.set_keyring(fake)
    yield fake
    keyring.set_keyring(previous)


def test_new_key_is_256_bit_and_random() -> None:
    a, b = new_meeting_key(), new_meeting_key()
    assert len(a) == 32 and a != b


def test_keyring_store_round_trip_under_evra_meeting_id(fake_keyring: _DictKeyring) -> None:
    store = KeyringKeyStore()
    key = new_meeting_key()
    store.set("m1", key)
    assert ("Evra", "meeting/m1") in fake_keyring.store
    assert store.get("m1") == key
    store.delete("m1")
    assert store.get("m1") is None
    store.delete("m1")  # deleting twice is fine


def test_memory_store() -> None:
    store = MemoryKeyStore()
    store.set("m", b"k" * 32)
    assert store.get("m") == b"k" * 32
    store.delete("m")
    assert store.get("m") is None

"""Per-meeting spill keys in the OS credential store (BUILD.md §5.5)."""

from __future__ import annotations

import base64
import contextlib
from typing import Protocol

import keyring
import keyring.errors
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from evra.constants import APP_NAME


def new_meeting_key() -> bytes:
    return AESGCM.generate_key(bit_length=256)


class KeyStore(Protocol):
    def get(self, meeting_id: str) -> bytes | None: ...

    def set(self, meeting_id: str, key: bytes) -> None: ...

    def delete(self, meeting_id: str) -> None: ...


class KeyringKeyStore:
    """Windows Credential Manager via keyring: service "Evra", username "meeting/<id>"."""

    def __init__(self, service: str = APP_NAME) -> None:
        self._service = service

    @staticmethod
    def _user(meeting_id: str) -> str:
        return f"meeting/{meeting_id}"

    def get(self, meeting_id: str) -> bytes | None:
        value = keyring.get_password(self._service, self._user(meeting_id))
        return base64.b64decode(value) if value else None

    def set(self, meeting_id: str, key: bytes) -> None:
        encoded = base64.b64encode(key).decode("ascii")
        keyring.set_password(self._service, self._user(meeting_id), encoded)

    def delete(self, meeting_id: str) -> None:
        with contextlib.suppress(keyring.errors.PasswordDeleteError):
            keyring.delete_password(self._service, self._user(meeting_id))


class MemoryKeyStore:
    def __init__(self) -> None:
        self._keys: dict[str, bytes] = {}

    def get(self, meeting_id: str) -> bytes | None:
        return self._keys.get(meeting_id)

    def set(self, meeting_id: str, key: bytes) -> None:
        self._keys[meeting_id] = key

    def delete(self, meeting_id: str) -> None:
        self._keys.pop(meeting_id, None)

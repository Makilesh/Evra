"""Handler factories that run inside spawned test workers."""

import os
from typing import Any


def echo(**config: Any) -> Any:
    def handle(op: str, payload: Any) -> Any:
        if op == "echo":
            return payload
        if op == "config":
            return config
        if op == "boom":
            raise ValueError("secret content that must not cross the pipe")
        if op == "die":
            os._exit(3)
        if op == "pid":
            return os.getpid()
        raise KeyError(op)

    return handle

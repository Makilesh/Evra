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


def fake_asr(**config: Any) -> Any:
    def handle(op: str, payload: Any) -> Any:
        if op == "ping":
            return "pong"
        samples = len(payload["pcm"]) // 2
        end = samples * 1000 // 16_000
        return [
            {
                "start_ms": 0,
                "end_ms": end,
                "text": "hello there",
                "words": [
                    {"start_ms": 0, "end_ms": end // 2, "text": "hello"},
                    {"start_ms": end // 2, "end_ms": end, "text": "there"},
                ],
            }
        ]

    return handle

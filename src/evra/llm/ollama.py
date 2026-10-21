"""Ollama provider (BUILD.md D4). Evra is a client of a loopback Ollama server; the listener is
Ollama's own.

Ollama's REST API is spoken with the standard library (the `ollama` package's HTTP stack pulls
in an MPL-2.0 dependency). Proxies are never used and redirects are refused, so a transcript
cannot leave the machine. Endpoints and fields were checked against Ollama 0.34.4 and the
official client's source: POST /api/chat, GET /api/tags, GET /api/ps, POST /api/generate.
"""

from __future__ import annotations

import http.client
import ipaddress
import json
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from typing import Any
from urllib.parse import urlsplit

from evra.config import LlmSettings
from evra.llm.provider import (
    ChatMessage,
    ChatResult,
    LlmConfigError,
    LlmError,
    LlmModelMissing,
    LlmTimeout,
    LlmUnavailable,
)


def is_loopback_url(url: str) -> bool:
    try:
        host = urlsplit(url).hostname or ""
    except ValueError:
        return False
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


class _NoRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        return None  # urllib then raises HTTPError for the 3xx


class OllamaHttp:
    """JSON over HTTP to one Ollama server: no proxies, no redirects."""

    def __init__(self, base_url: str, *, timeout_s: float) -> None:
        self._base = base_url.rstrip("/")
        self._timeout = timeout_s
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirects())

    def request(self, method: str, path: str, body: Mapping[str, Any] | None = None) -> Any:
        data = None if body is None else json.dumps(body).encode("utf-8")
        request = urllib.request.Request(
            self._base + path,
            data=data,
            method=method,
            headers={"Content-Type": "application/json"},
        )
        with self.opener.open(request, timeout=self._timeout) as response:
            return json.loads(response.read())


class OllamaProvider:
    name = "ollama"

    def __init__(
        self,
        settings: LlmSettings,
        *,
        http: Any = None,
        clock: Callable[[], float] = time.perf_counter,
    ) -> None:
        if not is_loopback_url(settings.ollama_url):
            raise LlmConfigError(
                "Evra only uses an LLM on this computer: ollama_url must be 127.0.0.1 or localhost"
            )
        self._settings = settings
        self._clock = clock
        self._http: Any = http or OllamaHttp(settings.ollama_url, timeout_s=settings.timeout_s)

    def chat_json(
        self, model: str, messages: Sequence[ChatMessage], schema: Mapping[str, Any]
    ) -> ChatResult:
        s = self._settings
        started = self._clock()
        response = self._call(
            "POST",
            "/api/chat",
            {
                "model": model,
                "messages": [{"role": m.role, "content": m.content} for m in messages],
                "stream": False,
                "format": dict(schema),
                "options": {
                    "num_ctx": s.num_ctx,
                    "temperature": 0,
                    "num_predict": s.max_output_tokens,
                },
                "keep_alive": s.keep_alive,
                "think": s.think,
            },
            model=model,
        )
        message = response.get("message") or {}
        return ChatResult(
            content=str(message.get("content") or ""),
            tokens_in=int(response.get("prompt_eval_count") or 0),
            tokens_out=int(response.get("eval_count") or 0),
            seconds=self._clock() - started,
            truncated=response.get("done_reason") == "length",
        )

    def installed_models(self) -> list[str]:
        listing = self._call("GET", "/api/tags")
        return sorted(str(m["model"]) for m in listing.get("models", []) if m.get("model"))

    def gpu_share(self, model: str) -> float | None:
        """Share of a loaded model held in VRAM (1.0 = fully on the GPU), or None if not loaded."""
        for loaded in self._call("GET", "/api/ps").get("models", []):
            if loaded.get("model") == model and loaded.get("size"):
                return float(loaded.get("size_vram") or 0) / float(loaded["size"])
        return None

    def unload(self, model: str) -> None:
        self._call("POST", "/api/generate", {"model": model, "keep_alive": 0}, model=model)

    def _call(
        self,
        method: str,
        path: str,
        body: Mapping[str, Any] | None = None,
        *,
        model: str | None = None,
    ) -> Any:
        try:
            reply = self._http.request(method, path, body)
        except urllib.error.HTTPError as exc:
            exc.close()
            if exc.code == 404 and model is not None:
                raise LlmModelMissing(model) from None
            raise LlmError(f"Ollama answered HTTP {exc.code}") from None
        except urllib.error.URLError as exc:
            if isinstance(exc.reason, TimeoutError):
                raise self._timeout() from None
            raise LlmUnavailable("Ollama is not running") from None
        except TimeoutError:
            raise self._timeout() from None
        except (OSError, http.client.HTTPException):  # refused, reset, cut-off reply
            raise LlmUnavailable("Ollama is not running") from None
        except ValueError:
            raise LlmError("Ollama sent a reply that is not JSON") from None
        if not isinstance(reply, dict):
            raise LlmError("Ollama sent a reply that is not a JSON object")
        return reply

    def _timeout(self) -> LlmTimeout:
        return LlmTimeout(f"no answer within {self._settings.timeout_s:.0f} s")

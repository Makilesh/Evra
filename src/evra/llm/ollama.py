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
import math
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
    LlmNotLocal,
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


def is_cloud_model_name(name: str) -> bool:
    """Ollama's cloud models carry a `cloud` tag: `gemma4:cloud`, `gemma4:31b-cloud`."""
    _, sep, tag = name.rpartition(":")
    tag = tag.lower()
    return bool(sep) and (tag == "cloud" or tag.endswith("-cloud"))


def _is_remote_entry(entry: Mapping[str, Any]) -> bool:
    return bool(entry.get("remote_host") or entry.get("remote_model"))


def _unit(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vector))
    return [x / norm for x in vector] if norm else vector


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
        self._tags: list[Mapping[str, Any]] | None = None

    def chat_json(
        self, model: str, messages: Sequence[ChatMessage], schema: Mapping[str, Any]
    ) -> ChatResult:
        self._ensure_local(model)
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
            cached_tokens=int(response.get("prompt_eval_cached_count") or 0),
        )

    def embed(self, model: str, texts: Sequence[str]) -> list[list[float]]:
        """One POST /api/embed for all texts. Ollama does not document normalised output, so
        every vector is scaled to unit length here."""
        self._ensure_local(model)
        if not texts:
            return []
        response = self._call(
            "POST",
            "/api/embed",
            {
                "model": model,
                "input": list(texts),
                "truncate": True,
                "keep_alive": self._settings.keep_alive,
            },
            model=model,
        )
        raw = response.get("embeddings")
        if not isinstance(raw, list) or len(raw) != len(texts):
            raise LlmError("Ollama sent a reply without embeddings")
        try:
            vectors = [_unit([float(x) for x in vector]) for vector in raw]
        except (TypeError, ValueError):
            raise LlmError("Ollama sent a reply without embeddings") from None
        # a cosine needs two whole vectors of one size: anything else is Ollama's error here,
        # so the meaning check falls back to the word check instead of crashing
        if not vectors[0] or any(len(v) != len(vectors[0]) for v in vectors):
            raise LlmError("Ollama sent embeddings that are empty or of different sizes")
        return vectors

    def installed_models(self) -> list[str]:
        return sorted(
            str(m["model"])
            for m in self._listing(refresh=True)
            if m.get("model")
            and not is_cloud_model_name(str(m["model"]))
            and not _is_remote_entry(m)
        )

    def _listing(self, *, refresh: bool = False) -> list[Mapping[str, Any]]:
        if self._tags is None or refresh:
            listing = self._call("GET", "/api/tags").get("models", [])
            self._tags = [m for m in listing if isinstance(m, dict)]
        return self._tags

    def _ensure_local(self, model: str) -> None:
        """Refuse a cloud model before any text is sent. The name tells for `:cloud` tags; the
        /api/tags entry (`remote_host`, `remote_model`) tells for the rest. A model that is not
        listed is left to the call, which answers 404."""
        if is_cloud_model_name(model):
            raise LlmNotLocal(model)
        wanted = {model} if ":" in model else {model, model + ":latest"}
        for entry in self._listing():
            if (str(entry.get("model")) in wanted or str(entry.get("name")) in wanted) and (
                _is_remote_entry(entry)
            ):
                raise LlmNotLocal(model)

    def gpu_share(self, model: str) -> float | None:
        """Share of a loaded model held in VRAM (1.0 = fully on the GPU), or None if not loaded."""
        for loaded in self._call("GET", "/api/ps").get("models", []):
            if loaded.get("model") == model and loaded.get("size"):
                return float(loaded.get("size_vram") or 0) / float(loaded["size"])
        return None

    def load(self, model: str) -> None:
        """A generate request with no prompt only loads the model. It asks for the context
        size every chat uses: loaded at any other size, the next chat would load it again."""
        self._ensure_local(model)
        s = self._settings
        self._call(
            "POST",
            "/api/generate",
            {"model": model, "keep_alive": s.keep_alive, "options": {"num_ctx": s.num_ctx}},
            model=model,
        )

    def unload(self, model: str) -> None:
        self._ensure_local(model)
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

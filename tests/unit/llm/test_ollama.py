import io
import urllib.error
import urllib.request
from collections.abc import Mapping
from typing import Any

import pytest

from evra.config import LlmSettings
from evra.llm.ollama import OllamaHttp, OllamaProvider, is_loopback_url
from evra.llm.provider import (
    ChatMessage,
    LlmConfigError,
    LlmError,
    LlmModelMissing,
    LlmTimeout,
    LlmUnavailable,
)

SCHEMA = {"type": "object", "properties": {"a": {"type": "integer"}}, "required": ["a"]}


def reply(content: str = '{"a": 1}', done_reason: str = "stop") -> dict[str, Any]:
    return {
        "message": {"role": "assistant", "content": content},
        "prompt_eval_count": 120,
        "eval_count": 30,
        "done_reason": done_reason,
    }


def http_error(code: int, body: str) -> urllib.error.HTTPError:
    return urllib.error.HTTPError("http://127.0.0.1", code, "x", {}, io.BytesIO(body.encode()))  # type: ignore[arg-type]


class FakeHttp:
    def __init__(
        self, answers: Mapping[str, Any] | None = None, error: BaseException | None = None
    ):
        self.answers = dict(answers or {})
        self.error = error
        self.calls: list[tuple[str, str, Any]] = []

    def request(self, method: str, path: str, body: Mapping[str, Any] | None = None) -> Any:
        self.calls.append((method, path, body))
        if self.error is not None:
            raise self.error
        return self.answers[path]


def _provider(http: FakeHttp, **settings: Any) -> OllamaProvider:
    ticks = iter([10.0, 12.5])
    return OllamaProvider(LlmSettings(**settings), http=http, clock=lambda: next(ticks))


def test_chat_sends_the_settings_every_time() -> None:
    http = FakeHttp({"/api/chat": reply()})
    _provider(http).chat_json("gemma4:12b", [ChatMessage("user", "hi")], SCHEMA)
    assert http.calls == [
        (
            "POST",
            "/api/chat",
            {
                "model": "gemma4:12b",
                "messages": [{"role": "user", "content": "hi"}],
                "stream": False,
                "format": SCHEMA,
                "options": {"num_ctx": 32768, "temperature": 0, "num_predict": 4096},
                "keep_alive": "30s",
                "think": False,
            },
        )
    ]


def test_reply_counts_time_and_truncation() -> None:
    http = FakeHttp({"/api/chat": reply(done_reason="length")})
    result = _provider(http).chat_json("m", [ChatMessage("user", "hi")], SCHEMA)
    assert (result.content, result.tokens_in, result.tokens_out) == ('{"a": 1}', 120, 30)
    assert result.seconds == pytest.approx(2.5)
    assert result.truncated


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (http_error(404, '{"error": "model not found"}'), LlmModelMissing),
        (http_error(500, '{"error": "boom"}'), LlmError),
        (urllib.error.URLError(ConnectionRefusedError()), LlmUnavailable),
        (urllib.error.URLError(TimeoutError()), LlmTimeout),
        (TimeoutError(), LlmTimeout),
        (ConnectionResetError(), LlmUnavailable),
        (ValueError("not json"), LlmError),
    ],
)
def test_errors_become_evra_errors(error: BaseException, expected: type[LlmError]) -> None:
    with pytest.raises(expected) as caught:
        _provider(FakeHttp(error=error)).chat_json("m", [ChatMessage("user", "x")], SCHEMA)
    assert type(caught.value) is expected
    assert caught.value.__cause__ is None


def test_error_messages_never_carry_server_text() -> None:
    error = http_error(500, '{"error": "SECRET transcript words"}')
    with pytest.raises(LlmError) as caught:
        _provider(FakeHttp(error=error)).chat_json("m", [ChatMessage("user", "x")], SCHEMA)
    assert "SECRET" not in str(caught.value)
    assert "500" in str(caught.value)


def test_missing_model_names_it() -> None:
    error = http_error(404, '{"error": "not found"}')
    with pytest.raises(LlmModelMissing) as caught:
        _provider(FakeHttp(error=error)).chat_json("qwen3.5:9b", [], SCHEMA)
    assert caught.value.model == "qwen3.5:9b"


def test_installed_models_are_sorted_names() -> None:
    http = FakeHttp({"/api/tags": {"models": [{"model": "qwen3.5:9b"}, {"model": "gemma4:12b"}]}})
    assert _provider(http).installed_models() == ["gemma4:12b", "qwen3.5:9b"]


def test_installed_models_when_ollama_is_down() -> None:
    http = FakeHttp(error=urllib.error.URLError(ConnectionRefusedError()))
    with pytest.raises(LlmUnavailable):
        _provider(http).installed_models()


def test_gpu_share_and_unload() -> None:
    http = FakeHttp(
        {
            "/api/ps": {"models": [{"model": "gemma4:12b", "size": 200, "size_vram": 150}]},
            "/api/generate": {"done_reason": "unload"},
        }
    )
    provider = _provider(http)
    assert provider.gpu_share("gemma4:12b") == 0.75
    assert provider.gpu_share("qwen3.5:9b") is None
    provider.unload("gemma4:12b")
    assert http.calls[-1] == ("POST", "/api/generate", {"model": "gemma4:12b", "keep_alive": 0})


@pytest.mark.parametrize(
    ("url", "ok"),
    [
        ("http://127.0.0.1:11434", True),
        ("http://localhost:11434", True),
        ("http://[::1]:11434", True),
        ("http://192.168.1.5:11434", False),
        ("https://example.com", False),
        ("not a url", False),
    ],
)
def test_only_loopback_urls_are_allowed(url: str, ok: bool) -> None:
    assert is_loopback_url(url) is ok
    if not ok:
        with pytest.raises(LlmConfigError):
            OllamaProvider(LlmSettings(ollama_url=url), http=FakeHttp())


def test_real_http_ignores_proxies_and_refuses_redirects(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HTTP_PROXY", "http://proxy.invalid:8080")

    def proxies(opener: urllib.request.OpenerDirector) -> list[dict[str, str]]:
        return [h.proxies for h in opener.handlers if isinstance(h, urllib.request.ProxyHandler)]

    default = proxies(urllib.request.build_opener())
    assert default and default[0].get("http") == "http://proxy.invalid:8080"  # env is honoured
    http = OllamaHttp("http://127.0.0.1:11434", timeout_s=5)
    assert proxies(http.opener) == []  # the environment's proxy is never installed
    redirects = [
        h for h in http.opener.handlers if isinstance(h, urllib.request.HTTPRedirectHandler)
    ]
    request = urllib.request.Request("http://127.0.0.1:11434/api/chat")
    assert redirects and all(
        h.redirect_request(request, None, 302, "Found", {}, "http://evil.example/") is None  # type: ignore[arg-type]
        for h in redirects
    )

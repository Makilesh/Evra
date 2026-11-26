import http.client
import io
import urllib.error
import urllib.request
from collections.abc import Mapping
from typing import Any

import pytest

from evra.config import LlmSettings
from evra.llm.ollama import OllamaHttp, OllamaProvider, is_cloud_model_name, is_loopback_url
from evra.llm.provider import (
    ChatMessage,
    LlmConfigError,
    LlmError,
    LlmModelMissing,
    LlmNotLocal,
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
        tags_ok = self.error is None or isinstance(self.error, urllib.error.HTTPError)
        if path == "/api/tags" and path not in self.answers and tags_ok:
            return {"models": []}  # the local-model check; tests about it list their own tags
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


def test_cached_tokens_come_from_the_cache_count() -> None:
    answer = {**reply(), "prompt_eval_cached_count": 100}
    result = _provider(FakeHttp({"/api/chat": answer})).chat_json(
        "m", [ChatMessage("user", "hi")], SCHEMA
    )
    assert (result.tokens_in, result.cached_tokens) == (120, 100)
    plain = _provider(FakeHttp({"/api/chat": reply()})).chat_json(
        "m", [ChatMessage("user", "hi")], SCHEMA
    )
    assert plain.cached_tokens == 0


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


def test_load_asks_for_the_model_at_the_notes_context_size() -> None:
    # Loaded at any other context size, the model would be loaded again by the note's call.
    loaded = {"model": "gemma4:12b", "response": "", "done": True, "done_reason": "load"}
    http = FakeHttp({"/api/generate": loaded})
    _provider(http).load("gemma4:12b")
    assert http.calls == [
        (
            "POST",
            "/api/generate",
            {"model": "gemma4:12b", "keep_alive": "30s", "options": {"num_ctx": 32768}},
        )
    ]


def test_loading_a_missing_model_names_it() -> None:
    http = FakeHttp(error=http_error(404, '{"error":"model not found"}'))
    with pytest.raises(LlmModelMissing) as caught:
        _provider(http).load("qwen9:404b")
    assert caught.value.model == "qwen9:404b"


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


def test_a_broken_http_reply_is_unavailable_not_a_traceback() -> None:
    fake = FakeHttp(error=http.client.IncompleteRead(b""))
    with pytest.raises(LlmUnavailable):
        _provider(fake).chat_json("m", [ChatMessage("user", "x")], SCHEMA)


@pytest.mark.parametrize("answer", [[1, 2], "text", None])
def test_a_reply_that_is_not_a_json_object_is_an_llm_error(answer: Any) -> None:
    http = FakeHttp({"/api/chat": answer, "/api/tags": answer})
    with pytest.raises(LlmError):
        _provider(http).chat_json("m", [ChatMessage("user", "x")], SCHEMA)
    with pytest.raises(LlmError):
        _provider(http).installed_models()


@pytest.mark.parametrize(
    ("name", "cloud"),
    [
        ("gemma4:cloud", True),
        ("gemma4:31b-cloud", True),
        ("GPT-OSS:120B-CLOUD", True),
        ("gemma4:12b", False),
        ("cloudy:7b", False),
        ("my-cloud", False),
        ("foo-cloud:latest", False),
        ("hf.co/u/m-cloud:Q4_K_M", False),
    ],
)
def test_cloud_model_names(name: str, cloud: bool) -> None:
    assert is_cloud_model_name(name) is cloud


def test_cloud_name_refused_before_any_request() -> None:
    http = FakeHttp({"/api/chat": reply()})
    with pytest.raises(LlmNotLocal) as raised:
        _provider(http).chat_json("gemma4:cloud", [ChatMessage("user", "hi")], SCHEMA)
    assert raised.value.model == "gemma4:cloud"
    assert "hi" not in str(raised.value)
    assert http.calls == []


def test_remote_model_in_tags_is_refused() -> None:
    tags = {"models": [{"model": "big:1b", "remote_host": "https://ollama.com:443"}]}
    http = FakeHttp({"/api/tags": tags, "/api/chat": reply()})
    with pytest.raises(LlmNotLocal):
        _provider(http).chat_json("big:1b", [ChatMessage("user", "hi")], SCHEMA)
    assert [c[1] for c in http.calls] == ["/api/tags"]


def test_local_model_checks_tags_once() -> None:
    tags = {"models": [{"model": "gemma4:12b", "name": "gemma4:12b"}]}
    http = FakeHttp({"/api/tags": tags, "/api/chat": reply()})
    provider = OllamaProvider(LlmSettings(), http=http)
    for _ in range(2):
        provider.chat_json("gemma4:12b", [ChatMessage("user", "hi")], SCHEMA)
    assert [c[1] for c in http.calls].count("/api/tags") == 1


def test_untagged_name_matches_latest_and_unlisted_is_left_to_the_call() -> None:
    tags = {"models": [{"model": "big:latest", "remote_model": "big"}]}
    http = FakeHttp({"/api/tags": tags, "/api/generate": {}})
    provider = OllamaProvider(LlmSettings(), http=http)
    with pytest.raises(LlmNotLocal):
        provider.load("big")
    provider.unload("other:1b")  # not listed: the call itself decides


def test_installed_models_hide_cloud_models() -> None:
    tags = {
        "models": [
            {"model": "gemma4:12b"},
            {"model": "gemma4:cloud"},
            {"model": "x:1b", "remote_model": "x"},
        ]
    }
    http = FakeHttp({"/api/tags": tags})
    assert _provider(http).installed_models() == ["gemma4:12b"]


def test_embed_posts_inputs_and_normalises() -> None:
    http = FakeHttp({"/api/embed": {"embeddings": [[3, 4]], "prompt_eval_count": 2}})
    vectors = _provider(http).embed("qwen3-embedding:0.6b", ["hello"])
    assert vectors == [[0.6, 0.8]]
    assert http.calls == [
        (
            "POST",
            "/api/embed",
            {
                "model": "qwen3-embedding:0.6b",
                "input": ["hello"],
                "truncate": True,
                "keep_alive": "30s",
            },
        )
    ]


def test_embed_refuses_cloud_models() -> None:
    http = FakeHttp({"/api/embed": {"embeddings": [[1.0]]}})
    with pytest.raises(LlmNotLocal):
        _provider(http).embed("qwen3-embedding:cloud", ["hello"])
    assert http.calls == []


def test_embed_count_mismatch_is_an_error() -> None:
    http = FakeHttp({"/api/embed": {"embeddings": [[1.0, 0.0]]}})
    with pytest.raises(LlmError, match="without embeddings"):
        _provider(http).embed("qwen3-embedding:0.6b", ["a", "b"])


@pytest.mark.parametrize(
    "embeddings",
    [[[]], [[1.0, 0.0], []], [[1.0, 0.0], [1.0]], [[1.0, 0.0], "ab"]],
    ids=["empty", "one-empty", "different-sizes", "not-a-vector"],
)
def test_embed_vectors_must_be_whole_and_one_size(embeddings: list[object]) -> None:
    """A vector the cosine cannot use is Ollama's error, never a crash in the note's check."""
    http = FakeHttp({"/api/embed": {"embeddings": embeddings}})
    texts = [f"t{i}" for i in range(len(embeddings))]
    with pytest.raises(LlmError):
        _provider(http).embed("qwen3-embedding:0.6b", texts)


def test_embed_nothing_makes_no_request() -> None:
    http = FakeHttp({"/api/embed": {"embeddings": []}})
    assert _provider(http).embed("qwen3-embedding:0.6b", []) == []
    assert http.calls == []


def test_embed_missing_model_is_reported() -> None:
    http = FakeHttp(error=http_error(404, "not found"))
    with pytest.raises(LlmModelMissing):
        _provider(http).embed("qwen3-embedding:0.6b", ["a"])

from evra.notes.semantic import Embedder, SemanticCheck, as_query, cosine
from tests.unit.notes.fakes import FakeProvider


def test_embedder_batches_and_caches() -> None:
    provider = FakeProvider([])
    texts = [f"text {i}" for i in range(120)] + [f"text {i}" for i in range(10)]
    embedder = Embedder(provider, "m", batch=64)
    vectors = embedder.vectors(texts)
    assert len(vectors) == 130
    assert vectors[0] == vectors[120]
    assert [len(call) for call in provider.embed_calls] == [64, 56]
    embedder.vectors(["text 3", "text 4"])
    assert len(provider.embed_calls) == 2  # cached


def test_embedder_no_texts() -> None:
    provider = FakeProvider([])
    assert Embedder(provider, "m").vectors([]) == []
    assert provider.embed_calls == []


def test_query_format() -> None:
    assert as_query("x") == (
        "Instruct: Given a statement from meeting notes, retrieve the transcript lines "
        "that say it\nQuery:x"
    )


def test_cosine_of_unit_vectors() -> None:
    assert cosine([1.0, 0.0], [0.6, 0.8]) == 0.6


def test_similarities_pair_order() -> None:
    provider = FakeProvider([])
    check = SemanticCheck(Embedder(provider, "m"))
    sims = check.similarities(
        [
            ("launch moves october", "launch moves october"),
            ("launch moves october", "banana smoothie recipe"),
        ]
    )
    assert len(sims) == 2
    assert sims[0] > sims[1]
    assert check.threshold == 0.55
    assert len(provider.embed_calls) == 1  # claims and sources in one batch
    queries = {t for call in provider.embed_calls for t in call}
    assert as_query("launch moves october") in queries
    assert "launch moves october" in queries

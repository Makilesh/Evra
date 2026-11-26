from evra.notes.bm25 import Bm25, tokenize


def test_the_document_with_the_query_words_scores_highest() -> None:
    docs = [tokenize("we talked about lunch"), tokenize("the vendor quote is due Friday")]
    scores = Bm25(docs).scores(tokenize("vendor quote"))
    assert scores[1] > scores[0] == 0


def test_empty_query_or_corpus_gives_zeros() -> None:
    assert Bm25([["a"], ["b"]]).scores([]) == [0.0, 0.0]
    assert Bm25([]).scores(["a"]) == []


def test_tokenize_lowercases_stems_and_drops_noise() -> None:
    assert tokenize("Promised the QUOTE, twice! 42 a") == ["promi", "quote", "twice"]

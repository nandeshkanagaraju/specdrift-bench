from specdrift.bench.schema import Rule
from specdrift.code.chunker import chunk_source, chunk_workspace
from specdrift.retrieval.embedder import LocalHashingEmbedder, tokenize
from specdrift.retrieval.retriever import (
    add_constant_context,
    matches_gold,
    recall_at_k,
    retrieve,
)
from tests.conftest import SAMPLE_SOURCE


def test_tokenizer_splits_identifiers_and_keeps_numbers():
    tokens = tokenize("MAX_ACTIVE_LOANS and activeLoans hold 3 items")
    assert {"max", "active", "loans", "hold", "3"} <= set(tokens)


def test_tokenizer_drops_modal_filler():
    assert "must" not in tokenize("A member MUST NOT borrow")


def test_embeddings_are_unit_length():
    embedder = LocalHashingEmbedder()
    embedder.fit(["alpha beta", "gamma delta"])
    vectors = embedder.encode(["alpha beta", "gamma delta"])
    for vector in vectors:
        assert abs(float((vector * vector).sum()) - 1.0) < 1e-5


def test_retrieval_is_deterministic(library_dir):
    chunks = chunk_workspace(library_dir)
    rules = [Rule(id="R06", text="A member MUST NOT hold more than 3 active loans at once.")]
    first = retrieve(rules, chunks, LocalHashingEmbedder(), k=3)
    second = retrieve(rules, chunks, LocalHashingEmbedder(), k=3)
    assert [h.chunk_id for h in first["R06"]] == [h.chunk_id for h in second["R06"]]


def test_retrieval_finds_the_relevant_method(library_dir):
    chunks = chunk_workspace(library_dir)
    rules = [Rule(id="R06", text="A member MUST NOT hold more than 3 active loans at once.")]
    hits = retrieve(rules, chunks, LocalHashingEmbedder(), k=5)["R06"]
    assert any("borrow" in hit.chunk_id for hit in hits)


def test_scores_are_sorted_descending(library_dir):
    chunks = chunk_workspace(library_dir)
    rules = [Rule(id="R13", text="The late fee MUST be 0.50 per day late, capped at 20.00.")]
    hits = retrieve(rules, chunks, LocalHashingEmbedder(), k=5)["R13"]
    assert [hit.score for hit in hits] == sorted((h.score for h in hits), reverse=True)


def test_empty_inputs_are_handled():
    assert retrieve([], [], LocalHashingEmbedder(), k=3) == {}


def test_gold_matching_compares_qualnames():
    assert matches_gold("src/a.py::Service.borrow", "Service.borrow")
    assert not matches_gold("src/a.py::Service.other", "Service.borrow")
    assert not matches_gold("src/a.py::Service.borrow", "")


def test_recall_at_k_respects_the_cutoff(library_dir):
    chunks = chunk_workspace(library_dir)
    rules = [Rule(id="R14", text="`list_loans` MUST return active loans sorted by due date.")]
    hits = retrieve(rules, chunks, LocalHashingEmbedder(), k=5)["R14"]
    assert recall_at_k(hits, "LibraryService.list_loans", 5)


def test_constant_context_adds_the_defining_module_chunk():
    chunks = chunk_source(SAMPLE_SOURCE, "a.py")
    borrow = [c for c in chunks if c.qualname == "Service.borrow"]
    widened = add_constant_context(borrow, chunks)
    assert [c.qualname for c in widened] == ["Service.borrow", "<module>"]


def test_constant_context_is_not_added_when_nothing_is_referenced():
    chunks = chunk_source(SAMPLE_SOURCE, "a.py")
    helper = [c for c in chunks if c.qualname == "helper"]
    assert add_constant_context(helper, chunks) == helper

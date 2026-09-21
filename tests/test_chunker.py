from specdrift.code.chunker import chunk_source, chunk_workspace
from tests.conftest import SAMPLE_SOURCE


def ids(chunks):
    return {chunk.qualname for chunk in chunks}


def test_emits_functions_methods_class_headers_and_module():
    chunks = chunk_source(SAMPLE_SOURCE, "a.py")
    assert ids(chunks) == {"<module>", "Service", "Service.borrow", "helper"}


def test_module_chunk_carries_the_constants():
    module = next(c for c in chunk_source(SAMPLE_SOURCE, "a.py") if c.qualname == "<module>")
    assert "LIMIT = 3" in module.source


def test_chunk_keeps_comments_and_line_span():
    borrow = next(c for c in chunk_source(SAMPLE_SOURCE, "a.py") if c.qualname == "Service.borrow")
    assert "# R01 - the check" in borrow.source
    assert borrow.start_line < borrow.end_line


def test_chunk_id_is_path_plus_qualname():
    chunks = chunk_source(SAMPLE_SOURCE, "pkg/a.py")
    assert "pkg/a.py::Service.borrow" in {chunk.id for chunk in chunks}


def test_syntax_error_yields_no_chunks():
    assert chunk_source("def broken(:\n", "a.py") == []


def test_workspace_chunks_are_sorted_and_relative(library_dir):
    chunks = chunk_workspace(library_dir)
    assert chunks
    assert [c.id for c in chunks] == sorted(c.id for c in chunks)
    assert all(chunk.file.startswith("src/") for chunk in chunks)

"""Turn rule text and code chunks into unit vectors.

Two backends behind one interface:

``local``
    A deterministic hashing vectoriser with IDF weighting, written in numpy. It needs
    no model download and no network, so `retrieval-eval` runs in seconds and a marker
    can reproduce the retrieval numbers exactly. This is the default.

``sentence-transformers``
    The published embedding model from the design document, used when the extra is
    installed. Vectors are cached on disk so a second run is free.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path
from typing import Protocol

import numpy as np

# Splits identifiers the way a reader does: snake_case, camelCase, digits kept whole.
_WORD_RE = re.compile(r"[A-Za-z]+|\d+(?:\.\d+)?")
_CAMEL_RE = re.compile(r"[A-Z]+(?![a-z])|[A-Z][a-z]*|[a-z]+")

# Spec-writing vocabulary and English filler carry no retrieval signal.
STOPWORDS = frozenset(
    """
    a an the and or of to in on at by for from with without is are be been being must
    shall should may can will would not no nor its it this that these those as if then
    than when while each every any all only also more most other another such same
    return returns returned when-ever per into out up down over under again
    """.split()
)


def tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    for raw in _WORD_RE.findall(text):
        if raw[0].isdigit():
            tokens.append(raw)
            continue
        for part in _CAMEL_RE.findall(raw):
            lowered = part.lower()
            if len(lowered) > 1 and lowered not in STOPWORDS:
                tokens.append(lowered)
    return tokens


class Embedder(Protocol):
    name: str

    def fit(self, corpus: list[str]) -> None: ...

    def encode(self, texts: list[str]) -> np.ndarray: ...


class LocalHashingEmbedder:
    """Hashed bag of identifiers with sublinear TF and IDF, L2 normalised."""

    def __init__(self, dims: int = 2048) -> None:
        self.name = f"local-hashing-{dims}"
        self.dims = dims
        self._idf: dict[str, float] = {}
        self._default_idf = 1.0

    def fit(self, corpus: list[str]) -> None:
        document_frequency: dict[str, int] = {}
        for text in corpus:
            for token in set(tokenize(text)):
                document_frequency[token] = document_frequency.get(token, 0) + 1

        total = max(len(corpus), 1)
        self._idf = {
            token: math.log((total + 1) / (count + 1)) + 1.0
            for token, count in document_frequency.items()
        }
        self._default_idf = math.log(total + 1) + 1.0

    def _bucket(self, token: str) -> int:
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
        return int.from_bytes(digest, "big") % self.dims

    def encode(self, texts: list[str]) -> np.ndarray:
        matrix = np.zeros((len(texts), self.dims), dtype=np.float32)

        for row, text in enumerate(texts):
            counts: dict[str, int] = {}
            for token in tokenize(text):
                counts[token] = counts.get(token, 0) + 1

            for token, count in counts.items():
                weight = (1.0 + math.log(count)) * self._idf.get(token, self._default_idf)
                matrix[row, self._bucket(token)] += weight

        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        norms[norms == 0.0] = 1.0
        return matrix / norms


class SentenceTransformerEmbedder:
    """The published model from the design document, with an on-disk vector cache."""

    def __init__(self, model_name: str, cache_dir: Path) -> None:
        self.name = model_name
        self.cache_dir = Path(cache_dir) / "embeddings"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._model = None

    def fit(self, corpus: list[str]) -> None:
        return None

    def _load(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.name)
        return self._model

    def _cache_path(self, text: str) -> Path:
        key = hashlib.sha256(f"{self.name}\x00{text}".encode("utf-8")).hexdigest()
        return self.cache_dir / f"{key}.json"

    def encode(self, texts: list[str]) -> np.ndarray:
        vectors: list[np.ndarray | None] = []
        missing: list[int] = []

        for index, text in enumerate(texts):
            path = self._cache_path(text)
            if path.exists():
                vectors.append(np.asarray(json.loads(path.read_text()), dtype=np.float32))
            else:
                vectors.append(None)
                missing.append(index)

        if missing:
            fresh = self._load().encode(
                [texts[i] for i in missing], normalize_embeddings=True
            )
            for slot, index in enumerate(missing):
                vector = np.asarray(fresh[slot], dtype=np.float32)
                vectors[index] = vector
                self._cache_path(texts[index]).write_text(json.dumps(vector.tolist()))

        matrix = np.vstack([v for v in vectors if v is not None])
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        norms[norms == 0.0] = 1.0
        return matrix / norms


def build_embedder(backend: str, model_name: str, cache_dir: Path) -> Embedder:
    if backend == "sentence-transformers":
        return SentenceTransformerEmbedder(model_name, cache_dir)
    if backend == "local":
        return LocalHashingEmbedder()
    raise ValueError(f"unknown embed backend {backend!r}")

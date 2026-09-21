"""A JSON-file cache for model responses.

The key is the content of the question, never the case id, so the many cases that
leave a (rule, chunk) pair untouched all share one stored answer. That is what keeps a
full benchmark run down to a few hundred calls.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


class ResponseCache:
    def __init__(self, cache_dir: str | Path, namespace: str = "verify") -> None:
        self.root = Path(cache_dir) / namespace
        self.root.mkdir(parents=True, exist_ok=True)
        self.hits = 0
        self.misses = 0

    @staticmethod
    def key(
        rule_text: str,
        chunk_sources: list[str],
        model: str,
        prompt_version: str,
        run: int = 1,
    ) -> str:
        parts = [rule_text, *chunk_sources, model, prompt_version]
        # Run 1 is the cached baseline; later runs deliberately bypass it via the salt.
        if run != 1:
            parts.append(f"run={run}")
        payload = "\x00".join(parts).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    def _path(self, key: str) -> Path:
        return self.root / key[:2] / f"{key}.json"

    def get(self, key: str) -> str | None:
        path = self._path(key)
        if not path.exists():
            self.misses += 1
            return None
        self.hits += 1
        return json.loads(path.read_text(encoding="utf-8"))["response"]

    def put(self, key: str, response: str) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"response": response}), encoding="utf-8")

    @property
    def total(self) -> int:
        return self.hits + self.misses

"""Runtime settings, read once from the environment or a .env file."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Stage 2 verification.
    llm_provider: str = "fake"          # fake | openai | anthropic
    llm_model: str = "gpt-4o-mini"
    llm_base_url: str = ""              # any OpenAI-compatible endpoint
    llm_api_key: str = ""
    llm_max_tokens: int = 600
    llm_timeout_s: float = 60.0

    # Stage 1 retrieval.
    embed_backend: str = "local"        # local | sentence-transformers
    embed_model: str = "BAAI/bge-small-en-v1.5"
    top_k: int = 3

    # Paths, all relative to the repository root.
    projects_dir: Path = REPO_ROOT / "projects"
    cases_dir: Path = REPO_ROOT / "cases"
    results_dir: Path = REPO_ROOT / "results"
    cache_dir: Path = REPO_ROOT / "cache"
    work_dir: Path = REPO_ROOT / "work"

    @property
    def built_cases_path(self) -> Path:
        return self.cases_dir / "built.jsonl"

    def detector_dir(self, detector: str) -> Path:
        return self.results_dir / detector


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()

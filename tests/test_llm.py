import sys
import types

import pytest

from specdrift.config import Settings
from specdrift.verify import llm as llm_module
from specdrift.verify.llm import FakeLLM, LLMError, build_llm, with_retries


class Flaky:
    model = "flaky"

    def __init__(self, failures: int) -> None:
        self.failures, self.calls = failures, 0

    def complete(self, system: str, user: str) -> str:
        self.calls += 1
        if self.calls <= self.failures:
            raise ConnectionError("boom")
        return "ok"


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(llm_module.time, "sleep", lambda s: None)


def test_with_retries_recovers_from_transient_failures():
    flaky = Flaky(failures=1)
    assert with_retries(flaky, "s", "u") == "ok"
    assert flaky.calls == 2


def test_with_retries_gives_up_with_an_llm_error():
    flaky = Flaky(failures=99)
    with pytest.raises(LLMError, match="boom"):
        with_retries(flaky, "s", "u")
    assert flaky.calls == llm_module.RETRIES


def test_build_llm_fake_and_unknown_provider():
    assert isinstance(build_llm(Settings(llm_provider="fake")), FakeLLM)
    with pytest.raises(ValueError, match="unknown LLM provider"):
        build_llm(Settings(llm_provider="carrier-pigeon"))


def test_openai_adapter_sends_the_prompt_and_budget(monkeypatch):
    seen = {}

    class Completions:
        def create(self, **kwargs):
            seen.update(kwargs)
            message = types.SimpleNamespace(content="hello")
            return types.SimpleNamespace(choices=[types.SimpleNamespace(message=message)])

    class Client:
        def __init__(self, **kwargs):
            seen["client"] = kwargs
            self.chat = types.SimpleNamespace(completions=Completions())

    monkeypatch.setitem(sys.modules, "openai", types.SimpleNamespace(OpenAI=Client))
    settings = Settings(llm_provider="openai", llm_model="m", llm_api_key="k", llm_base_url="http://x")
    adapter = build_llm(settings, max_tokens=123)

    assert adapter.complete("SYS", "USER") == "hello"
    assert seen["max_tokens"] == 123 and seen["temperature"] == 0 and seen["model"] == "m"
    assert seen["messages"][0] == {"role": "system", "content": "SYS"}
    assert seen["client"]["base_url"] == "http://x"


def test_anthropic_adapter_joins_text_blocks(monkeypatch):
    sent = {}

    class Messages:
        def create(self, **kwargs):
            sent.update(kwargs)
            blocks = [types.SimpleNamespace(type="text", text="a"),
                      types.SimpleNamespace(type="tool_use", text="skip"),
                      types.SimpleNamespace(type="text", text="b")]
            return types.SimpleNamespace(content=blocks)

    class Client:
        def __init__(self, **kwargs):
            self.messages = Messages()

    monkeypatch.setitem(sys.modules, "anthropic", types.SimpleNamespace(Anthropic=Client))
    adapter = build_llm(Settings(llm_provider="anthropic", llm_model="m", llm_api_key="k"))
    assert adapter.complete("s", "u") == "ab"
    # The current SDK has no `temperature` argument; sending one raised TypeError on every call.
    assert "temperature" not in sent

import types

from specdrift.config import Settings
from specdrift.verify import llm as llm_module
from specdrift.verify.llm import build_llm


class _Batch(dict):
    def to(self, device):
        self.device_seen = device
        return self


def _fakes(seen):
    class Tok:
        pad_token_id = 0

        def apply_chat_template(self, messages, tokenize, add_generation_prompt):
            seen["messages"], seen["template"] = messages, (tokenize, add_generation_prompt)
            return "PROMPT"

        def __call__(self, text, return_tensors):
            return _Batch(input_ids=types.SimpleNamespace(shape=(1, 3)))

        def decode(self, tokens, skip_special_tokens):
            seen["decoded"] = (list(tokens), skip_special_tokens)
            return '{"verdict": "COMPLIANT"}'

    class Model:
        device = "cpu"

        def generate(self, **kwargs):
            seen["generate"] = kwargs
            return [[7, 7, 7, 8, 9]]

    return Model(), Tok()


def test_adapter_decodes_only_the_new_tokens_greedily():
    seen = {}
    adapter = llm_module.HuggingFaceLLM("Qwen/base", "runs/m1-adapter/", max_tokens=77, _loaded=_fakes(seen))

    assert adapter.complete("SYS", "USER") == '{"verdict": "COMPLIANT"}'
    assert seen["decoded"] == ([8, 9], True)
    assert seen["generate"]["do_sample"] is False and seen["generate"]["max_new_tokens"] == 77
    assert seen["messages"] == [{"role": "system", "content": "SYS"}, {"role": "user", "content": "USER"}]
    assert seen["template"] == (False, True)


def test_model_name_includes_the_adapter_so_caches_cannot_mix():
    loaded = _fakes({})
    tuned = llm_module.HuggingFaceLLM("Qwen/base", "runs/m1-adapter/", _loaded=loaded)
    plain = llm_module.HuggingFaceLLM("Qwen/base", _loaded=loaded)
    assert tuned.model == "Qwen/base+m1-adapter" and plain.model == "Qwen/base"


def test_build_llm_routes_huggingface_with_the_adapter(monkeypatch):
    made = {}

    def fake_load(self, load_in_4bit):
        made["args"] = (self.base, self.adapter, self.max_tokens, load_in_4bit)
        return _fakes({})

    monkeypatch.setattr(llm_module.HuggingFaceLLM, "_load", fake_load)
    adapter = build_llm(Settings(llm_provider="huggingface", llm_model="Qwen/base", llm_adapter="a/b"), max_tokens=50)

    assert isinstance(adapter, llm_module.HuggingFaceLLM)
    assert made["args"] == ("Qwen/base", "a/b", 50, True)

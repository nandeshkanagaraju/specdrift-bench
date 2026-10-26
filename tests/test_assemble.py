import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from specdrift import cli
from specdrift.bench.schema import Chunk, Counterexample, Evidence, Rule
from specdrift.config import REPO_ROOT
from specdrift.data.assemble import (
    assemble_project,
    load_rule_map,
    parse_failure,
    shown_span,
    symbol_matches,
    view_covers,
)
from specdrift.data.inject import Mutant, inject_project
from specdrift.data.schema import Provenance, Target, TrainingExample
from specdrift.data.validate import approx_tokens, problems, shown_end
from specdrift.spec.parser import load_project_rules

runner = CliRunner()
TOY = REPO_ROOT / "tests" / "fixtures" / "toyshop"


@pytest.fixture(scope="module")
def mutants():
    found, _ = inject_project(TOY, "toyshop", per_operator=3)
    return found


@pytest.fixture(scope="module")
def built(mutants):
    return assemble_project(TOY, "toyshop", mutants, TOY / "rules.yaml", gold_view=0.0, abstain=0.0)


def by(examples, **match):
    return [e for e in examples if all(getattr(e, k) == v for k, v in match.items())]


def note(example, key):
    return example.provenance.notes[key]


# ---------------------------------------------------------------- what the oracle decides


def test_a_mutant_the_projects_own_suite_misses_is_rescued_by_the_oracle(built):
    examples, stats = built
    rescued = [e for e in by(examples, label="DRIFT") if note(e, "mutant_status") == "survived"]
    assert rescued and stats["counts"]["DRIFT/rescued by oracle"] == len(rescued)
    assert {e.rule.id for e in rescued} == {"R04"}                 # shipping is untested by the suite
    one = next(e for e in rescued if note(e, "operator") == "constant")
    assert one.target.counterexample == Counterexample(input="shipping(50)", expected="0", actual="5")
    assert one.provenance.label_method == "execution"


def test_the_oracle_not_the_symbol_decides_which_rule_is_violated(built):
    examples, _ = built
    constant = [e for e in examples if note_or_none(e, "mutant_id") and "FREE_SHIPPING_AT = 51" in note(e, "inject_replace")]
    by_rule = {e.rule.id: e.label for e in constant}
    # <module> belongs to R01, R03 and R04; only R04's oracle fails when the shipping threshold moves
    assert by_rule["R04"] == "DRIFT"
    assert by_rule.get("R01", "COMPLIANT") == "COMPLIANT" and by_rule.get("R03", "COMPLIANT") == "COMPLIANT"


def note_or_none(example, key):
    return example.provenance.notes.get(key)


def test_wrong_rule_examples_show_the_changed_code_and_stay_compliant(built):
    examples, _ = built
    wrong = by(examples, category="hardneg:wrong_rule")
    assert wrong
    for example in wrong:
        assert example.label == "COMPLIANT" and example.source == "hardneg"
        replace = note(example, "inject_replace")
        assert any(replace in chunk.source or replace.strip().splitlines()[0].strip() in chunk.source
                   for chunk in example.chunks)


def test_counterexamples_name_the_exception_that_was_expected(built):
    examples, _ = built
    dropped = next(e for e in by(examples, label="DRIFT") if note(e, "operator") == "drop_guard")
    assert dropped.target.counterexample == Counterexample(
        input="check_age(17)", expected="raises ValueError", actual="no exception was raised")
    wrong_type = next(e for e in by(examples, label="DRIFT") if note(e, "operator") == "exception_type")
    assert wrong_type.target.counterexample.expected == "raises ValueError"
    assert wrong_type.target.counterexample.actual.startswith("raises RuntimeError")


def test_example_ids_are_unique_and_do_not_repeat_the_project(built):
    ids = [e.example_id for e in built[0]]
    assert len(ids) == len(set(ids)) and not any("toyshop-toyshop" in i for i in ids)


def test_every_rule_gets_an_unchanged_example(built):
    examples, _ = built
    assert {e.rule.id for e in by(examples, category="N1")} == {"R01", "R02", "R03", "R04"}
    assert all(e.label == "COMPLIANT" for e in by(examples, category="N1"))


# ---------------------------------------------------------------- everything written is valid and consistent


def test_the_validator_accepts_everything_that_was_written(built):
    examples, stats = built
    assert examples and not stats["rejected_by_validator"]
    assert all(not problems(e) for e in examples)


def test_evidence_is_in_the_line_numbers_the_prompt_shows(built):
    examples, _ = built
    for example in by(examples, label="DRIFT"):
        if note(example, "operator") == "drop_guard":
            continue                                            # a deleted line has no line of its own
        ev = example.target.evidence
        chunk = next(c for c in example.chunks if c.file == ev.file and c.start_line <= ev.start_line <= shown_end(c))
        shown = chunk.source.splitlines()[ev.start_line - chunk.start_line]
        assert shown.strip() in note(example, "inject_replace"), (example.example_id, shown)


def test_examples_the_validator_rejects_are_dropped_and_reported(mutants, monkeypatch):
    from specdrift.data import assemble

    real = assemble.problems
    monkeypatch.setattr(assemble, "problems", lambda e: ["forced"] if e.rule.id == "R03" else real(e))
    examples, stats = assemble_project(TOY, "toyshop", mutants, TOY / "rules.yaml")
    assert "R03" not in {e.rule.id for e in examples}
    assert stats["rejected_by_validator"] and all(v == ["forced"] for v in stats["rejected_by_validator"].values())
    assert stats["examples"] == len(examples)


def test_every_drift_clause_is_quoted_from_the_rule(built):
    for example in by(built[0], label="DRIFT"):
        assert example.target.violated_clause in example.rule.text


def test_find_and_replace_are_recorded_for_the_leakage_check(built):
    for example in by(built[0], source="synth", label="DRIFT"):
        assert note(example, "inject_find")                      # what was changed is always recorded
        assert "inject_replace" in example.provenance.notes      # ... and may legitimately be empty (a deleted guard)


# ---------------------------------------------------------------- what is shown to the model


def test_gold_view_always_contains_the_changed_chunk(mutants):
    examples, _ = assemble_project(TOY, "toyshop", mutants, TOY / "rules.yaml", gold_view=1.0, abstain=0.0)
    drift = by(examples, label="DRIFT")
    assert drift
    for example in drift:
        symbol = next(m.symbol for m in mutants if m.mutant_id == note(example, "mutant_id"))
        assert symbol in {c.qualname for c in example.chunks}


def test_a_retrieval_miss_becomes_an_uncertain_example_never_a_drift_label(mutants):
    examples, _ = assemble_project(TOY, "toyshop", mutants, TOY / "rules.yaml", gold_view=0.0, abstain=0.0, top_k=1)
    for example in examples:
        if example.category == "abstain:retrieval_miss":
            assert example.label == "UNCERTAIN" and example.target.violated_clause == ""
    for example in by(examples, label="DRIFT"):
        symbol = next(m.symbol for m in mutants if m.mutant_id == note(example, "mutant_id"))
        assert symbol in {c.qualname for c in example.chunks}   # a DRIFT label always has its code in view
    assert any(e.category == "abstain:retrieval_miss" for e in examples)


def test_a_retrieval_miss_also_yields_a_drift_example_that_shows_the_changed_code(mutants):
    args = dict(gold_view=0.0, abstain=0.0, top_k=1)
    examples, stats = assemble_project(TOY, "toyshop", mutants, TOY / "rules.yaml", **args)
    misses = by(examples, category="abstain:retrieval_miss")
    golds = [e for e in examples if e.example_id.endswith("-gold")]
    assert misses and len(golds) == len(misses) == stats["counts"]["DRIFT/recovered from a retrieval miss"]
    for gold in golds:
        miss = next(e for e in misses if e.example_id == note(gold, "recovered_from"))
        assert (gold.label, miss.label) == ("DRIFT", "UNCERTAIN") and gold.rule.id == miss.rule.id
        symbol = next(m.symbol for m in mutants if m.mutant_id == note(gold, "mutant_id"))
        assert symbol in {c.qualname for c in gold.chunks} and note(gold, "view") == "gold"
        assert gold.target.counterexample.input and not problems(gold)

    off, _ = assemble_project(TOY, "toyshop", mutants, TOY / "rules.yaml", gold_on_miss=False, **args)
    assert not [e for e in off if e.example_id.endswith("-gold")]


def test_abstention_twins_drop_the_code_the_rule_is_about(mutants):
    examples, stats = assemble_project(TOY, "toyshop", mutants, TOY / "rules.yaml", gold_view=0.0, abstain=1.0)
    twins = by(examples, category="abstain:dropped_chunk")
    assert twins and stats["counts"]["abstain/dropped_chunk"] == len(twins)
    specs = load_rule_map(TOY / "rules.yaml", load_project_rules(TOY), TOY)
    for twin in twins:
        assert twin.label == "UNCERTAIN" and twin.example_id.endswith("-abstain")
        assert not view_covers(specs[twin.rule.id].symbols, twin.chunks)
        assert note(twin, "from") in {e.example_id for e in examples}


def test_the_same_seed_gives_the_same_examples(mutants):
    a, _ = assemble_project(TOY, "toyshop", mutants, TOY / "rules.yaml", seed=5)
    b, _ = assemble_project(TOY, "toyshop", mutants, TOY / "rules.yaml", seed=5)
    assert [e.model_dump() for e in a] == [e.model_dump() for e in b]


def test_a_whole_project_lands_in_the_split_it_is_given(mutants):
    examples, _ = assemble_project(TOY, "toyshop", mutants, TOY / "rules.yaml", split="val")
    assert {e.split for e in examples} == {"val"} and {e.project_id for e in examples} == {"toyshop"}


# ---------------------------------------------------------------- bad input is refused, not guessed at


@pytest.fixture()
def toy_copy(tmp_path):
    root = tmp_path / "toyshop"
    shutil.copytree(TOY, root, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
    return root


def test_a_rule_whose_oracle_fails_on_the_original_is_excluded(toy_copy, mutants):
    (toy_copy / "oracles" / "test_r03.py").write_text(
        "from shop import total_price\n\ndef test_wrong():\n    assert total_price(10, 2) == 999\n")
    examples, stats = assemble_project(toy_copy, "toyshop", mutants, toy_copy / "rules.yaml")
    assert "R03" in stats["rules_excluded"]
    assert "R03" not in {e.rule.id for e in examples}


def test_no_usable_oracle_at_all_is_an_error(toy_copy, mutants):
    for path in (toy_copy / "oracles").glob("test_r0*.py"):
        path.write_text("def test_never():\n    assert False\n")
    with pytest.raises(ValueError, match="no rule has an oracle"):
        assemble_project(toy_copy, "toyshop", mutants, toy_copy / "rules.yaml")


def test_the_rule_map_is_checked_against_the_spec_and_the_disk(toy_copy):
    rules = load_project_rules(toy_copy)
    path = toy_copy / "rules.yaml"
    path.write_text("R99:\n  symbols: [x]\n  oracle: [oracles/test_r01.py]\n")
    with pytest.raises(ValueError, match="not a rule"):
        load_rule_map(path, rules, toy_copy)
    path.write_text("R01:\n  symbols: [check_age]\n  oracle: [oracles/missing.py]\n")
    with pytest.raises(ValueError, match="does not exist"):
        load_rule_map(path, rules, toy_copy)
    path.write_text("R01:\n  symbols: []\n  oracle: [oracles/test_r01.py]\n")
    with pytest.raises(ValueError, match="needs both"):
        load_rule_map(path, rules, toy_copy)


def test_the_test_set_cannot_be_turned_into_training_data(toy_copy, mutants):
    with pytest.raises(ValueError, match="test set"):
        assemble_project(toy_copy, "toyshop", mutants, toy_copy / "rules.yaml", protected_roots=[toy_copy.parent])


def test_the_original_project_is_left_untouched(toy_copy, mutants):
    before = {p: p.read_text() for p in toy_copy.rglob("*.py")}
    assemble_project(toy_copy, "toyshop", mutants, toy_copy / "rules.yaml")
    assert {p: p.read_text() for p in toy_copy.rglob("*.py")} == before


def test_mutants_that_crashed_or_that_no_rule_covers_are_skipped(toy_copy, mutants):
    stray = Mutant(mutant_id="x-D2-999", project="toyshop", category="D2", operator="constant",
                   file="src/shop.py", line=1, symbol="not_a_symbol", find="a", replace="b",
                   description="", status="killed")
    _, stats = assemble_project(toy_copy, "toyshop", [*mutants, stray], toy_copy / "rules.yaml")
    assert stats["counts"]["skipped/no rule covers the symbol"] >= 1
    assert stats["counts"].get("skipped/crash", 0) == sum(m.status == "crash" for m in mutants)


# ---------------------------------------------------------------- small pieces


def test_symbol_matching_covers_methods_of_a_class_but_not_prefix_lookalikes():
    assert symbol_matches(["Wallet"], "Wallet.deposit") and symbol_matches(["Wallet"], "Wallet")
    assert not symbol_matches(["Wallet"], "WalletTotals.add") and not symbol_matches(["f"], "<module>")
    assert symbol_matches(["<module>"], "<module>")


def test_the_module_chunk_is_numbered_the_way_the_prompt_shows_it():
    source = '"""doc"""\n\nA = 1\n\nB = 2\n\n\ndef f():\n    return A\n'
    from specdrift.code.chunker import chunk_source

    module = next(c for c in chunk_source(source, "m.py") if c.qualname == "<module>")
    # B is on file line 5 but the prompt shows it as line 3 (docstring, A, B counted consecutively)
    assert shown_span(module, source, 5, 5) == (module.start_line + 2, module.start_line + 2)
    func = next(c for c in chunk_source(source, "m.py") if c.qualname == "f")
    assert shown_span(func, source, 9, 9) == (9, 9)


FAILURES = {
    "assert": "tests/o.py:5: in test_x\n    assert shipping(50) == 0\nE   assert 5 == 0\nE    +  where 5 = shipping(50)\n",
    "no_raise_old": "tests/o.py:5: in test_x\n    with pytest.raises(ValueError):\nE   Failed: DID NOT RAISE <class 'ValueError'>\n",
    "no_raise_new": "tests/o.py:5: in test_x\n    with pytest.raises(ValueError):\nE   Failed: DID NOT RAISE ValueError\n",
    "diff": "tests/o.py:5: in test_x\n    assert str(bump()) == \"3.4.6\"\nE   AssertionError: assert '3.4.7' == '3.4.6'\nE     - 3.4.6\nE     + 3.4.7\n",
    "left_raises": "tests/o.py:5: in test_x\n    assert str(Version(0, 0, 0)) == \"0.0.0\"\nE   ValueError: 'major' is negative\n",
    "other": "tests/o.py:5: in test_x\n    f(1)\nsrc/m.py:2: in f\n    raise KeyError(1)\nE   KeyError: 1\n",
    "nothing": "no traceback at all",
}


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("assert", Counterexample(input="shipping(50)", expected="0", actual="5")),
        ("no_raise_old", Counterexample(input="", expected="raises ValueError", actual="no exception was raised")),
        ("no_raise_new", Counterexample(input="", expected="raises ValueError", actual="no exception was raised")),
        ("diff", Counterexample(input="str(bump())", expected="'3.4.6'", actual="'3.4.7'")),
        ("left_raises", Counterexample(input="str(Version(0, 0, 0))", expected="'0.0.0'", actual="raises ValueError: 'major' is negative")),
        ("other", Counterexample(input="f(1)", expected="no exception", actual="raises KeyError: 1")),
        ("nothing", Counterexample(input="(oracle)", expected="the oracle passes", actual="the oracle failed")),
    ],
)
def test_failure_output_is_read_into_input_expected_actual(name, expected, tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "o.py").write_text("x = 1\n" * 4 + "with pytest.raises(ValueError):\n    pass\n")
    got = parse_failure(FAILURES[name], tmp_path, ("tests/o.py",))
    assert (got.expected, got.actual) == (expected.expected, expected.actual)
    if name in ("assert", "other", "diff", "left_raises"):
        assert got.input == expected.input


# ---------------------------------------------------------------- the validator itself


def good_drift(**over):
    chunk = Chunk(id="a.py::f", file="a.py", qualname="f", start_line=1, end_line=2,
                  source="def f(x):\n    return x\n")
    base = dict(
        example_id="v-1", source="synth", split="train", project_id="p", rule=Rule(id="R01", text="f MUST return x."),
        chunks=[chunk], label="DRIFT", category="D1",
        target=Target(verdict="DRIFT", confidence=0.9, violated_clause="f MUST return x.",
                      evidence=Evidence(file="a.py", start_line=2, end_line=2),
                      counterexample=Counterexample(input="f(1)", expected="1", actual="2")),
        provenance=Provenance(label_method="execution", generator="t"),
    )
    base.update(over)
    return TrainingExample(**base)


def test_a_class_chunk_with_a_trimmed_trailing_blank_line_is_valid_but_a_real_gap_is_not():
    trimmed = good_drift().chunks[0].model_copy(update={"end_line": 3})            # spans 3, holds 2
    assert problems(good_drift(chunks=[trimmed])) == []
    gapped = good_drift().chunks[0].model_copy(update={"end_line": 9})             # spans 9, holds 2
    assert any("spans" in p for p in problems(good_drift(chunks=[gapped])))


def test_the_validator_accepts_a_good_example_and_names_each_defect():
    assert problems(good_drift()) == []

    def bad(**over):
        return problems(good_drift(**over))

    target = good_drift().target
    assert any("verbatim" in p for p in bad(target=target.model_copy(update={"violated_clause": "something else"})))
    assert any("evidence" in p for p in bad(target=target.model_copy(
        update={"evidence": Evidence(file="a.py", start_line=9, end_line=9)})))
    assert any("counterexample" in p for p in bad(target=target.model_copy(update={"counterexample": Counterexample()})))
    assert any("does not match" in p for p in bad(label="COMPLIANT"))
    assert any("no code" in p for p in bad(chunks=[]))
    assert any("must carry no" in p for p in problems(good_drift(
        label="UNCERTAIN", target=target.model_copy(update={"verdict": "UNCERTAIN"}))))
    secret = good_drift().chunks[0].model_copy(update={"source": "def f(x):\n    k = 'sk-" + "a" * 30 + "'\n"})
    assert any("secret" in p for p in bad(chunks=[secret]))
    huge = good_drift().chunks[0].model_copy(update={"source": "x = 1\n" * 2000, "end_line": 2000})
    assert approx_tokens(good_drift(chunks=[huge])) > 1536 and any("tokens" in p for p in bad(chunks=[huge]))


# ---------------------------------------------------------------- the command line


def test_cli_injects_then_assembles(settings, tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    muts, outfile = tmp_path / "m.jsonl", tmp_path / "out" / "b.jsonl"
    assert runner.invoke(cli.app, ["data-inject", str(TOY), "--out", str(muts), "--per-operator", "2"]).exit_code == 0
    done = runner.invoke(cli.app, ["data-assemble", str(TOY), "--mutants", str(muts), "--out", str(outfile)])
    assert done.exit_code == 0, done.output
    rows = [json.loads(line) for line in outfile.read_text().splitlines()]
    assert rows and all(TrainingExample.model_validate(r) for r in rows)
    assert json.loads(outfile.with_suffix(".stats.json").read_text())["examples"] == len(rows)

    refused = runner.invoke(cli.app, ["data-assemble", str(settings.projects_dir / "library"), "--mutants", str(muts)])
    assert refused.exit_code == 1


def test_cli_assemble_gives_a_clean_message_for_a_missing_or_broken_mutants_file(settings, tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    missing = runner.invoke(cli.app, ["data-assemble", str(TOY), "--mutants", str(tmp_path / "nope.jsonl")])
    assert missing.exit_code == 1 and "cannot read the mutants file" in missing.output
    assert "Traceback" not in missing.output
    broken = tmp_path / "bad.jsonl"
    broken.write_text("this is not json\n")
    result = runner.invoke(cli.app, ["data-assemble", str(TOY), "--mutants", str(broken)])
    assert result.exit_code == 1 and "cannot read the mutants file" in result.output


def test_stage_a_data_still_passes_the_validator_when_present():
    path = Path(REPO_ROOT / "data" / "stage_a.jsonl")
    if not path.exists():
        pytest.skip("run `specdrift data-stage-a` first")
    for line in path.read_text().splitlines():
        assert problems(TrainingExample.model_validate_json(line)) == []

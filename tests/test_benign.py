import ast
import json
import textwrap
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from specdrift import cli
from specdrift.bench.builder import apply_patch
from specdrift.bench.schema import Chunk, Counterexample, Evidence, Rule
from specdrift.config import REPO_ROOT
from specdrift.data import benign
from specdrift.data.assemble import assemble_project
from specdrift.data.benign import (
    CAVEATS,
    COMMENTS,
    DEAD_BRANCH_NOTES,
    OVERLAPS_BENCHMARK,
    benign_candidates,
    decoy_comment,
    decoy_dead_branch,
    decoy_docstring,
    expand_augassign,
    extract_temp,
    not_eq,
    rename_local,
    reorder_assignments,
    swap_compare_sides,
)
from specdrift.data.candidate import Candidate
from specdrift.data.inject import inject_project, make_patch
from specdrift.data.mix import MixConfig, mix
from specdrift.data.schema import Provenance, Target, TrainingExample
from specdrift.data.validate import problems

runner = CliRunner()
TOY = REPO_ROOT / "tests" / "fixtures" / "toyshop"


def lines_of(found):
    return [c.new_lines for c in found]


# ---------------------------------------------------------------- each N2 operator


def test_rename_local_renames_every_use_and_only_the_local():
    src = "def f(a, b):\n    total = a + b\n    total += 1\n    return total * 2\n"
    out = rename_local(src)
    assert [(c.line, c.end_line) for c in out] == [(2, 4)]
    assert out[0].new_lines == ["    total_value = a + b", "    total_value += 1", "    return total_value * 2"]


@pytest.mark.parametrize(
    "src",
    [
        "def f(a):\n    return a + 1\n",                                             # a parameter, and used once
        "def f(a):\n    x = 1\n    return a\n",                                      # the local is used only once
        "def f(a):\n    x = a\n    return f'{x}'\n",                                   # an f-string refers to it by name
        "def f(a):\n    x = a\n    g = lambda: x\n    return g()\n",                  # a closure captures it
        "def f(a):\n    x = a\n    return [x for _ in range(2)]\n",                  # a comprehension scope
        "def f(a):\n    global x\n    x = a\n    return x\n",
        "def f(a):\n    x = a\n    return locals()['x']\n",
        "def f(a):\n    x = a\n    def g():\n        return x\n    return g()\n",
    ],
)
def test_rename_local_leaves_alone_what_it_cannot_safely_rename(src):
    assert rename_local(src) == []


def test_rename_local_avoids_a_name_that_already_exists():
    src = "def f(a):\n    x = a\n    x_value = 1\n    return x + x_value\n"
    renamed = [c for c in rename_local(src) if "`x`" in c.description]
    assert renamed and "x_item" in renamed[0].new_lines[0]


@pytest.mark.parametrize(
    ("src", "expected"),
    [
        ("if a < limit:\n    pass\n", ["if limit > a:"]),
        ("if a >= b.c:\n    pass\n", ["if b.c <= a:"]),
        ("ok = a == 3\n", ["ok = 3 == a"]),
        ("ok = a != b\n", ["ok = b != a"]),
    ],
)
def test_swap_compare_sides(src, expected):
    assert lines_of(swap_compare_sides(src))[0] == expected


@pytest.mark.parametrize("src", ["if f(a) < b:\n    pass\n", "if a < b < c:\n    pass\n", "if a in b:\n    pass\n",
                                 "if a < a:\n    pass\n", "if x[g(1)] < b:\n    pass\n"])
def test_swap_compare_sides_leaves_calls_chains_and_identical_sides_alone(src):
    assert swap_compare_sides(src) == []


def test_not_eq():
    assert lines_of(not_eq("if a != b:\n    pass\n")) == [["if not (a == b):"]]
    assert not_eq("if f(a) != b:\n    pass\n") == []


def test_expand_augassign_only_for_a_plain_number():
    assert lines_of(expand_augassign("n += 1\nm -= 2.5\nk *= 3\n")) == [["n = n + 1"], ["m = m - 2.5"], ["k = k * 3"]]
    assert expand_augassign("items += [1]\nn += step\nflag += True\nx /= 2\nself.n += 1\n") == []


def test_extract_temp_keeps_the_value_in_a_fresh_name():
    out = extract_temp("def f(a):\n    return a * 2\n")
    assert lines_of(out) == [["    result_ = a * 2", "    return result_"]]
    assert extract_temp("def f(a):\n    return a\n") == [] and extract_temp("def f(a):\n    return a.b\n") == []
    taken = extract_temp("def f(a):\n    result_ = 1\n    return a * 2\n")
    assert lines_of(taken) == [["    out_ = a * 2", "    return out_"]]


def test_reorder_assignments_only_swaps_independent_constants_and_names():
    assert lines_of(reorder_assignments("a = 1\nb = c\n")) == [["b = c", "a = 1"]]
    assert reorder_assignments("a = 1\nb = a\n") == []              # the second reads the first
    assert reorder_assignments("a = f()\nb = 2\n") == []            # a call may have effects
    assert reorder_assignments("a = 1\na = 2\n") == []
    assert reorder_assignments("a, b = 1, 2\nc = 3\n") == []


# ---------------------------------------------------------------- each N3 operator


def test_decoy_comment_goes_above_a_statement_with_its_indent():
    out = decoy_comment("def f(a):\n    x = 1\n    return x\n")
    assert all(c.new_lines[0].startswith("    # ") and c.new_lines[1].startswith("    ") for c in out) and len(out) == 2
    assert decoy_comment('def f(a):\n    """doc"""\n    return a\n')[0].line == 3      # never above the docstring


def test_decoy_comment_never_lands_inside_a_continued_statement():
    src = "def f(a):\n    x = 1 + \\\n        2\n    return x\n"
    assert {c.line for c in decoy_comment(src)} == {2, 4}                  # statement starts only, never the continuation
    for c in decoy_comment(src):
        compile(apply_patch(src, *make_patch(src, c)), "s", "exec")


def test_decoy_docstring_extends_a_one_line_docstring_only():
    out = decoy_docstring('def f(a):\n    """Do it."""\n    return a\n')
    assert len(out) == 1 and out[0].new_lines[0].startswith('    """Do it. Caveat:') and out[0].new_lines[0].endswith('"""')
    assert decoy_docstring('def f(a):\n    """Do\n    it."""\n    return a\n') == []
    assert decoy_docstring("def f(a):\n    return a\n") == []


def test_decoy_dead_branch_never_goes_before_an_elif_or_else():
    src = "def f(a):\n    if a > 1:\n        return 1\n    elif a > 0:\n        return 2\n    else:\n        raise ValueError\n"
    assert {c.line for c in decoy_dead_branch(src)} == {2, 7}        # the opening `if` and the raise; never the elif (line 4)


def test_decoy_dead_branch_adds_an_unreachable_block_before_a_check():
    out = decoy_dead_branch("def f(a):\n    if a:\n        raise ValueError\n    return a\n")
    assert {c.line for c in out} == {2, 3} and out[0].new_lines[0].lstrip().startswith("if False:")
    assert out[0].new_lines[1].strip() == "pass" and decoy_dead_branch("def f(a):\n    return a\n") == []


# ---------------------------------------------------------------- the transformations really preserve behaviour

SAMPLE = textwrap.dedent('''\
    def classify(a, b, limit):
        """Classify a pair."""
        total = a + b
        count = 0
        flag = True
        count += 1
        if a < limit and b != 3:
            return total * 2 + count
        if a >= b:
            count -= 1
        if total > 10:
            count += 2
        elif total > 5:
            count += 3
        elif total > 0:
            count += 4
        else:
            count += 5
        return total - count if flag else 0
''')
INPUTS = [(a, b, limit) for a in (-2, 0, 3, 5) for b in (0, 3, 4) for limit in (0, 4, 6)]


def behaviour(source):
    namespace: dict = {}
    exec(compile(source, "sample", "exec"), namespace)
    return [namespace["classify"](*args) for args in INPUTS]


def test_every_n2_and_n3_candidate_preserves_behaviour_on_a_sample():
    before = behaviour(SAMPLE)
    checked = {"N2": 0, "N3": 0}
    for cand in benign_candidates(SAMPLE):
        patch = make_patch(SAMPLE, cand)
        assert patch is not None, cand
        after = apply_patch(SAMPLE, *patch)
        assert after != SAMPLE and behaviour(after) == before, (cand.operator, cand.description)
        checked[cand.category] += 1
    assert checked["N2"] >= 6 and checked["N3"] >= 6


def test_decoy_comments_do_not_change_the_syntax_tree():
    for cand in decoy_comment(SAMPLE):
        after = apply_patch(SAMPLE, *make_patch(SAMPLE, cand))
        assert ast.dump(ast.parse(after)) == ast.dump(ast.parse(SAMPLE))


def test_every_operator_is_tagged_for_benchmark_overlap():
    operators = {c.operator for c in benign_candidates(SAMPLE)}
    assert operators <= set(OVERLAPS_BENCHMARK), operators - set(OVERLAPS_BENCHMARK)
    assert any(OVERLAPS_BENCHMARK.values()) and not all(OVERLAPS_BENCHMARK.values())


# ---------------------------------------------------------------- no text copied from the benchmark's own cases


def benchmark_text():
    chunks = []
    for manifest in sorted((REPO_ROOT / "cases").glob("*.yaml")):
        for case in yaml.safe_load(manifest.read_text()):
            for key in ("find", "replace", "note"):
                value = case.get(key) or ""
                chunks.append("\n".join(value) if isinstance(value, list) else str(value))
    return "\n".join(chunks).lower()


@pytest.mark.parametrize("phrase", [*COMMENTS, *CAVEATS, *DEAD_BRANCH_NOTES])
def test_no_decoy_wording_is_copied_from_a_benchmark_case(phrase):
    text = benchmark_text()
    assert phrase.lower() not in text
    # nor do its distinctive words: the benchmark's decoys use these exact phrasings
    for banned in ("no longer enforced", "advisory only", "no-op", "currently disabled", "not applied in this build",
                   "no longer applied", "is disabled", "owns it"):
        assert banned not in phrase.lower()


def test_the_decoys_are_distinct_from_each_other():
    assert len({*COMMENTS}) == len(COMMENTS) and len({*CAVEATS}) == len(CAVEATS)


# ---------------------------------------------------------------- through the injector and assembler


@pytest.fixture(scope="module")
def mutants():
    found, _ = inject_project(TOY, "toyshop", benign=True, per_operator=20)
    return found


def test_benign_mutants_are_preserved_when_the_suite_still_passes(mutants):
    assert mutants and {m.status for m in mutants} == {"preserved"}
    assert {m.category for m in mutants} <= {"N2", "N3"} and {"N2", "N3"} <= {m.category for m in mutants}
    assert all(m.mutant_id.startswith(f"toyshop-{m.category}-") for m in mutants)


def test_a_refactor_that_breaks_the_suite_is_recorded_as_killed_not_preserved(monkeypatch):
    def breaking(source):                                   # the suite tests the age boundary, so it notices
        line = next(i for i, text in enumerate(source.splitlines(), 1) if text.strip() == "if age < MIN_AGE:")
        return [Candidate("N2", "swap_compare_sides", line, line, ["    if age <= MIN_AGE:"], "a 'refactor' that is not one")]

    monkeypatch.setattr("specdrift.data.inject.benign_candidates", breaking)
    found, _ = inject_project(TOY, "toyshop", benign=True, only=("shop.py",))
    assert [m.status for m in found] == ["killed"]


def test_benign_mutants_become_compliant_examples_for_every_covered_rule(mutants):
    examples, stats = assemble_project(TOY, "toyshop", mutants, TOY / "rules.yaml", gold_view=1.0, abstain=0.0)
    benign_examples = [e for e in examples if e.category in ("N2", "N3")]
    assert benign_examples and all(e.label == "COMPLIANT" and e.source == "hardneg" for e in benign_examples)
    assert {e.category for e in benign_examples} == {"N2", "N3"}
    assert stats["counts"]["COMPLIANT/N2"] > 0 and stats["counts"]["COMPLIANT/N3"] > 0
    for e in benign_examples:
        assert e.provenance.notes["inject_find"] and e.provenance.notes["operator"] in OVERLAPS_BENCHMARK
    # a refactor is expected to break no oracle, so it must not appear in the kill-rate table or its warning
    assert stats["oracles_that_kill_nothing"] == [] and stats["oracle_kill_rate"] == {}


def test_a_refactor_the_retriever_missed_is_recovered_with_a_view_that_shows_it(mutants):
    args = dict(gold_view=0.0, abstain=0.0, top_k=1)
    examples, stats = assemble_project(TOY, "toyshop", mutants, TOY / "rules.yaml", **args)
    golds = [e for e in examples if e.example_id.endswith("-gold") and e.category in ("N2", "N3")]
    assert golds and stats["counts"]["COMPLIANT/recovered from a retrieval miss"] == len(golds)
    for e in golds:
        symbol = next(m.symbol for m in mutants if m.mutant_id == e.provenance.notes["mutant_id"])
        assert e.label == "COMPLIANT" and e.provenance.notes["view"] == "gold"
        assert symbol in {c.qualname for c in e.chunks} and not problems(e)

    off, off_stats = assemble_project(TOY, "toyshop", mutants, TOY / "rules.yaml", gold_on_miss=False, **args)
    assert not [e for e in off if e.example_id.endswith("-gold")]
    assert off_stats["counts"]["skipped/mutated code not in view"] >= len(golds)


def test_a_decoy_that_changed_behaviour_never_becomes_a_drift_example(monkeypatch):
    def breaking_decoy(source):                      # the suite tests the age boundary, so it notices; its oracle fails too
        line = next(i for i, text in enumerate(source.splitlines(), 1) if text.strip() == "if age < MIN_AGE:")
        return [Candidate("N3", "decoy_dead_branch", line, line, ["    if age <= MIN_AGE:"], "a 'decoy' that is not one")]

    monkeypatch.setattr("specdrift.data.inject.benign_candidates", breaking_decoy)
    found, _ = inject_project(TOY, "toyshop", benign=True, only=("shop.py",))
    assert [m.status for m in found] == ["killed"]
    examples, stats = assemble_project(TOY, "toyshop", found, TOY / "rules.yaml", gold_view=1.0, abstain=0.0)
    assert not [e for e in examples if e.label == "DRIFT" or e.category in ("N2", "N3")]
    assert stats["counts"]["skipped/N3 was not behaviour-preserving"] == 1


def test_a_change_that_breaks_an_oracle_is_not_used_as_a_refactor(monkeypatch):
    def shifts_the_threshold(source):                       # the suite does not test shipping, the R04 oracle does
        line = next(i for i, text in enumerate(source.splitlines(), 1) if text.startswith("FREE_SHIPPING_AT"))
        return [Candidate("N2", "swap_compare_sides", line, line, ["FREE_SHIPPING_AT = 51"], "not really a refactor")]

    monkeypatch.setattr("specdrift.data.inject.benign_candidates", shifts_the_threshold)
    found, _ = inject_project(TOY, "toyshop", benign=True, only=("shop.py",))
    assert [m.status for m in found] == ["preserved"]          # the project's own suite cannot tell
    examples, stats = assemble_project(TOY, "toyshop", found, TOY / "rules.yaml", gold_view=1.0, abstain=0.0)
    assert not [e for e in examples if e.category == "N2" and e.rule.id == "R04"]
    assert stats["counts"]["skipped/N2 changed what a rule's oracle checks"] >= 1


# ---------------------------------------------------------------- the mixer and the command line


def _example(operator, n):
    chunk = Chunk(id="a.py::f", file="a.py", qualname="f", start_line=1, end_line=2, source=f"def f(x):\n    return x + {n}\n")
    return TrainingExample(
        example_id=f"b{n}", source="hardneg", split="train", project_id="p1", rule=Rule(id="R01", text="f MUST return x."),
        chunks=[chunk], label="COMPLIANT", category="N2", target=Target(verdict="COMPLIANT", confidence=0.9),
        provenance=Provenance(label_method="execution", generator="t", notes={"operator": operator}))


def test_the_mixer_can_hold_an_operator_family_out():
    data = [_example("rename_local", n) for n in range(20)] + [_example("not_eq", n + 100) for n in range(20)]
    other = [TrainingExample.model_validate({**e.model_dump(), "project_id": "p2", "example_id": e.example_id + "x",
                                             "rule": {"id": "R01", "text": "f MUST return x."}}) for e in data]
    _, summary = mix(data + other, MixConfig(paper_share=0, exclude_operators=("rename_local",)))
    assert summary["skipped"]["excluded operator"] == 40
    assert json.dumps(summary["splits"]).count("rename_local") == 0


def test_cli_inject_benign_flag(settings, tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    out = tmp_path / "m.jsonl"
    done = runner.invoke(cli.app, ["data-inject", str(TOY), "--benign", "--out", str(out), "--per-operator", "2"])
    assert done.exit_code == 0, done.output
    rows = [json.loads(line) for line in out.read_text().splitlines()]
    assert rows and {r["status"] for r in rows} == {"preserved"} and {r["category"] for r in rows} <= {"N2", "N3"}
    assert Path(out).exists() and benign.OVERLAPS_BENCHMARK and Evidence and Counterexample

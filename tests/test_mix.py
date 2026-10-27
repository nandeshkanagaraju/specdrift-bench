import json
import random
from collections import Counter

import pytest
from typer.testing import CliRunner

from specdrift import cli
from specdrift.bench.schema import Chunk, Counterexample, Evidence, Rule
from specdrift.config import REPO_ROOT
from specdrift.data.mix import (
    MixConfig,
    cap_per_rule,
    choose_val_projects,
    group_of,
    largest_total,
    mix,
    quotas,
)
from specdrift.data.schema import Provenance, Target, TrainingExample
from specdrift.data.validate import problems

runner = CliRunner()
MANIFEST = REPO_ROOT / "data" / "test_manifest.json"
_counter = iter(range(10**6))


def make(label, *, project="p1", rule="R01", source="synth", category="D1", operator=None, split="train",
         generator="injector-v1", text=None):
    n = next(_counter)
    chunk = Chunk(id="a.py::f", file="a.py", qualname="f", start_line=1, end_line=2,
                  source=f"def f(x):\n    return x + {n}\n")
    if label == "DRIFT":
        target = Target(verdict="DRIFT", confidence=0.9, violated_clause="f MUST return x.",
                        evidence=Evidence(file="a.py", start_line=2, end_line=2),
                        counterexample=Counterexample(input="f(1)", expected="1", actual="2"))
    else:
        target = Target(verdict=label, confidence=0.9)
    notes = {"operator": operator} if operator else {}
    return TrainingExample(
        example_id=f"e{n}", source=source, split=split, project_id=project, rule=Rule(id=rule, text=text or "f MUST return x."),
        chunks=[chunk], label=label, category=category, target=target,
        provenance=Provenance(label_method="execution", generator=generator, notes=notes))


def pool(project="p1", drift=40, compliant=60, uncertain=12, rules=4, **kw):
    out = []
    for label, n in (("DRIFT", drift), ("COMPLIANT", compliant), ("UNCERTAIN", uncertain)):
        out += [make(label, project=project, rule=f"R{i % rules + 1:02d}", **kw) for i in range(n)]
    return out


def counts(examples):
    return Counter(e.label for e in examples)


# ---------------------------------------------------------------- label shares and size


def test_the_label_shares_hit_the_target():
    out, summary = mix(pool("a") + pool("b"), MixConfig(paper_share=0, max_per_rule=100, val_fraction=0.5))
    train = out["train"]
    c = counts(train)
    assert abs(c["DRIFT"] / len(train) - 0.35) <= 1 / len(train) + 0.01
    assert abs(c["COMPLIANT"] / len(train) - 0.55) <= 0.02 and abs(c["UNCERTAIN"] / len(train) - 0.10) <= 0.02
    assert sum(summary["splits"]["train"]["labels"].values()) == len(train)


def test_the_scarcest_label_sets_the_size_and_nothing_is_padded():
    scarce = pool("a", drift=7, compliant=500, uncertain=500)
    out, summary = mix(scarce + pool("b", drift=7, compliant=500, uncertain=500),
                       MixConfig(paper_share=0, max_per_rule=500, val_fraction=0.5))
    train = out["train"]
    assert counts(train)["DRIFT"] <= 7                              # never more DRIFT than exist
    assert summary["splits"]["train"]["binding_label"]["synth"] == "DRIFT"
    assert len(train) <= 7 / 0.35 + 1


def test_largest_total_names_the_binding_label():
    assert largest_total({"DRIFT": 35, "COMPLIANT": 500, "UNCERTAIN": 500}, {"DRIFT": 0.35, "COMPLIANT": 0.55,
                                                                           "UNCERTAIN": 0.10}) == (100, "DRIFT")
    assert largest_total({"DRIFT": 500, "COMPLIANT": 500, "UNCERTAIN": 3}, {"DRIFT": 0.35, "COMPLIANT": 0.55,
                                                                          "UNCERTAIN": 0.10})[1] == "UNCERTAIN"


@pytest.mark.parametrize("total", [0, 1, 7, 100, 101, 999])
def test_quotas_always_sum_exactly(total):
    q = quotas(total, {"DRIFT": 0.35, "COMPLIANT": 0.55, "UNCERTAIN": 0.10})
    assert sum(q.values()) == total and all(v >= 0 for v in q.values())


def test_a_requested_total_caps_the_size():
    out, _ = mix(pool("a") + pool("b"), MixConfig(paper_share=0, total=20, max_per_rule=100, val_fraction=0.5))
    assert len(out["train"]) <= 20


def test_shares_must_be_valid():
    with pytest.raises(ValueError, match="sum to 1"):
        MixConfig(shares={"DRIFT": 0.5, "COMPLIANT": 0.5, "UNCERTAIN": 0.5})
    with pytest.raises(ValueError, match="paper_share"):
        MixConfig(paper_share=1.5)


# ---------------------------------------------------------------- caps and diversity


def test_no_rule_contributes_more_than_the_cap_per_label():
    capped = cap_per_rule(pool("a", drift=30, rules=1), MixConfig(max_per_rule=4), random.Random(1))
    assert counts(capped)["DRIFT"] == 4 and counts(capped)["COMPLIANT"] == 4 and counts(capped)["UNCERTAIN"] == 4


def test_a_held_out_project_stays_out_of_train():
    big, small = pool("big", drift=200, compliant=300, uncertain=60), pool("small", drift=20, compliant=30, uncertain=6)
    out, _ = mix(big + small, MixConfig(paper_share=0, max_per_rule=1000, val_projects=("small",)))
    assert {group_of(e) for e in out["train"]} == {"big"} and {group_of(e) for e in out["val"]} == {"small"}


def test_a_big_project_cannot_fill_what_the_others_cannot_supply():
    data = (pool("big", drift=200, compliant=300, uncertain=60) + pool("small", drift=20, compliant=30, uncertain=6)
            + pool("third", drift=20, compliant=30, uncertain=6))
    cfg = dict(paper_share=0, max_per_rule=1000, val_projects=("third",))

    capped, summary = mix(data, MixConfig(max_group_share=0.6, **cfg))
    share = summary["splits"]["train"]["largest_group_share"]
    assert all(v <= 0.6 + 1e-9 for v in share.values()), share
    uncapped, _ = mix(data, MixConfig(max_group_share=1.0, **cfg))
    big_share = lambda out: sum(group_of(e) == "big" for e in out["train"] if e.label == "DRIFT") / sum(  # noqa: E731
        e.label == "DRIFT" for e in out["train"])
    assert big_share(uncapped) > 0.8 > 0.6 >= big_share(capped) - 1e-9     # the cap bites
    assert len(capped["train"]) < len(uncapped["train"])                  # ... by shrinking the mix, not by padding
    assert counts(capped["train"])["DRIFT"] <= 20 / 0.4 + 1               # small's 20 is all the other side can offer


@pytest.mark.parametrize(
    ("sizes", "share", "expected"),
    [([100, 20], 0.6, 50), ([100, 100], 0.6, 200), ([100], 0.6, 100), ([100, 20], 1.0, 120), ([0, 50], 0.5, 50), ([], 0.6, 0)],
)
def test_fair_capacity(sizes, share, expected):
    from specdrift.data.mix import fair_capacity

    assert fair_capacity(sizes, share) == expected


def test_a_source_that_cannot_meet_its_shares_is_dropped_not_allowed_to_empty_the_mix():
    paper_drift_only = [make("DRIFT", project=f"paper-{i}", source="paper", generator="jin-chen-2026/mbpp",
                             category="paper:x") for i in range(30)]               # no COMPLIANT at all
    out, summary = mix(paper_drift_only + pool("a") + pool("b"), MixConfig(max_per_rule=100, val_projects=("b",)))
    assert out["train"] and not [e for e in out["train"] if e.source == "paper"]
    assert summary["splits"]["train"]["dropped_sources"] == ["paper"]


def test_one_mutation_operator_cannot_dominate_a_project():
    many = [make("DRIFT", project="a", rule="R01", operator="boundary") for _ in range(60)]
    few = [make("DRIFT", project="a", rule="R01", operator="string") for _ in range(6)]
    other = pool("b", drift=0, compliant=40, uncertain=8)
    base = [e for e in pool("a", drift=0, compliant=40, uncertain=8)]
    out, _ = mix(many + few + base + other, MixConfig(paper_share=0, max_per_rule=1000, val_projects=("b",), total=30))
    ops = Counter(e.provenance.notes.get("operator") for e in out["train"] if e.label == "DRIFT")
    assert ops["string"] >= 4 and ops["boundary"] >= 4              # both used, neither swamps the other


# ---------------------------------------------------------------- splits


def test_a_stage_b_project_lands_wholly_in_one_split_and_stage_a_keeps_its_split():
    paper = [make(lbl, project=f"paper-{lbl}-{i}", source="paper", generator="jin-chen-2026/mbpp",
                  split="val" if i % 5 == 0 else "train", category="paper:x")
             for i in range(60) for lbl in ("DRIFT", "COMPLIANT")]
    out, _ = mix(paper + pool("a") + pool("b") + pool("c"), MixConfig(max_per_rule=100, max_group_share=1.0))
    by_project: dict[str, set] = {}
    for split, examples in out.items():
        for e in examples:
            by_project.setdefault(e.project_id, set()).add(e.split)
            assert e.split == split
    assert all(len(v) == 1 for v in by_project.values())
    assert {e.split for e in out["val"] if e.source == "paper"} == {"val"}


def test_at_least_one_project_is_held_out_when_there_are_two_or_more():
    cfg = MixConfig(val_fraction=0.01)
    assert len(choose_val_projects(["a", "b"], cfg)) == 1
    assert choose_val_projects(["only"], cfg) == set()
    assert len(choose_val_projects([f"p{i}" for i in range(10)], MixConfig(val_fraction=0.3))) == 3


def test_held_out_projects_can_be_named_and_unknown_names_are_refused():
    assert choose_val_projects(["a", "b", "c"], MixConfig(val_projects=("b",))) == {"b"}
    with pytest.raises(ValueError, match="not in the data"):
        choose_val_projects(["a", "b"], MixConfig(val_projects=("zzz",)))


# ---------------------------------------------------------------- sources


def paper_pool(n=80):
    return [make(lbl, project=f"paper-{lbl}-{i}", source="paper", generator="jin-chen-2026/humaneval", category="paper:x")
            for i in range(n) for lbl in ("DRIFT", "COMPLIANT")]


def test_stage_a_takes_its_share_and_stage_b_carries_all_the_uncertain():
    out, _ = mix(paper_pool() + pool("a", drift=200, compliant=300, uncertain=100) + pool("b", drift=200, compliant=300, uncertain=100),
                 MixConfig(paper_share=0.3, max_per_rule=1000, val_projects=("b",)))
    train = out["train"]
    share = sum(e.source == "paper" for e in train) / len(train)
    assert 0.27 <= share <= 0.33
    assert not [e for e in train if e.source == "paper" and e.label == "UNCERTAIN"]
    assert abs(counts(train)["UNCERTAIN"] / len(train) - 0.10) <= 0.02          # overall, not only inside Stage B


def test_paper_share_zero_and_exclude_source_both_leave_stage_a_out():
    data = paper_pool() + pool("a") + pool("b")
    assert not [e for e in mix(data, MixConfig(paper_share=0, max_per_rule=100))[0]["train"] if e.source == "paper"]
    out, summary = mix(data, MixConfig(exclude_sources=("paper",), max_per_rule=100))
    assert not [e for s in out.values() for e in s if e.source == "paper"] and summary["skipped"]["excluded source"] == 160


def test_paper_share_one_gives_only_stage_a():
    out, _ = mix(paper_pool() + pool("a") + pool("b"), MixConfig(paper_share=1.0, max_per_rule=100))
    assert out["train"] and {e.source for e in out["train"]} == {"paper"}


# ---------------------------------------------------------------- safety


def test_invalid_examples_never_reach_the_output():
    good = pool("a") + pool("b")
    bad = make("DRIFT", project="a")
    bad = bad.model_copy(update={"target": bad.target.model_copy(update={"violated_clause": "not in the rule"})})
    assert problems(bad)
    out, summary = mix(good + [bad], MixConfig(paper_share=0, max_per_rule=100, val_fraction=0.5))
    assert summary["skipped"]["fails the validator"] == 1
    assert bad.example_id not in {e.example_id for s in out.values() for e in s}


def test_the_same_example_in_two_inputs_is_merged_but_one_id_with_two_contents_is_an_error():
    a = make("DRIFT")
    _, summary = mix([a, a] + pool("x") + pool("y"), MixConfig(paper_share=0, max_per_rule=100, val_fraction=0.5))
    assert summary["skipped"]["same example in two inputs"] == 1
    clash = a.model_copy(update={"chunks": [a.chunks[0].model_copy(update={"source": "def f(x):\n    return x + 999\n"})]})
    with pytest.raises(ValueError, match="appears twice with different content"):
        mix([a, clash], MixConfig())


def test_duplicate_content_under_a_different_id_is_dropped():
    a = make("DRIFT")
    twin = a.model_copy(update={"example_id": "another-run-same-line"})
    _, summary = mix([a, twin] + pool("x") + pool("y"), MixConfig(paper_share=0, max_per_rule=100, val_fraction=0.5))
    assert summary["skipped"]["same content as an earlier example"] == 1


def test_the_same_seed_gives_the_same_mix_and_another_seed_a_different_one():
    data = pool("a", drift=80, compliant=120, uncertain=30) + pool("b", drift=80, compliant=120, uncertain=30)
    ids = lambda cfg: [e.example_id for e in mix(data, cfg)[0]["train"]]  # noqa: E731
    base = MixConfig(paper_share=0, max_per_rule=100, val_fraction=0.5, total=40)
    assert ids(base) == ids(base) and ids(base) != ids(MixConfig(**{**base.__dict__, "seed": 99}))


# ---------------------------------------------------------------- the command line


@pytest.fixture()
def jsonl(tmp_path):
    def write(name, examples):
        path = tmp_path / name
        path.write_text("".join(e.model_dump_json() + "\n" for e in examples))
        return str(path)
    return write


@pytest.mark.skipif(not MANIFEST.exists(), reason="run `specdrift data-freeze` first")
def test_cli_writes_balanced_files_and_a_report(jsonl, tmp_path):
    inputs = [jsonl("a.jsonl", pool("a", drift=50, compliant=70, uncertain=14)),
              jsonl("b.jsonl", pool("b", drift=50, compliant=70, uncertain=14))]
    out = tmp_path / "mix"
    done = runner.invoke(cli.app, ["data-mix", *inputs, "--out", str(out), "--paper-share", "0", "--max-per-rule", "100"])
    assert done.exit_code == 0, done.output
    assert "leakage check: clean" in done.output
    train = [TrainingExample.model_validate_json(line) for line in (out / "train.jsonl").read_text().splitlines()]
    val = [TrainingExample.model_validate_json(line) for line in (out / "val.jsonl").read_text().splitlines()]
    assert train and val and not {e.project_id for e in train} & {e.project_id for e in val}
    report = json.loads((out / "mix.json").read_text())
    assert set(report["inputs"]) == set(inputs) and report["splits"]["train"]["examples"] == len(train)


@pytest.mark.skipif(not MANIFEST.exists(), reason="run `specdrift data-freeze` first")
def test_cli_refuses_and_writes_nothing_when_the_mix_overlaps_the_test_set(jsonl, tmp_path):
    leaked = [make("DRIFT", project="library") for _ in range(5)] + pool("a") + pool("b")
    out = tmp_path / "mix"
    done = runner.invoke(cli.app, ["data-mix", jsonl("x.jsonl", leaked), "--out", str(out), "--paper-share", "0",
                                   "--max-per-rule", "100"])
    assert done.exit_code == 1 and "overlaps the frozen test set" in done.output
    assert not out.exists()


def test_cli_rejects_impossible_shares(jsonl):
    done = runner.invoke(cli.app, ["data-mix", jsonl("x.jsonl", pool("a")), "--drift", "0.7", "--uncertain", "0.4"])
    assert done.exit_code == 1 and "leave room" in done.output

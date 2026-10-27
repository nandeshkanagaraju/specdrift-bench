import json
import shutil
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from specdrift import cli
from specdrift.config import REPO_ROOT
from specdrift.data.assemble import library_chunks, load_rule_map
from specdrift.data.rulegen import (
    build_oracle_prompt,
    build_rule_prompt,
    check_oracle_source,
    library_names,
    lint_rules,
    module_path,
    parse_rules_json,
    render,
    write_rules,
)
from specdrift.spec.parser import load_project_rules

runner = CliRunner()
TOY = REPO_ROOT / "tests" / "fixtures" / "toyshop"


def rule(text, symbols=("check_age",), quote="if age < MIN_AGE:", section="Customers", file="src/shop.py"):
    return {"text": text, "section": section, "symbols": list(symbols), "grounding": "code",
            "evidence": {"file": file, "quote": quote}}


GOOD = [
    rule("`check_age` MUST raise `ValueError` for an age below 18."),
    rule("`discount` MUST return 10 percent of the total for an order of 100 or more.", ("discount",),
         "if total >= 100 and rate > 0:", "Pricing"),
    rule("`shipping` MUST return 0 for a total of `FREE_SHIPPING_AT` or more.", ("shipping",),
         "if total >= FREE_SHIPPING_AT:", "Pricing"),
]


@pytest.fixture()
def project(tmp_path):
    root = tmp_path / "shop"
    shutil.copytree(TOY, root, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache", "oracles", "rules.yaml",
                                                             "spec.md"))
    return root


def dropped(rules, root):
    return [reason for _, reason in lint_rules(rules, root, "src").dropped]


# ---------------------------------------------------------------- the lint


def test_good_rules_survive(project):
    result = lint_rules(GOOD, project, "src")
    assert len(result.kept) == 3 and not result.dropped


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("`check_age` should raise `ValueError` for an age below 18.", "0 MUST"),
        ("`check_age` MUST raise `ValueError` and MUST NOT accept 17.", "2 MUST"),
        ("`check_age` MUST raise `ValueError` for 17, and `discount` MUST return 0 for 99.", "2 MUST"),
        ("`check_age` MUST properly reject minors.", "hedge"),
        ("`check_age` MUST raise `ValueError`. It MUST do so quickly.", "more than one sentence"),
        ("The tests for `check_age` MUST cover 18.", "tests"),
        (" ".join(["word"] * 41) + " MUST", "more than 40"),
    ],
)
def test_each_kind_of_bad_rule_is_dropped_with_its_reason(project, text, expected):
    reasons = dropped([rule(text)], project)
    assert reasons and expected in reasons[0], reasons


def test_the_word_test_in_ordinary_behaviour_is_not_a_reason_to_drop_a_rule(project):
    kept = lint_rules([rule("`check_age` MUST treat an age of 18 as an equality test against `MIN_AGE`.")], project, "src")
    assert len(kept.kept) == 1 and not kept.dropped
    assert "tests" in dropped([rule("The unit tests for `check_age` MUST cover 18.")], project)[0]
    assert "tests" in dropped([rule("`check_age` MUST be covered by pytest.")], project)[0]


def test_a_compound_rule_is_dropped(project):
    both = "`discount` MUST return 0 for 99, and MUST NOT return None."
    assert "2 MUST" in dropped([rule(both, ("discount",), "rate = 0.1")], project)[0]
    joined = "`discount` MUST return 0 for 99, and `shipping` returns 5."
    assert "joins" in dropped([rule(joined, ("discount",), "rate = 0.1")], project)[0]


def test_invented_symbols_and_quotes_are_caught(project):
    assert "unresolvable" in dropped([rule("`ghost` MUST return 1.", ("ghost",))], project)[0]
    assert "quote" in dropped([rule("`check_age` MUST raise `ValueError` below 18.", quote="if age < 99:")], project)[0]
    assert "quote" in dropped([rule("`check_age` MUST raise `ValueError` below 18.", file="src/missing.py")], project)[0]


def test_a_rule_is_not_kept_twice(project):
    twin = rule("`check_age` MUST raise `ValueError` for an age below 18!")
    result = lint_rules([GOOD[0], twin], project, "src")
    assert len(result.kept) == 1 and "duplicate" in result.dropped[0][1]


def test_two_rules_that_differ_in_their_boundary_are_both_kept(project):
    # distinct boundaries cite distinct lines (as `size > maxsize` and `size < 0` do in cachetools)
    larger = rule("`check_age` MUST raise `ValueError` when the age of a customer is larger than `MIN_AGE`.",
                  quote="if age < MIN_AGE:")
    negative = rule("`check_age` MUST raise `ValueError` when the age of a customer is negative.",
                    quote='raise ValueError("too young")')
    result = lint_rules([larger, negative], project, "src")
    assert len(result.kept) == 2 and not result.dropped


def test_opposite_rules_one_word_apart_are_not_duplicates_but_a_paraphrase_of_the_same_line_is(project):
    accept = rule("`discount` MUST accept an order equal to the threshold.", ("discount",), "if total >= 100 and rate > 0:")
    reject = rule("`discount` MUST reject an order equal to the threshold.", ("discount",), "rate = 0.1")
    other = rule("`discount` MUST accept an order equal to the minimum.", ("discount",), "return total * rate")
    assert len(lint_rules([accept, reject, other], project, "src").kept) == 3
    paraphrase = rule("`discount` MUST give a discount for an order at the threshold.", ("discount",),
                      "if total >= 100 and rate > 0:")
    result = lint_rules([accept, paraphrase], project, "src")
    assert len(result.kept) == 1 and "duplicate" in result.dropped[0][1]


def test_a_rule_with_no_anchor_is_kept_with_a_warning(project):
    result = lint_rules([rule("A customer MUST be checked.", ("check_age",))], project, "src")
    assert len(result.kept) == 1 and result.warnings and "no number" in result.warnings[0][1]


def test_too_few_surviving_rules_makes_a_repo_unusable(project):
    assert not lint_rules(GOOD, project, "src").usable


# ---------------------------------------------------------------- rendering


def test_rendering_gives_spec_and_rule_map_the_existing_parsers_accept(project):
    kept = lint_rules(GOOD, project, "src").kept
    ids = write_rules(project, kept, "shop")
    assert ids == ["R01", "R02", "R03"]
    rules = load_project_rules(project)
    assert [r.id for r in rules] == ids and rules[1].section == "Pricing"
    for r in rules:
        (project / "oracles" / f"test_{r.id.lower()}.py").write_text("def test_x():\n    pass\n")
    specs = load_rule_map(project / "rules.yaml", rules, project)
    assert specs["R02"].symbols == ["discount"] and specs["R02"].oracle == ("oracles/test_r02.py",)


def test_rules_are_grouped_by_section_and_numbered_after_grouping():
    mixed = [rule("`a` MUST x 1."), rule("`b` MUST y 2.", section="Other"), rule("`c` MUST z 3.")]
    for r in mixed:
        r["symbols"] = ["f"]
    spec, mapping, ordered = render(mixed, "lib")
    assert [r["text"] for r in ordered] == ["`a` MUST x 1.", "`c` MUST z 3.", "`b` MUST y 2."]
    assert spec.index("R02") < spec.index("## Other") < spec.index("R03")
    assert list(yaml.safe_load(mapping)) == ["R01", "R02", "R03"]


def test_model_output_in_code_fences_is_read():
    assert parse_rules_json('```json\n{"rules": [{"text": "x"}]}\n```') == [{"text": "x"}]
    assert parse_rules_json('[{"text": "x"}]') == [{"text": "x"}]
    with pytest.raises(ValueError):
        parse_rules_json('{"nope": 1}')


# ---------------------------------------------------------------- the prompt inputs


def test_prompt_a_lists_real_symbols_and_numbered_library_code_only(project):
    (project / "src" / "tests").mkdir()
    (project / "src" / "tests" / "test_inner.py").write_text("def test_inner():\n    assert True\n")
    system, user = build_rule_prompt(project, "shop", "src")
    assert "exactly one requirement" in system
    assert "check_age" in user and "<module>" in user and "   8 | def check_age(age):" in user
    assert "test_inner" not in user                       # tests inside the package are never library code


def test_prompt_b_gives_imports_the_script_worked_out(project):
    system, user = build_oracle_prompt(project, "R04", "`shipping` MUST return 0.", ["shipping", "<module>"], "src")
    assert "from shop import shipping" in user and "def shipping(total):" in user
    assert "exactly two shapes" in system


@pytest.mark.parametrize(
    ("rel", "subdir", "expected"),
    [("src/pkg/mod.py", "src", "pkg.mod"), ("src/pkg/__init__.py", "src", "pkg"),
     ("voluptuous/schema.py", "voluptuous", "voluptuous.schema"), ("schema.py", ".", "schema")],
)
def test_module_paths(rel, subdir, expected):
    assert module_path(rel, subdir) == expected


# ---------------------------------------------------------------- the static oracle gate


def test_the_hand_written_toy_oracles_pass_the_gate():
    names = library_names(TOY, "src")
    assert names == {"shop"}
    for path in sorted((TOY / "oracles").glob("test_r*.py")):
        assert check_oracle_source(path.read_text(), names) == [], path.name


GOOD_ORACLE = (
    "import pytest\nfrom shop import shipping, check_age\n\n\n"
    "def test_free():\n    assert shipping(50) == 0\n    assert shipping(49) == 5\n\n\n"
    "def test_minor():\n    with pytest.raises(ValueError):\n        check_age(17)\n"
)


def gate(source):
    return check_oracle_source(source, {"shop"})


def test_a_good_oracle_passes_and_arrange_then_assert_is_allowed():
    assert gate(GOOD_ORACLE) == []
    stateful = ("from shop import shipping\n\n\ndef test_a():\n    total = 50\n    shipping(total)\n"
                "    assert shipping(total) == 0\n    assert shipping(1) == 5\n")
    assert gate(stateful) == []


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("def test_a(:\n", "does not parse"),
        ("import os\nfrom shop import shipping\n\n\ndef test_a():\n    assert shipping(1) == 5\n    assert shipping(2) == 5\n", "os"),
        ("import numpy\n\n\ndef test_a():\n    assert 1 == 1\n    assert 2 == 2\n", "not the standard library"),
        ("import requests\n\n\ndef test_a():\n    assert 1 == 1\n    assert 2 == 2\n", "requests"),
        ("from shop import shipping\n\n\ndef test_a():\n    totals = [x for x in (1, 2)]\n    assert shipping(1) == 5\n    assert shipping(2) == 5\n", "ListComp"),
        ("from shop import shipping\n\n\ndef test_a():\n    f = lambda: 1\n    assert shipping(1) == 5\n    assert shipping(2) == 5\n", "Lambda"),
        ("from shop import shipping\n\n\ndef test_a():\n    import os\n    assert shipping(1) == 5\n    assert shipping(2) == 5\n", "Import"),
        ("import time\nfrom shop import shipping\n\n\ndef test_a():\n    assert shipping(1) == 5\n    assert shipping(2) == 5\n", "time"),
        ("from shop import *\n\n\ndef test_a():\n    assert shipping(1) == 5\n    assert shipping(2) == 5\n", "star"),
        ("from shop import shipping\n\n\ndef test_a():\n    assert shipping(1) == shipping(2)\n    assert shipping(1) == 5\n", "literal"),
        ("from shop import shipping\n\n\ndef test_a():\n    assert shipping(1)\n    assert shipping(1) == 5\n", "literal"),
        ("from shop import shipping\n\n\ndef test_a():\n    for x in (1, 2):\n        assert shipping(x) == 5\n", "For"),
        ("from shop import shipping\n\n\ndef test_a():\n    if True:\n        assert shipping(1) == 5\n", "If"),
        ("from shop import shipping\n\n\ndef test_a(x):\n    assert shipping(1) == 5\n    assert shipping(2) == 5\n", "arguments"),
        ("from shop import shipping\n\n\ndef helper():\n    return 1\n\n\ndef test_a():\n    assert shipping(1) == 5\n    assert shipping(2) == 5\n", "top level"),
        ("from shop import shipping\n\n\ndef test_a():\n    eval('1')\n    assert shipping(1) == 5\n    assert shipping(2) == 5\n", "eval"),
        ("from shop import shipping\n\n\ndef test_a():\n    assert shipping(1) == 5\n", "only 1 check"),
        ("import pytest\nfrom shop import check_age\n\n\ndef test_a():\n    with pytest.raises(ValueError, match='x'):\n        check_age(1)\n    assert check_age(30) is True\n", "pytest.raises"),
        ("from shop import shipping\n\n" + "\n".join(f"# {i}" for i in range(45)) + "\n\n\ndef test_a():\n    assert shipping(1) == 5\n    assert shipping(2) == 5\n", "40 lines"),
        ("x = 1\n\n\ndef test_a():\n    assert 1 == 1\n    assert 2 == 2\n", "top level"),
        ("", "no test function"),
    ],
)
def test_the_gate_names_what_is_wrong(source, expected):
    problems = gate(source)
    assert problems and any(expected in p for p in problems), problems


# ---------------------------------------------------------------- the command line


def test_cli_prompt_render_and_check(project, tmp_path):
    prompt = tmp_path / "a.txt"
    assert runner.invoke(cli.app, ["data-rulegen-prompt", str(project), "--out", str(prompt)]).exit_code == 0
    assert prompt.read_text().startswith("LIBRARY: shop") and prompt.with_suffix(".system.txt").exists()

    answer = tmp_path / "rules.json"
    answer.write_text(json.dumps({"rules": GOOD * 2}))          # 3 good rules, each twice -> duplicates dropped
    few = runner.invoke(cli.app, ["data-rulegen-render", str(project), "--rules", str(answer)])
    assert few.exit_code == 1 and "too few" in few.output and not (project / "spec.md").exists()

    more = GOOD + [rule("`check_age` MUST accept exactly 18.", quote="return True"),
                   rule("`discount` MUST return 0 for a total of 99.", ("discount",), "return 0", "Pricing"),
                   rule("`shipping` MUST return 5 for a total of 49.", ("shipping",), "return 5", "Pricing")]
    answer.write_text(json.dumps({"rules": more}))
    done = runner.invoke(cli.app, ["data-rulegen-render", str(project), "--rules", str(answer)])
    assert done.exit_code == 0, done.output
    assert (project / "spec.md").exists() and "R06" in done.output

    out = tmp_path / "b.txt"
    assert runner.invoke(cli.app, ["data-oracle-prompt", str(project), "--rule", "R01", "--out", str(out)]).exit_code == 0
    assert "RULE R01" in out.read_text()
    assert runner.invoke(cli.app, ["data-oracle-prompt", str(project), "--rule", "R99", "--out", str(out)]).exit_code == 1

    shutil.copytree(TOY / "oracles", project / "oracles", dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__"))
    ids = [r.id for r in load_project_rules(project)]
    mapping = yaml.safe_load((project / "rules.yaml").read_text())
    for rid in ids:                      # point every rule at a real, valid oracle
        mapping[rid]["oracle"] = ["oracles/test_r04.py"]
    (project / "rules.yaml").write_text(yaml.safe_dump(mapping))
    assert runner.invoke(cli.app, ["data-oracle-check", str(project)]).exit_code == 0
    (project / "oracles" / "test_r04.py").write_text("import os\n\n\ndef test_a():\n    assert 1 == 1\n    assert 2 == 2\n")
    bad = runner.invoke(cli.app, ["data-oracle-check", str(project)])
    assert bad.exit_code == 1 and "FAIL" in bad.output


def test_library_chunks_exclude_tests_inside_the_package(tmp_path):
    pkg = tmp_path / "pkg"
    (pkg / "tests").mkdir(parents=True)
    (pkg / "core.py").write_text("def f():\n    return 1\n")
    (pkg / "tests" / "test_core.py").write_text("def test_f():\n    assert True\n")
    assert {c.file for c in library_chunks(tmp_path, "pkg")} == {"pkg/core.py"}
    assert Path(pkg).exists()

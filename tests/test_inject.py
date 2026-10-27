import json
import random
import socket
import sys
import textwrap
from collections import Counter

import pytest
from typer.testing import CliRunner

from specdrift import cli
from specdrift.bench.builder import apply_patch
from specdrift.config import REPO_ROOT
from specdrift.data import inject
from specdrift.data.inject import (
    ProjectBroken,
    candidates_for,
    inject_project,
    make_patch,
    run_suite,
    sample,
    sandbox_wrap,
    token_candidates,
)

runner = CliRunner()

SHOP = textwrap.dedent('''\
    LIMIT = 3


    def check_age(age):
        if age < 18:
            raise ValueError("too young")
        return True


    def discount(total):
        rate = 0.1
        if total >= 100 and rate > 0:
            return total * rate
        return 0


    def untested(x):
        if x > 5:
            return 1
        return 0


    def total_price(price, qty):
        subtotal = price * qty
        tax = subtotal * 0.2
        return subtotal + tax
''')

SHOP_TESTS = textwrap.dedent('''\
    import pytest
    from shop import check_age, discount, total_price


    def test_adult():
        assert check_age(18) is True


    def test_minor():
        with pytest.raises(ValueError):
            check_age(17)


    def test_discount():
        assert discount(100) == 10.0
        assert discount(99) == 0


    def test_total():
        assert total_price(10, 2) == 24.0
''')


@pytest.fixture()
def shop(tmp_path):
    root = tmp_path / "shop-project"
    (root / "src").mkdir(parents=True)
    (root / "tests").mkdir()
    (root / "src" / "shop.py").write_text(SHOP)
    (root / "tests" / "test_shop.py").write_text(SHOP_TESTS)
    return root


def find(mutants, operator, contains):
    hits = [m for m in mutants if m.operator == operator and contains in m.description]
    assert len(hits) == 1, (operator, contains, [m.description for m in mutants if m.operator == operator])
    return hits[0]


# ---------------------------------------------------------------- candidate generation


@pytest.mark.parametrize(
    ("source", "category", "operator", "expected_line"),
    [
        ("if a < b:\n    pass\n", "D1", "boundary", "if a <= b:"),
        ("if a >= b:\n    pass\n", "D1", "boundary", "if a > b:"),
        ("if a and b:\n    pass\n", "D4", "and_or", "if a or b:"),
        ("if a == b:\n    pass\n", "D4", "invert_eq", "if a != b:"),
        ("x = 14\n", "D2", "constant", "x = 15"),
        ("x = 0.5\n", "D2", "constant", "x = 0.75"),
        ("def f():\n    raise KeyError('a')\n", "D6", "exception_type", "    raise ValueError('a')"),
        ("def f():\n    return True\n", "D9", "flip_bool", "    return False"),
        ("def f(y):\n    return y\n", "D9", "return_none", "    return None"),
    ],
)
def test_each_operator_makes_the_edit_it_describes(source, category, operator, expected_line):
    mine = [c for c in candidates_for(source) if c.operator == operator]
    assert len(mine) == 1 and mine[0].category == category
    assert expected_line in mine[0].new_lines


def test_operators_ignore_strings_comments_and_indexes():
    source = 'msg = "a < b and 12"  # x == y\nitems[2] = 3\n'
    found = token_candidates(source)
    assert {c.operator for c in found} == {"constant"}    # only the 3, not the string, comment or the [2]
    assert found[0].new_lines == ["items[2] = 4"]


def test_a_guard_is_dropped_only_when_the_block_has_something_else():
    only = "def f(x):\n    if x < 0:\n        raise ValueError\n"
    assert "drop_guard" not in {c.operator for c in candidates_for(only)}
    both = only + "    return x\n"
    drops = [c for c in candidates_for(both) if c.operator == "drop_guard"]
    assert len(drops) == 1 and drops[0].new_lines == []


def test_only_adjacent_simple_statements_are_swapped():
    source = "def f(a):\n    b = a + 1\n    c = b * 2\n    if c:\n        return c\n"
    swaps = [c for c in candidates_for(source) if c.operator == "swap_statements"]
    assert len(swaps) == 1
    assert swaps[0].new_lines == ["    c = b * 2", "    b = a + 1"]


# ---------------------------------------------------------------- patches


def test_a_patch_matches_exactly_once_and_changes_the_file():
    source = "def f(a):\n    if a < 1:\n        return 0\n\n\ndef g(a):\n    if a < 1:\n        return 0\n"
    boundary = [c for c in candidates_for(source) if c.operator == "boundary"]
    assert len(boundary) == 2
    for cand in boundary:
        find, replace = make_patch(source, cand)
        assert source.count(find) == 1                  # the repeated line was widened with context
        patched = apply_patch(source, find, replace)
        assert patched != source and compile(patched, "x", "exec")
    assert make_patch(source, boundary[0])[0] != make_patch(source, boundary[1])[0]


def test_sampling_is_seeded_and_capped():
    cands = token_candidates("\n".join(f"v{i} = {i + 2}" for i in range(30)))
    assert len(cands) == 30
    first = sample(cands, 4, random.Random(5))
    assert first == sample(cands, 4, random.Random(5))
    assert len(first) == 4
    assert first != sample(cands, 4, random.Random(6))

    mixed = candidates_for("a = 5\nb = 6\nc = 7\nd = 8\ne = 9\n")
    per_op = Counter(c.operator for c in sample(mixed, 2, random.Random(1)))
    assert set(per_op) == {"constant", "swap_statements", "drop_statement"}
    assert set(per_op.values()) == {2}                                # every operator is capped, whatever the set


# ---------------------------------------------------------------- labelling by running the suite


def test_mutants_are_labelled_by_what_the_projects_tests_do(shop):
    mutants, stats = inject_project(shop, "shop", per_operator=50, timeout=60)

    # tested boundary: the suite notices
    age = find(mutants, "boundary", "`<` becomes `<=`")
    assert age.status == "killed" and age.symbol == "check_age" and "test_adult" in age.failing_test
    # untested code: the suite does not, so it is *unverified*, never silently DRIFT
    untested = [m for m in mutants if m.symbol == "untested"]
    assert untested and all(m.status == "survived" for m in untested)
    # a swap that only breaks a name is a crash, not drift
    swap = find(mutants, "swap_statements", "swap places")
    assert swap.status == "crash"
    assert stats["by_status"]["killed"] >= 3 and stats["mutants"] == len(mutants)


def test_ids_are_unique_and_every_patch_replays_on_the_original(shop):
    mutants, _ = inject_project(shop, "shop", per_operator=50)
    assert len({m.mutant_id for m in mutants}) == len(mutants)
    assert all(m.mutant_id.startswith(f"shop-{m.category}-") for m in mutants)
    original = (shop / "src" / "shop.py").read_text()
    for m in mutants:
        assert apply_patch(original, m.find, m.replace) != original


def test_the_run_is_reproducible(shop):
    a, _ = inject_project(shop, "shop", per_operator=2, seed=3)
    b, _ = inject_project(shop, "shop", per_operator=2, seed=3)
    assert [m.model_dump() for m in a] == [m.model_dump() for m in b]


def test_the_original_project_is_never_modified(shop):
    before = (shop / "src" / "shop.py").read_text()
    inject_project(shop, "shop", per_operator=50)
    assert (shop / "src" / "shop.py").read_text() == before
    assert not list(shop.rglob("__pycache__"))


def test_a_project_that_fails_its_own_tests_is_refused(shop):
    (shop / "tests" / "test_shop.py").write_text(SHOP_TESTS.replace("== 24.0", "== 99.0"))
    with pytest.raises(ProjectBroken):
        inject_project(shop, "shop")


def test_the_test_set_cannot_be_used_as_a_source(shop):
    with pytest.raises(ValueError, match="test set"):
        inject_project(shop, "shop", protected_roots=[shop.parent])
    inject_project(shop, "shop", protected_roots=[shop.parent], allow_test_project=True, per_operator=1)


def test_a_hanging_suite_is_a_timeout_not_a_hang(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_slow.py").write_text("import time\n\ndef test_slow():\n    time.sleep(30)\n")
    status, _, message, _ = run_suite(tmp_path, timeout=1.5, mode="off")
    assert status == "timeout" and "time limit" in message


# ---------------------------------------------------------------- the sandbox


@pytest.mark.skipif(sys.platform != "darwin", reason="sandbox-exec is macOS only")
def test_the_sandbox_blocks_the_network_the_unsandboxed_run_can_use(tmp_path):
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    port = server.getsockname()[1]
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_net.py").write_text(
        f"import socket\n\ndef test_net():\n    socket.create_connection(('127.0.0.1', {port}), 2).close()\n"
    )
    try:
        assert run_suite(tmp_path, 30, "off")[0] == "passed"
        status, _, _, sandboxed = run_suite(tmp_path, 30, "auto")
        assert sandboxed and status != "passed"
    finally:
        server.close()


def test_require_mode_refuses_when_no_sandbox_exists(monkeypatch):
    monkeypatch.setattr(inject.shutil, "which", lambda name: None)
    monkeypatch.setattr(inject.sys, "platform", "linux")
    assert sandbox_wrap(["x"], "auto") == (["x"], False)
    with pytest.raises(RuntimeError, match="sandbox"):
        sandbox_wrap(["x"], "require")


# ---------------------------------------------------------------- a real host project, as a smoke test


def test_a_real_project_gives_killed_and_surviving_mutants():
    mutants, stats = inject_project(
        REPO_ROOT / "projects" / "ratelimiter", "ratelimiter", per_operator=1, allow_test_project=True
    )
    assert stats["by_status"].get("killed", 0) >= 3
    assert {m.category for m in mutants} >= {"D1", "D2"}
    assert all(m.status != "invalid" for m in mutants)


# ---------------------------------------------------------------- the command line


def test_cli_writes_mutants_and_refuses_the_test_set(shop, settings, tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    out = tmp_path / "out" / "shop.jsonl"
    done = runner.invoke(cli.app, ["data-inject", str(shop), "--out", str(out), "--per-operator", "2"])
    assert done.exit_code == 0, done.output
    rows = [json.loads(line) for line in out.read_text().splitlines()]
    assert rows and {"find", "replace", "status", "symbol"} <= set(rows[0])
    assert json.loads(out.with_suffix(".stats.json").read_text())["mutants"] == len(rows)

    refused = runner.invoke(cli.app, ["data-inject", str(settings.projects_dir / "library")])
    assert refused.exit_code == 1 and "test set" in refused.output


def test_a_crash_is_still_a_crash_when_pytest_truncates_the_message(tmp_path):
    # pytest cuts the summary line to the terminal width, so "UnboundLocalError" can arrive as "Unbou..."
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src" / "calc.py").write_text(
        "def total(price, qty):\n    subtotal = price * qty\n    tax = subtotal * 0.2\n    return subtotal + tax\n"
    )
    long_name = "test_the_total_includes_tax_for_a_typical_order_of_several_items_at_a_typical_unit_price_ok"
    (tmp_path / "tests" / "test_calc.py").write_text(
        f"from calc import total\n\n\ndef {long_name}():\n    assert total(10, 2) == 24.0\n"
    )
    mutants, _ = inject_project(tmp_path, "calc", per_operator=50)
    swap = find(mutants, "swap_statements", "swap places")
    assert swap.status == "crash", (swap.status, swap.failure_message)


def test_only_the_named_files_are_mutated(shop):
    (shop / "src" / "other.py").write_text("def g(a):\n    if a < 3:\n        return 1\n    return 0\n")
    both, _ = inject_project(shop, "shop", per_operator=50)
    just, _ = inject_project(shop, "shop", per_operator=50, only=("shop.py",))
    assert {m.file for m in both} == {"src/shop.py", "src/other.py"}
    assert {m.file for m in just} == {"src/shop.py"}


def test_focus_mutates_only_the_cited_lines_and_all_of_them(shop):
    from specdrift.data.inject import focus_lines

    source = (shop / "src" / "shop.py").read_text()
    assert focus_lines(source, ["if   age <  18:"]) == {5}          # whitespace-insensitive
    assert focus_lines(source, ["nothing like this"]) == set() and focus_lines(source, ["", "  "]) == set()

    mutants, _ = inject_project(shop, "shop", focus={"src/shop.py": ["if age < 18:", "if total >= 100 and rate > 0:"]})
    assert {m.line for m in mutants} == {5, 12}                       # lines 5 and 12 of SHOP, nothing else
    ops = {(m.line, m.operator) for m in mutants}
    assert {(5, "boundary"), (5, "constant"), (12, "boundary"), (12, "and_or"), (12, "constant")} <= ops

    capped, _ = inject_project(shop, "shop", per_operator=1)
    assert len(mutants) != len(capped)                                # not the sampled set


def test_focus_skips_files_no_rule_cites(shop):
    (shop / "src" / "other.py").write_text("def g(a):\n    if a < 3:\n        return 1\n    return 0\n")
    mutants, _ = inject_project(shop, "shop", focus={"src/shop.py": ["if age < 18:"]})
    assert {m.file for m in mutants} == {"src/shop.py"}


def test_cli_focus_rules_reads_evidence_from_the_rules_json(shop, settings, tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    rules = tmp_path / "rules.json"
    rules.write_text(json.dumps({"rules": [{"evidence": {"file": "src/shop.py", "quote": "if age < 18:"}}]}))
    out = tmp_path / "m.jsonl"
    done = runner.invoke(cli.app, ["data-inject", str(shop), "--focus-rules", str(rules), "--out", str(out)])
    assert done.exit_code == 0, done.output
    assert {json.loads(line)["line"] for line in out.read_text().splitlines()} == {5}


# ---------------------------------------------------------------- operators added after the pilot


def edits(source, operator):
    return [c.new_lines for c in candidates_for(source) if c.operator == operator]


@pytest.mark.parametrize(
    ("source", "operator", "expected"),
    [
        ("if not flag:\n    pass\n", "drop_not", [["if flag:"]]),
        ("if a is None:\n    pass\n", "flip_is", [["if a is not None:"]]),
        ("if a is not None:\n    pass\n", "flip_is", [["if a is None:"]]),
        ("ok = key in cache\n", "flip_in", [["ok = key not in cache"]]),
        ("ok = key not in cache\n", "flip_in", [["ok = key in cache"]]),
        ("x = a + b\n", "arith", [["x = a - b"]]),
        ("x = a - 1\n", "arith", [["x = a + 1"]]),
        ("total += 1\n", "arith", [["total -= 1"]]),
        ('prefix = "=="\n', "string", [['prefix = "==x"']]),
        ("def f(a):\n    return a.get(1)\n", "return_none_expr", [["    return None"]]),
        ("x(a, b)\ny = 1\n", "swap_args", [["x(b, a)"]]),
        ("def f():\n    if flag:\n        self.touch(key)\n", "pass_statement", [["        pass"]]),
        ("if flag:\n    x = 1\n", "invert_condition", [["if not (flag):"]]),
        ("if a > b and c:\n    x = 1\n", "invert_condition", [["if not (a > b and c):"]]),
        ("if x:\n    pass\nelif y:\n    pass\n", "invert_condition", [["if not (x):"], ["elif not (y):"]]),
    ],
)
def test_each_new_operator_makes_the_edit_it_describes(source, operator, expected):
    assert edits(source, operator) == expected


@pytest.mark.parametrize(
    ("source", "operator"),
    [
        ("x = -a\n", "arith"),                                   # unary minus is not a subtraction
        ("x = a ** -1\n", "arith"),
        ("x = [i for i in items]\n", "flip_in"),                 # a comprehension is not a membership test
        ("for i in items:\n    pass\n", "flip_in"),
        ('def f():\n    """A docstring."""\n    return 1\n', "string"),
        ("def f():\n    'short doc'\n    return 1\n", "string"),   # a string standing alone is a docstring
        ('x = f"hello {a}"\n', "string"),
        ('x = b"bytes"\n', "string"),
        ('x = r"a.b"\n', "string"),
        ('raise ValueError("bad value")\n', "string"),
        ('warn("careful")\n', "string"),
        ('x = "' + "a" * 41 + '"\n', "string"),
        ("def f(a):\n    return a\n", "return_none_expr"),      # a bare name is `return_none`, not this
        ("def f():\n    return None\n", "return_none_expr"),
        ("def f():\n    return True\n", "return_none_expr"),
        ("isinstance(a, b)\ny = 1\n", "swap_args"),             # would only raise TypeError
        ("x(a)\ny = 1\n", "swap_args"),
        ("x(a, a)\ny = 1\n", "swap_args"),                      # swapping identical text changes nothing
        ("x(*a, b)\ny = 1\n", "swap_args"),
        ("def f():\n    x = 1\n", "drop_statement"),            # the only statement would leave an empty block
        ("if True:\n    x = 1\n", "invert_condition"),                # a constant condition is not a rule
        ("if (a and\n        b):\n    x = 1\n", "invert_condition"),     # multi-line conditions are left alone
        ("def f():\n    x = 1\n", "drop_statement"),
        ("def f(a):\n    if a:\n        return 1\n", "pass_statement"),   # a return is not a droppable statement
        ("def f():\n    return 1\n    pass\n", "drop_statement"),
    ],
)
def test_new_operators_leave_alone_what_they_should(source, operator):
    assert edits(source, operator) == []


def test_a_dunder_assignment_is_never_dropped():
    lines = [c.line for c in candidates_for("__all__ = ['a']\ny = 1\n") if c.operator == "drop_statement"]
    assert lines == [2]


def test_drop_statement_removes_calls_and_assignments_but_not_returns_or_ifs():
    source = "def f(a):\n    a.touch()\n    b = 1\n    c += 2\n    if a:\n        pass\n    return b\n"
    dropped = [c.line for c in candidates_for(source) if c.operator == "drop_statement"]
    assert dropped == [2, 3, 4]


def test_non_ascii_lines_are_never_edited_by_column_arithmetic():
    source = 'def f(a):\n    return g("é", a)\n'
    assert edits(source, "return_none_expr") == [] and edits(source, "swap_args") == []


def test_every_new_patch_still_compiles_on_a_realistic_module():
    from pathlib import Path

    source = (REPO_ROOT / "tests" / "fixtures" / "toyshop" / "src" / "shop.py").read_text()
    new = {"drop_not", "flip_is", "flip_in", "arith", "string", "return_none_expr", "drop_statement", "swap_args"}
    bad = []
    for cand in candidates_for(source):
        if cand.operator in new:
            patch = make_patch(source, cand)
            if patch is not None:
                try:
                    compile(apply_patch(source, *patch), "shop.py", "exec")
                except SyntaxError:
                    bad.append((cand.operator, cand.line))
    assert not bad, bad
    assert Path(REPO_ROOT / "pyproject.toml").exists()


# ---------------------------------------------------------------- operators added after the iniconfig pilot


@pytest.mark.parametrize(
    ("source", "operator", "expected"),
    [
        ("def f(a, strict=True):\n    pass\n", "flip_bool_arg", [["def f(a, strict=False):"]]),
        ("def f(*, flag=False):\n    pass\n", "flip_bool_arg", [["def f(*, flag=True):"]]),
        ("def f(\n    x: bool = True,\n):\n    pass\n", "flip_bool_arg", [["    x: bool = False,"]]),
        ("run(a, check=True)\n", "flip_bool_arg", [["run(a, check=False)"]]),
        ("sorted(items, key=len)\n", "drop_key_arg", [["sorted(items)"]]),
        ("x = sorted(items, key=len, reverse=True)\n", "drop_key_arg", [["x = sorted(items, reverse=True)"]]),
        ("max(a, b, key=abs)\n", "drop_key_arg", [["max(a, b)"]]),
        ("for n in sorted(self.d, key=self.lineof):  # type: ignore\n    pass\n", "drop_key_arg",
         [["for n in sorted(self.d):  # type: ignore"]]),
        ("x = line[1:-1]\n", "shift_slice", [["x = line[2:-1]"], ["x = line[1:-2]"]]),
        ("x = s[:3]\n", "shift_slice", [["x = s[:4]"]]),
        ("x = s[0:]\n", "shift_slice", [["x = s[1:]"]]),
    ],
)
def test_each_iniconfig_operator_makes_the_edit_it_describes(source, operator, expected):
    assert edits(source, operator) == expected


@pytest.mark.parametrize(
    ("source", "operator"),
    [
        ("x = f(a=1)\n", "flip_bool_arg"),                          # a number is the `constant` operator's
        ("x = f(a=None)\n", "flip_bool_arg"),
        ("x = f(a=flag)\n", "flip_bool_arg"),
        ("def f(a=(True, 1)):\n    pass\n", "flip_bool_arg"),        # only a bare boolean, not one inside a tuple
        ("def f(a):\n    pass\n", "flip_bool_arg"),
        ('x = f("é", ok=True)\n', "flip_bool_arg"),                  # column arithmetic is unsafe on non-ASCII lines
        ("sorted(items)\n", "drop_key_arg"),
        ("foo(items, key=len)\n", "drop_key_arg"),                  # only functions where `key` is a sort key
        ("items.sort(key=len)\n", "drop_key_arg"),                  # nothing before it to cut the comma from
        ("sorted(\n    items, key=len\n)\n", "drop_key_arg"),       # a call spanning lines is left alone
        ('sorted(["é"], key=len)\n', "drop_key_arg"),
        ("x = s[a:b]\n", "shift_slice"),
        ("x = s[::2]\n", "shift_slice"),                             # the step is not a boundary
        ("x = s[i]\n", "shift_slice"),                               # an index, not a slice
        ("x = s[True:]\n", "shift_slice"),
        ('x = s[1:"é"]\n', "shift_slice"),
    ],
)
def test_iniconfig_operators_leave_alone_what_they_should(source, operator):
    assert edits(source, operator) == []


def test_iniconfig_operators_are_filed_under_the_categories_they_belong_to():
    source = "def f(a=True):\n    return sorted(a, key=len)[1:]\n"
    cats = {c.operator: c.category for c in candidates_for(source)}
    assert cats["flip_bool_arg"] == "D2" and cats["drop_key_arg"] == "D3" and cats["shift_slice"] == "D1"


def test_flip_bool_arg_names_the_parameter_or_keyword_it_changes():
    def described(source):
        return sorted(c.description for c in candidates_for(source) if c.operator == "flip_bool_arg")

    assert described("def f(a, b=1, strict=True, *, flag=False):\n    pass\n") == [
        "the default of `flag` becomes True", "the default of `strict` becomes False"]
    assert described("run(a, check=True)\n") == ["`check=` becomes False"]


def test_every_iniconfig_patch_applies_and_compiles():
    source = "def f(a, strict=True):\n    items = sorted(a, key=len)\n    return items[1:-1], strict\n"
    seen = set()
    for cand in candidates_for(source):
        if cand.operator in {"flip_bool_arg", "drop_key_arg", "shift_slice"}:
            find, replace = make_patch(source, cand)
            compile(apply_patch(source, find, replace), "m.py", "exec")
            seen.add(cand.operator)
    assert seen == {"flip_bool_arg", "drop_key_arg", "shift_slice"}


# ---------------------------------------------------------------- pytest ids with spaces


def test_a_failure_in_a_test_whose_id_has_spaces_is_a_kill_not_a_crash():
    out = ("FAILED testing/test_iniconfig.py::test_tokenize[assignment in value] - AssertionError: assert [] == "
           "[PL(0, None, 'value', ['x = 3'])]\n1 failed in 0.03s\n")
    run = inject.classify_run(1, out, "")
    assert run.status == "killed"
    assert run.test == "testing/test_iniconfig.py::test_tokenize[assignment in value]"
    assert run.message.startswith("AssertionError: assert [] ==")


@pytest.mark.parametrize(
    ("line", "test", "message"),
    [
        # The exact lines pytest 9.1 printed for a unittest `self.subTest` and for the `subtests` fixture.
        ("SUBFAILED[case 2] test_unit.py::T::test_sub - AssertionError: 2 == 2",
         "test_unit.py::T::test_sub", "AssertionError: 2 == 2"),
        ("SUBFAILED(n=2) test_unit.py::T::test_sub_kwargs - AssertionError: 2 == 2",
         "test_unit.py::T::test_sub_kwargs", "AssertionError: 2 == 2"),
        ("SUBFAILED[case 2] (n=2) test_sub.py::test_with_subtests - AssertionError: two is wrong",
         "test_sub.py::test_with_subtests", "AssertionError: two is wrong"),
        ("SUBFAILED[a - b] (n=(1, 2)) tests/test_data.py::TestData::test_valid[x y] - AssertionError: no",
         "tests/test_data.py::TestData::test_valid[x y]", "AssertionError: no"),
    ],
)
def test_a_failed_subtest_is_a_kill_even_though_its_parent_test_passes(line, test, message):
    run = inject.classify_run(1, line + "\n2 failed, 54 passed, 514 subtests passed in 0.16s\n", "")
    assert (run.status, run.test, run.message) == ("killed", test, message)


def test_a_subtest_that_fails_with_a_crash_error_is_still_a_crash():
    line = "SUBFAILED[case 2] tests/test_data.py::TestData::test_valid - NameError: name 'x' is not defined\n"
    assert inject.classify_run(1, line, "").status == "crash"


def test_the_summary_line_alone_is_still_unparseable():
    assert inject.classify_run(1, "2 failed, 54 passed, 514 subtests passed in 0.16s\n", "").status == "crash"


def test_ids_without_spaces_and_without_a_message_still_parse():
    plain = inject.classify_run(1, "FAILED tests/test_a.py::test_x - assert 1 == 2\n", "")
    assert (plain.status, plain.test, plain.message) == ("killed", "tests/test_a.py::test_x", "assert 1 == 2")
    bare = inject.classify_run(1, "FAILED tests/test_a.py::test_x\n", "")
    assert (bare.status, bare.test, bare.message) == ("killed", "tests/test_a.py::test_x", "")


def test_genuine_crashes_are_still_crashes():
    named = inject.classify_run(
        1, "FAILED tests/test_a.py::test_x[a b] - UnboundLocalError: cannot access local variable 'sources'\n", "")
    assert named.status == "crash" and named.test == "tests/test_a.py::test_x[a b]"
    assert inject.classify_run(1, "1 failed in 0.03s\n", "").status == "crash"           # nothing to parse
    assert inject.classify_run(2, "FAILED tests/test_a.py::test_x - assert 1 == 2\n", "").status == "crash"
    assert inject.classify_run(0, "", "").status == "passed"


def test_a_collection_error_with_no_test_id_is_a_crash():
    out = "FAILED tests/test_a.py - ImportError: cannot import name 'x'\n"
    run = inject.classify_run(1, out, "")
    assert run.status == "crash" and run.message.startswith("ImportError")


def test_the_injector_kills_a_mutant_on_a_project_whose_failing_test_has_spaces_in_its_id(tmp_path):
    root = tmp_path / "p"
    (root / "src").mkdir(parents=True)
    (root / "tests").mkdir()
    (root / "src" / "m.py").write_text("def double(x):\n    return x * 2\n")
    (root / "tests" / "test_m.py").write_text(
        "import pytest\nfrom m import double\n\n\n"
        "@pytest.mark.parametrize('x', [3], ids=['a case with spaces'])\n"
        "def test_double(x):\n    assert double(x) == 6\n"
    )
    mutants, _ = inject_project(root, "p", per_operator=50)

    assert mutants and {m.status for m in mutants} == {"killed"}
    assert all("a case with spaces" in m.failing_test for m in mutants)


def test_the_injector_kills_a_mutant_on_a_project_whose_tests_use_unittest_subtests(tmp_path):
    root = tmp_path / "p"
    (root / "src").mkdir(parents=True)
    (root / "tests").mkdir()
    (root / "src" / "m.py").write_text("def double(x):\n    return x * 2\n")
    (root / "tests" / "test_m.py").write_text(
        "import unittest\nfrom m import double\n\n\n"
        "class T(unittest.TestCase):\n"
        "    def test_double(self):\n"
        "        for n in (3, 4):\n"
        "            with self.subTest(msg=f'case {n}'):\n"
        "                self.assertEqual(double(n), n * 2)\n"
    )
    mutants, _ = inject_project(root, "p", per_operator=50)

    assert mutants and {m.status for m in mutants} == {"killed"}
    assert all(m.failing_test.endswith("T::test_double") for m in mutants)

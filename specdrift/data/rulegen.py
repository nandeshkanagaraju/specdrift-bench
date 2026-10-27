"""Stage B, step 2: everything around the rule and oracle prompts except the model call itself.

docs/rule-extraction-prompt.md is the design. The model returns JSON; this module builds the prompt,
lints what comes back, and renders `spec.md` and `rules.yaml` deterministically, so no model ever writes
a file that something else has to parse. It also holds the static gate every oracle must pass.
"""

from __future__ import annotations

import ast
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from specdrift.bench.schema import Chunk
from specdrift.data.assemble import library_chunks
from specdrift.data.leakage import norm_text, rules_are_near
from specdrift.data.stage_a import _BANNED_CALLS, _BANNED_MODULES

RULE_PROMPT_VERSION = "v0"
ORACLE_PROMPT_VERSION = "v0.1"
MIN_RULES = 6
# Edit distance cannot tell a paraphrase from an opposite rule: "accept a value equal to `min`" and "reject a
# value equal to `min`" are 0.09 apart, `min` against `max` three characters. Two rules are duplicates when they
# cite the same symbols and the same line of code, or are almost the same text (punctuation, a stray word).
DUPLICATE_DISTANCE = 0.03
MAX_WORDS = 40
README_CHARS = 6000
ORACLE_MAX_LINES = 40
ORACLE_MIN_CHECKS = 2

RULE_SYSTEM = """You write a specification for an existing Python library, as a list of short, testable rules. A reader will
later decide, for each rule, whether a changed version of the code still obeys it, so every rule must be
something a test could check by running the code.

Write a rule only when the code or the README states or clearly implies it. Do not invent behaviour. Do not
describe how the code is organised, how fast it is, how it logs, or how it is formatted.

A good rule:
- has exactly one requirement, using MUST or MUST NOT once;
- states a concrete value, a named exception, a boundary (at least, more than, exactly), an ordering
  (before, only after), or a returned shape, so a one-character change to the code would break it;
- names the public function or class it is about in backticks;
- is one sentence, at most 40 words.

A bad rule is vague ("handles errors properly"), a restatement of a function name ("`parse` parses input"),
a list of several requirements joined by "and", or about internals no caller can observe.

Prefer rules about: limits and thresholds, defaults, error conditions and the exception raised, argument
validation, ordering of steps, what is returned for empty or edge input, and units or rounding.

Return JSON only, matching the schema. Write between 8 and 20 rules. If the library has fewer than 8 such
behaviours, write fewer; never pad."""

RULE_USER = """LIBRARY: {name}

README:
{readme}

SOURCE FILES (with line numbers):
{sources}

RESOLVABLE SYMBOLS (use only these in "symbols"):
{symbols}

Return:
{{
  "rules": [
    {{
      "text": "<one sentence, one MUST or MUST NOT>",
      "section": "<2-4 word topic heading>",
      "symbols": ["<symbol from the list>"],
      "grounding": "documented" | "code",
      "evidence": {{"file": "<path>", "quote": "<one line copied exactly from that file>"}}
    }}
  ]
}}"""

ORACLE_SYSTEM = """You write a pytest file that decides whether a Python library still obeys ONE specification rule.
The file will be run against the original code, where it must pass, and against slightly changed copies of the
code, where it must fail if the change breaks the rule. A one-character change (a comparison operator, a constant,
a deleted check, a different exception) must make it fail.

Requirements:
- Test only what the rule says. Do not assert anything the rule does not state, even if the code does it.
- For every number or boundary in the rule, test the value exactly at the boundary and one step on each side.
- Use only the public names in the symbol list, imported exactly as shown.
- A test may first set things up with plain assignments and single calls, then check with exactly two shapes:
    assert <expression> == <literal>          (or `is True`, `is False`, `is None`)
    with pytest.raises(<ExceptionName>):
        <one call expression>
  The expected value must be written out as a literal; never compute it by calling the code under test.
- No loops, conditionals, helper functions, classes, lambdas, comprehensions, try blocks or imports inside a test.
- Each test function checks one thing and has a name that says what.
- No network, files, clock, randomness, sleeping, mocks, fixtures or parametrize.
- At most 40 lines, imports included. No comments.

Return only the Python source of the file."""

ORACLE_USER = """RULE {rule_id}: {text}

IMPORT AS:
{imports}

CODE THE RULE IS ABOUT:
{code}

Write the pytest file."""

HEDGES = re.compile(
    r"\b(should|may|might|usually|typically|generally|appropriate|properly|correctly|reasonable|efficient|"
    r"gracefully|as expected)\b", re.IGNORECASE)
ORDERING = re.compile(r"\b(before|after|only|first|then)\b", re.IGNORECASE)
MODAL = re.compile(r"\bMUST NOT\b|\bMUST\b")
COMPOUND = re.compile(r",\s+and\s|\band\s+MUST\b")
# The test suite, not the word: "an equality test" is behaviour, "the tests for X" is not.
ABOUT_TESTS = re.compile(r"\b(the tests?|tests? (suite|cases?|for|of)|unit tests?|fixtures?|mocks?|pytest)\b", re.IGNORECASE)
NO_ORACLE_MODULES = _BANNED_MODULES | {"time", "random", "tempfile", "logging"}


# --------------------------------------------------------------------------- prompt A inputs


def readme_text(root: Path) -> str:
    for name in ("README.md", "README.rst", "README.txt", "README"):
        path = root / name
        if path.is_file():
            return path.read_text(encoding="utf-8", errors="replace")[:README_CHARS]
    return "(no README)"


def numbered_sources(root: Path, chunks: list[Chunk]) -> str:
    files = sorted({c.file for c in chunks})
    blocks = []
    for rel in files:
        lines = (root / rel).read_text(encoding="utf-8", errors="replace").splitlines()
        blocks.append(f"=== {rel} ===\n" + "\n".join(f"{i:>4} | {line}" for i, line in enumerate(lines, 1)))
    return "\n\n".join(blocks)


def build_rule_prompt(root: Path, name: str, subdir: str) -> tuple[str, str]:
    chunks = library_chunks(root, subdir)
    symbols = sorted({c.qualname for c in chunks})
    user = RULE_USER.format(name=name, readme=readme_text(root), sources=numbered_sources(root, chunks),
                            symbols="\n".join(symbols))
    return RULE_SYSTEM, user


def module_path(rel: str, subdir: str) -> str:
    """src/pkg/mod.py -> pkg.mod ; pkg/__init__.py -> pkg ; flat layouts keep the package dir."""
    parts = rel[:-3].split("/")
    if parts and parts[0] == subdir and subdir == "src":
        parts = parts[1:]
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def build_oracle_prompt(root: Path, rule_id: str, text: str, symbols: list[str], subdir: str) -> tuple[str, str]:
    chunks = [c for c in library_chunks(root, subdir) if c.qualname in symbols]
    imports = sorted({
        f"from {module_path(c.file, subdir)} import {c.qualname.split('.')[0]}"
        for c in chunks if c.qualname != "<module>"
    })
    code = "\n\n".join(f"# {c.file}\n{c.source}" for c in chunks)
    return ORACLE_SYSTEM, ORACLE_USER.format(rule_id=rule_id, text=text, imports="\n".join(imports) or "(none)",
                                             code=code)


# --------------------------------------------------------------------------- reading and linting rules


def parse_rules_json(text: str) -> list[dict]:
    cleaned = re.sub(r"^\s*```(?:json)?\s*|\s*```\s*$", "", text.strip())
    data = json.loads(cleaned)
    rules = data.get("rules") if isinstance(data, dict) else data
    if not isinstance(rules, list):
        raise ValueError('expected {"rules": [...]}')
    return rules


@dataclass
class Lint:
    kept: list[dict] = field(default_factory=list)
    dropped: list[tuple[dict, str]] = field(default_factory=list)
    warnings: list[tuple[dict, str]] = field(default_factory=list)

    @property
    def usable(self) -> bool:
        return len(self.kept) >= MIN_RULES


def _flat(text: str) -> str:
    return " ".join(text.split())


def lint_rules(rules: list[dict], root: Path, subdir: str) -> Lint:
    chunks = library_chunks(root, subdir)
    known = {c.qualname for c in chunks}
    result = Lint()
    seen: list[tuple[str, frozenset[str], str]] = []

    for rule in rules:
        text = _flat(str(rule.get("text", "")))
        symbols = rule.get("symbols") or []
        evidence = rule.get("evidence") or {}
        reason = ""

        if not text or len(text.split()) > MAX_WORDS:
            reason = f"empty or more than {MAX_WORDS} words"
        elif len(re.split(r"(?<=[.!?])\s+(?=[A-Z])", text)) > 1:
            reason = "more than one sentence"
        elif len(MODAL.findall(text)) != 1:
            reason = f"{len(MODAL.findall(text))} MUST/MUST NOT, needs exactly one"
        elif COMPOUND.search(text):
            reason = "joins two requirements"
        elif HEDGES.search(text):
            reason = f"hedge word: {HEDGES.search(text).group(0)}"  # type: ignore[union-attr]
        elif ABOUT_TESTS.search(text):
            reason = "is about tests, not behaviour"
        elif not symbols or any(s not in known for s in symbols):
            reason = f"unresolvable symbol(s): {[s for s in symbols if s not in known]}"
        else:
            quote, rel = _flat(str(evidence.get("quote", ""))), str(evidence.get("file", ""))
            target = root / rel
            if not quote or not target.is_file() or quote not in _flat(target.read_text(encoding="utf-8",
                                                                                          errors="replace")):
                reason = "evidence quote is not in the named file"
            elif any(
                (frozenset(symbols) == syms and quote == cited) or rules_are_near(norm_text(text), earlier, DUPLICATE_DISTANCE)
                for earlier, syms, cited in seen
            ):
                reason = "duplicate of an earlier rule (same symbols and cited line, or nearly the same text)"

        if reason:
            result.dropped.append((rule, reason))
            continue
        if not (re.search(r"\d", text) or "`" in text or '"' in text or ORDERING.search(text)):
            result.warnings.append((rule, "no number, identifier, quoted string or ordering word"))
        seen.append((norm_text(text), frozenset(symbols), _flat(str(evidence.get("quote", "")))))
        result.kept.append(rule)
    return result


def render(kept: list[dict], name: str) -> tuple[str, str, list[dict]]:
    """spec.md text, rules.yaml text and the rules in id order. Rules are grouped by section."""
    sections: dict[str, list[dict]] = {}
    for rule in kept:
        sections.setdefault(str(rule.get("section") or "Behaviour").strip(), []).append(rule)

    lines = [f"# {name} specification", ""]
    ordered: list[dict] = []
    entries: dict[str, dict] = {}
    for section, group in sections.items():
        lines += [f"## {section}", ""]
        for rule in group:
            rule_id = f"R{len(ordered) + 1:02d}"
            lines.append(f"- **{rule_id}** {_flat(rule['text'])}")
            entries[rule_id] = {"symbols": list(rule["symbols"]), "oracle": [f"oracles/test_{rule_id.lower()}.py"]}
            ordered.append(rule)
        lines.append("")
    return "\n".join(lines), yaml.safe_dump(entries, sort_keys=False), ordered


def write_rules(root: Path, kept: list[dict], name: str) -> list[str]:
    spec, rules_yaml, ordered = render(kept, name)
    (root / "spec.md").write_text(spec, encoding="utf-8")
    (root / "rules.yaml").write_text(rules_yaml, encoding="utf-8")
    (root / "oracles").mkdir(exist_ok=True)
    return [f"R{i + 1:02d}" for i in range(len(ordered))]


# --------------------------------------------------------------------------- the static oracle gate


def _is_literal(node: ast.AST) -> bool:
    try:
        ast.literal_eval(node)
    except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError):
        return False
    return True


def _is_raises(node: ast.With) -> bool:
    """`with pytest.raises(Name):` and nothing else in the header."""
    if len(node.items) != 1:
        return False
    call = node.items[0].context_expr
    if not isinstance(call, ast.Call) or len(call.args) != 1 or call.keywords:
        return False
    func = call.func
    return (isinstance(func, ast.Attribute) and func.attr == "raises"
            and isinstance(func.value, ast.Name) and func.value.id == "pytest")


def check_oracle_source(source: str, library: set[str]) -> list[str]:
    """Static gate (docs/rule-extraction-prompt.md, section 6). An empty list means it may be run."""
    found: list[str] = []
    if len(source.splitlines()) > ORACLE_MAX_LINES:
        found.append(f"more than {ORACLE_MAX_LINES} lines")
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return [f"does not parse: {exc.msg}"]

    stdlib = set(sys.stdlib_module_names)
    checks = 0
    for node in tree.body:
        if isinstance(node, ast.Import):
            roots = [a.name.split(".")[0] for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            roots = [(node.module or "").split(".")[0]]
            if any(a.name == "*" for a in node.names) or node.level:
                found.append("star or relative import")
        elif isinstance(node, ast.FunctionDef) and node.name.startswith("test"):
            roots = []
            checks += _check_test(node, found)
        else:
            found.append(f"line {node.lineno}: only imports and test functions are allowed at the top level")
            continue
        for root in roots:
            if root in NO_ORACLE_MODULES:
                found.append(f"imports {root}, which a deterministic oracle may not use")
            elif root not in stdlib and root != "pytest" and root not in library:
                found.append(f"imports {root}, which is not the standard library or the library under test")
    if not any(isinstance(n, ast.FunctionDef) for n in tree.body):
        found.append("no test function")
    elif checks < ORACLE_MIN_CHECKS:
        found.append(f"only {checks} check(s); at least {ORACLE_MIN_CHECKS} are needed")
    return found


FORBIDDEN_INSIDE = (ast.For, ast.While, ast.If, ast.Try, ast.FunctionDef, ast.ClassDef, ast.Lambda, ast.ListComp,
                    ast.SetComp, ast.DictComp, ast.GeneratorExp, ast.Import, ast.ImportFrom, ast.Global, ast.Nonlocal,
                    ast.Await, ast.AsyncFunctionDef)


def _check_test(func: ast.FunctionDef, found: list[str]) -> int:
    checks = 0
    if func.args.args or func.decorator_list:
        found.append(f"{func.name}: takes arguments or has decorators (no fixtures or parametrize)")
    for stmt in func.body:
        for inner in ast.walk(stmt):
            if isinstance(inner, FORBIDDEN_INSIDE):
                found.append(f"{func.name}: uses {type(inner).__name__}, which is not allowed in a test")
            if isinstance(inner, ast.Call) and isinstance(inner.func, ast.Name) and inner.func.id in _BANNED_CALLS:
                found.append(f"{func.name}: calls {inner.func.id}")
        if isinstance(stmt, ast.Assert):
            test = stmt.test
            ok = (isinstance(test, ast.Compare) and len(test.ops) == 1 and isinstance(test.ops[0], (ast.Eq, ast.Is))
                  and _is_literal(test.comparators[0]) and not _is_literal(test.left))
            if ok:
                checks += 1
            else:
                found.append(f"{func.name}: an assert must be `<expression> == <literal>` or `is <constant>` "
                             "(the expected value may not be computed)")
        elif isinstance(stmt, ast.With):
            if _is_raises(stmt) and len(stmt.body) == 1 and isinstance(stmt.body[0], (ast.Expr, ast.Assign)):
                checks += 1
            else:
                found.append(f"{func.name}: a `with` must be `pytest.raises(Name)` around exactly one statement")
        elif not isinstance(stmt, (ast.Assign, ast.AugAssign, ast.Expr)):
            found.append(f"{func.name}: {type(stmt).__name__} is not allowed")
    return checks


def library_names(root: Path, subdir: str) -> set[str]:
    """Top-level importable names of the library under test."""
    names = set()
    for chunk in library_chunks(root, subdir):
        module = module_path(chunk.file, subdir)
        if module:
            names.add(module.split(".")[0])
    return names

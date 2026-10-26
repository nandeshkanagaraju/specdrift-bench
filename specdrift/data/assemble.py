"""Stage B, part 2: turn mutants into training examples, labelled by per-rule oracle tests.

A mutant is DRIFT for a rule only if that rule's oracle passes on the original project and fails
on the mutant. The project's own suite is not the judge: it misses behaviour no test was written
for, and it cannot say which rule a failure belongs to. The oracle can.

What one project yields (docs/training-data-spec.md, sections 5 and 6):

    DRIFT       a mutant whose symbol a rule covers and whose oracle for that rule fails
    COMPLIANT   the same mutated code shown against a covered rule whose oracle still passes
                (`hardneg:wrong_rule`), and the unchanged code for every rule (`N1`)
    UNCERTAIN   a view that does not contain the code the rule is about: either retrieval missed
                it, or it was dropped on purpose to teach abstention

The model is shown what SpecGuard shows it: Stage 1's top-k excerpt with constant context, or, for a
fraction of examples, the gold chunk alone.
"""

from __future__ import annotations

import ast
import random
import re
import shutil
import tempfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import yaml

from specdrift.bench.builder import IGNORED, apply_patch
from specdrift.bench.schema import Chunk, Counterexample, Evidence, Rule
from specdrift.code.chunker import chunk_source, chunk_workspace
from specdrift.data.inject import Mutant, PytestRun, SandboxMode, is_test_project, run_pytest
from specdrift.data.schema import Provenance, Target, TrainingExample
from specdrift.data.stage_a import changed_span
from specdrift.data.validate import problems
from specdrift.retrieval.embedder import build_embedder
from specdrift.retrieval.retriever import add_constant_context, retrieve
from specdrift.spec.parser import load_project_rules
from specdrift.verify.engine import excerpt_for

CONFIDENCE = 0.9
ABSTAIN_CONFIDENCE = 0.5
USABLE_STATUS = ("killed", "survived", "preserved")


@dataclass
class RuleSpec:
    rule: Rule
    symbols: list[str]
    oracle: tuple[str, ...]


# --------------------------------------------------------------------------- rule map


def load_rule_map(path: Path, rules: list[Rule], root: Path) -> dict[str, RuleSpec]:
    """rules.yaml: rule id -> {symbols: [...], oracle: [pytest paths relative to the project]}."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    by_id = {rule.id: rule for rule in rules}
    specs: dict[str, RuleSpec] = {}
    for rule_id, entry in raw.items():
        if rule_id not in by_id:
            raise ValueError(f"{path}: {rule_id} is not a rule in spec.md")
        symbols, oracle = entry.get("symbols") or [], entry.get("oracle") or []
        if not symbols or not oracle:
            raise ValueError(f"{path}: {rule_id} needs both `symbols` and `oracle`")
        for target in oracle:
            if not (root / target.split("::")[0]).is_file():
                raise ValueError(f"{path}: oracle {target} does not exist")
        specs[rule_id] = RuleSpec(by_id[rule_id], list(symbols), tuple(oracle))
    return specs


def symbol_matches(symbols: list[str], symbol: str) -> bool:
    """A rule about `Class` covers `Class.method`; `<module>` covers module-level code only."""
    return any(symbol == s or symbol.startswith(s + ".") for s in symbols)


def view_covers(symbols: list[str], view: list[Chunk]) -> bool:
    return any(symbol_matches(symbols, chunk.qualname) for chunk in view)


# --------------------------------------------------------------------------- reading a failure

_FRAME_RE = re.compile(r"^(?P<path>\S+?):(?P<line>\d+): in \S+$")
_ASSERT_RE = re.compile(r"^assert (?P<lhs>.+?) (?P<op>==|!=|is not|is|<=|>=|<|>|not in|in) (?P<rhs>.+)$")
_WHERE_RE = re.compile(r"where .+? = (?P<call>.+)$")
_RAISES_RE = re.compile(r"DID NOT RAISE (?:<class '(?:[\w.]+\.)?(?P<name>\w+)'>|(?:[\w.]+\.)?(?P<bare>\w+))")
_WITH_RAISES_RE = re.compile(r"with pytest\.raises\((?:[\w.]+\.)?(?P<name>\w+)")


def _clip(text: str, limit: int = 200) -> str:
    return text if len(text) <= limit else text[: limit - 3] + "..."


def parse_failure(output: str, root: Path, oracles: tuple[str, ...]) -> Counterexample:
    """input / expected / actual from a failed oracle's short traceback."""
    lines = output.splitlines()
    first_e = next((i for i, line in enumerate(lines) if re.match(r"^E\s", line)), None)
    if first_e is None:
        return Counterexample(input="(oracle)", expected="the oracle passes", actual="the oracle failed")
    e_lines = []
    for line in lines[first_e:]:
        if not re.match(r"^E\s", line):
            break
        e_lines.append(line[1:].strip())

    # the statement in the oracle file that failed, not the library frame it came from
    names = {Path(o.split("::")[0]).as_posix() for o in oracles}
    frame_line, statement, expects = 0, "", ""
    frames: list[tuple[re.Match[str], int]] = []
    for i, line in enumerate(lines[:first_e]):
        frame = _FRAME_RE.match(line)
        if frame:
            frames.append((frame, i))
    for match, index in frames:
        if any(match["path"].endswith(name) for name in names):
            frame_line, statement = int(match["line"]), lines[index + 1].strip() if index + 1 < len(lines) else ""
            path = next((root / n for n in names if match["path"].endswith(n)), None)
            source = path.read_text(encoding="utf-8").splitlines() if path and path.is_file() else []
            if statement.startswith("with pytest.raises") and source:
                # DID NOT RAISE is reported on the `with` line; the call under test is the line after it
                declared = _WITH_RAISES_RE.match(statement)
                expects = declared["name"] if declared else ""
                statement = next((t.strip() for t in source[frame_line:] if t.strip()), statement)
            elif source and 0 < frame_line <= len(source):
                # another exception escaped: the enclosing `with pytest.raises(X)` says what was expected
                indent = len(source[frame_line - 1]) - len(source[frame_line - 1].lstrip())
                for above in reversed(source[max(0, frame_line - 6) : frame_line - 1]):
                    outer = _WITH_RAISES_RE.match(above.strip())
                    if outer and len(above) - len(above.lstrip()) < indent:
                        expects = outer["name"]
                        break
            break

    head = e_lines[0]
    if head.startswith("AssertionError: assert "):          # pytest adds the prefix when it appends a diff
        head = head[len("AssertionError: "):]
    if raised := _RAISES_RE.search(head):
        name = raised["name"] or raised["bare"]
        return Counterexample(input=_clip(statement), expected=f"raises {name}", actual="no exception was raised")
    if asserted := _ASSERT_RE.match(head):
        call = next((w["call"] for line in e_lines[1:] if (w := _WHERE_RE.search(line))), "")
        subject = call or (statement[7:] if statement.startswith("assert ") else statement).split(f" {asserted['op']} ")[0]
        expected = asserted["rhs"] if asserted["op"] in ("==", "is") else f"{asserted['op']} {asserted['rhs']}"
        return Counterexample(input=_clip(subject), expected=_clip(expected), actual=_clip(asserted["lhs"]))

    # An exception escaped while the assert's own left side was being evaluated: the assert still says what
    # was expected, so show its call as the input and its literal as the expectation.
    if statement.startswith("assert "):
        try:
            node = ast.parse(statement).body[0]
        except SyntaxError:
            node = None
        if isinstance(node, ast.Assert) and isinstance(node.test, ast.Compare) and len(node.test.ops) == 1:
            return Counterexample(input=_clip(ast.unparse(node.test.left)),
                                  expected=_clip(ast.unparse(node.test.comparators[0])),
                                  actual=_clip(f"raises {head}"))
    return Counterexample(
        input=_clip(statement or "(oracle)"),
        expected=f"raises {expects}" if expects else "no exception",
        actual=_clip(f"raises {head}"),
    )


# --------------------------------------------------------------------------- building examples


def _example(
    *, name: str, split: str, example_id: str, source: str, rule: Rule, view: list[Chunk], label: str,
    category: str, target: Target, method: str, seed: int, notes: dict[str, str], oracle: str | None,
) -> TrainingExample:
    return TrainingExample(
        example_id=example_id, source=source, split=split, project_id=name,  # type: ignore[arg-type]
        rule=rule, chunks=view, label=label,  # type: ignore[arg-type]
        category=category, target=target,
        provenance=Provenance(label_method=method, generator="injector-v1", oracle_test=oracle,  # type: ignore[arg-type]
                              seed=seed, notes=notes),
    )


def _abstain(base: TrainingExample, spec: RuleSpec, drop_gold: str, reason: str) -> TrainingExample:
    kept = [c for c in base.chunks if not symbol_matches(spec.symbols, c.qualname) and c.id != drop_gold]
    notes = {**base.provenance.notes, "abstain_reason": reason, "from": base.example_id}
    return base.model_copy(update={
        "example_id": base.example_id + "-abstain", "source": "synth", "chunks": kept, "label": "UNCERTAIN",
        "category": f"abstain:{reason}", "target": Target(verdict="UNCERTAIN", confidence=ABSTAIN_CONFIDENCE),
        "provenance": base.provenance.model_copy(update={"label_method": "injected_known", "notes": notes}),
    })


def shown_span(chunk: Chunk, mutated: str, start: int, end: int) -> tuple[int, int]:
    """File lines (start, end) -> the line numbers the prompt shows for `chunk`.

    A function chunk is contiguous, so its numbers are the file's. The module chunk joins the
    top-level statements and drops what lies between them, but is numbered consecutively from its
    first line, so the changed line has to be found in the chunk's own text.
    """
    held = chunk.source.splitlines()
    if len(held) == chunk.end_line - chunk.start_line + 1:
        first = min(max(start, chunk.start_line), chunk.end_line)
        return first, min(max(end, first), chunk.end_line)
    changed = mutated.splitlines()[start - 1].strip()
    index = next((i for i, line in enumerate(held) if line.strip() == changed), 0)
    return chunk.start_line + index, chunk.start_line + index


def is_test_path(rel: str) -> bool:
    """Test code is never library code, even when it lives inside the package (voluptuous/tests)."""
    parts = rel.split("/")
    return bool({"tests", "test", "testing"} & set(parts[:-1])) or parts[-1].startswith("test_") or parts[-1] == "conftest.py"


def library_chunks(root: Path, subdir: str) -> list[Chunk]:
    return [c for c in chunk_workspace(root, subdir) if not is_test_path(c.file)]


def assemble_project(
    project: Path,
    name: str,
    mutants: list[Mutant],
    rule_map: Path,
    *,
    subdir: str = "src",
    split: str = "train",
    seed: int = 17,
    top_k: int = 3,
    gold_view: float = 0.2,
    abstain: float = 0.1,
    gold_on_miss: bool = True,
    timeout: float = 60.0,
    sandbox: SandboxMode = "auto",
    protected_roots: list[Path] | None = None,
    allow_test_project: bool = False,
) -> tuple[list[TrainingExample], dict]:
    project = project.resolve()
    if not allow_test_project and is_test_project(project, protected_roots or []):
        raise ValueError(f"{project} is part of the test set; refusing to generate training data from it")

    rules = load_project_rules(project)
    specs = load_rule_map(rule_map, rules, project)
    rng = random.Random(seed)
    stats: Counter = Counter()
    kills: dict[str, list[int]] = {}          # rule -> [mutants its oracle was run on, mutants it failed on]
    excluded: dict[str, str] = {}
    examples: list[TrainingExample] = []

    with tempfile.TemporaryDirectory(prefix="specdrift-assemble-") as scratch:
        work = Path(scratch) / "p"
        shutil.copytree(project, work, ignore=IGNORED)

        usable: dict[str, RuleSpec] = {}
        for rule_id, spec in specs.items():
            base_run = run_pytest(work, timeout, sandbox, spec.oracle)
            if base_run.status == "passed":
                usable[rule_id] = spec
            else:
                excluded[rule_id] = f"oracle {base_run.status} on the unmodified project"
        if not usable:
            raise ValueError(f"{name}: no rule has an oracle that passes on the unmodified project: {excluded}")

        embedder = build_embedder("local", "", Path(scratch))
        pristine = library_chunks(work, subdir)

        def show(rule: Rule, chunks: list[Chunk], gold: list[Chunk], use_gold: bool) -> list[Chunk]:
            if use_gold:
                return add_constant_context(gold, chunks)
            by_id = {c.id: c for c in chunks}
            return excerpt_for(rule, retrieve(rules, chunks, embedder, k=top_k), by_id, chunks)[0]

        # ---- unchanged code, once per rule
        for rule_id, spec in usable.items():
            gold = [c for c in pristine if symbol_matches(spec.symbols, c.qualname)][:1]
            view = show(spec.rule, pristine, gold, rng.random() < gold_view)
            covered = view_covers(spec.symbols, view)
            label = "COMPLIANT" if covered else "UNCERTAIN"
            target = Target(verdict=label, confidence=CONFIDENCE if covered else ABSTAIN_CONFIDENCE)  # type: ignore[arg-type]
            base = _example(
                name=name, split=split, example_id=f"synth-{name}-N1-{rule_id}", source="hardneg", rule=spec.rule,
                view=view, label=label, category="N1" if covered else "abstain:retrieval_miss", target=target,
                method="execution" if covered else "injected_known", seed=seed,
                notes={"view": "retrieved"}, oracle=" ".join(spec.oracle),
            )
            examples.append(base)
            stats[f"N1/{label}"] += 1
            if covered and rng.random() < abstain:
                examples.append(_abstain(base, spec, "", "dropped_chunk"))
                stats["abstain/dropped_chunk"] += 1

        # ---- each mutant
        for mutant in mutants:
            if mutant.status not in USABLE_STATUS:
                stats[f"skipped/{mutant.status}"] += 1
                continue
            if mutant.category in ("N2", "N3") and mutant.status != "preserved":
                # A "refactor" or "decoy" that changed behaviour is a defect in the generator, not an example of drift.
                stats[f"skipped/{mutant.category} was not behaviour-preserving"] += 1
                continue
            cands = [s for s in usable.values() if symbol_matches(s.symbols, mutant.symbol)]
            if not cands:
                stats["skipped/no rule covers the symbol"] += 1
                continue

            path = work / mutant.file
            original = path.read_text(encoding="utf-8")
            mutated = apply_patch(original, mutant.find, mutant.replace)
            runs: dict[str, PytestRun] = {}
            path.write_text(mutated, encoding="utf-8")
            try:
                for spec in cands:
                    runs[spec.rule.id] = run_pytest(work, timeout, sandbox, spec.oracle, tb="short")
                    if mutant.status != "preserved":        # a refactor is *meant* to break no oracle
                        tally = kills.setdefault(spec.rule.id, [0, 0])
                        tally[0] += 1
                        tally[1] += runs[spec.rule.id].status == "killed"
            finally:
                path.write_text(original, encoding="utf-8")

            changed = [c for c in pristine if c.file != mutant.file] + chunk_source(mutated, mutant.file)
            gold_chunk = next(
                (c for c in changed if c.file == mutant.file and c.qualname == mutant.symbol
                 and c.start_line <= mutant.line <= c.end_line + 1), None)
            if gold_chunk is None:
                stats["skipped/mutated chunk not found"] += 1
                continue
            start, end = changed_span(original, mutated)
            start, end = shown_span(gold_chunk, mutated, start, end)

            benign = mutant.status == "preserved"           # an N2 refactor or N3 decoy: every oracle must still pass
            passed_specs = [s for s in cands if runs[s.rule.id].status == "passed"]
            wrong = {rng.choice(passed_specs).rule.id} if passed_specs and not benign else set()
            for spec in cands:
                run = runs[spec.rule.id]
                if benign and run.status == "passed":
                    kind = "benign"
                elif benign and run.status == "killed":
                    stats[f"skipped/{mutant.category} changed what a rule's oracle checks"] += 1
                    continue
                elif run.status == "killed":
                    kind = "drift"
                elif run.status == "passed" and spec.rule.id in wrong:
                    kind = "wrong_rule"
                else:
                    stats[f"skipped/oracle {run.status}"] += 1
                    continue

                use_gold = rng.random() < gold_view
                view = show(spec.rule, changed, [gold_chunk], use_gold)
                shown = gold_chunk.id in {c.id for c in view}
                others = ",".join(sorted(r for r, o in runs.items() if o.status == "killed" and r != spec.rule.id))
                notes = {
                    "view": "gold" if use_gold else "retrieved",
                    "violates_other_rules": others,
                    "mutant_id": mutant.mutant_id, "operator": mutant.operator, "mutant_status": mutant.status,
                    "inject_find": mutant.find, "inject_replace": mutant.replace,
                }
                example_id = f"synth-{mutant.mutant_id}-{spec.rule.id}"
                oracle = run.test or " ".join(spec.oracle)

                if kind == "drift" and not shown:
                    base = _example(
                        name=name, split=split, example_id=example_id, source="synth", rule=spec.rule, view=view,
                        label="UNCERTAIN", category="abstain:retrieval_miss", target=Target(
                            verdict="UNCERTAIN", confidence=ABSTAIN_CONFIDENCE),
                        method="injected_known", seed=seed, notes=notes, oracle=oracle)
                    examples.append(base)
                    stats["abstain/retrieval_miss"] += 1
                    if gold_on_miss:
                        # The rule *was* violated: show the changed code too, and teach the verdict that goes with it.
                        gold_view_chunks = add_constant_context([gold_chunk], changed)
                        target = Target(
                            verdict="DRIFT", confidence=CONFIDENCE, violated_clause=spec.rule.text,
                            evidence=Evidence(file=mutant.file, start_line=start, end_line=end),
                            counterexample=parse_failure(run.output, work, spec.oracle))
                        examples.append(_example(
                            name=name, split=split, example_id=example_id + "-gold", source="synth", rule=spec.rule,
                            view=gold_view_chunks, label="DRIFT", category=mutant.category, target=target,
                            method="execution", seed=seed,
                            notes={**notes, "view": "gold", "counterexample_method": "oracle_failure",
                                   "recovered_from": example_id}, oracle=oracle))
                        stats[f"DRIFT/{mutant.category}"] += 1
                        stats["DRIFT/recovered from a retrieval miss"] += 1
                        if mutant.status == "survived":
                            stats["DRIFT/rescued by oracle"] += 1
                    continue
                if kind in ("wrong_rule", "benign") and not shown:
                    if not gold_on_miss:
                        stats["skipped/mutated code not in view"] += 1
                        continue
                    # A refactor the model is never shown teaches nothing: show the changed code instead.
                    view = add_constant_context([gold_chunk], changed)
                    notes = {**notes, "view": "gold", "recovered_from": f"{example_id} (retrieval miss)"}
                    example_id += "-gold"
                    stats["COMPLIANT/recovered from a retrieval miss"] += 1

                if kind == "drift":
                    counter = parse_failure(run.output, work, spec.oracle)
                    target = Target(
                        verdict="DRIFT", confidence=CONFIDENCE, violated_clause=spec.rule.text,
                        evidence=Evidence(file=mutant.file, start_line=start, end_line=end), counterexample=counter)
                    base = _example(
                        name=name, split=split, example_id=example_id, source="synth", rule=spec.rule, view=view,
                        label="DRIFT", category=mutant.category, target=target, method="execution", seed=seed,
                        notes={**notes, "counterexample_method": "oracle_failure"}, oracle=oracle)
                    stats[f"DRIFT/{mutant.category}"] += 1
                    if mutant.status == "survived":
                        stats["DRIFT/rescued by oracle"] += 1
                else:
                    category = mutant.category if kind == "benign" else "hardneg:wrong_rule"
                    base = _example(
                        name=name, split=split, example_id=example_id, source="hardneg", rule=spec.rule, view=view,
                        label="COMPLIANT", category=category,
                        target=Target(verdict="COMPLIANT", confidence=CONFIDENCE), method="execution", seed=seed,
                        notes=notes, oracle=" ".join(spec.oracle))
                    stats[f"COMPLIANT/{mutant.category if kind == 'benign' else 'wrong_rule'}"] += 1
                examples.append(base)
                if rng.random() < abstain:
                    examples.append(_abstain(base, spec, gold_chunk.id, "dropped_chunk"))
                    stats["abstain/dropped_chunk"] += 1

    rejected = {e.example_id: p for e in examples if (p := problems(e))}
    examples = [e for e in examples if e.example_id not in rejected]
    summary = {
        "examples": len(examples), "counts": dict(sorted(stats.items())), "rules_excluded": excluded,
        "rejected_by_validator": rejected, "seed": seed, "split": split,
        "oracle_kill_rate": {r: {"mutants": n, "killed": k} for r, (n, k) in sorted(kills.items())},
        "oracles_that_kill_nothing": sorted(r for r, (n, k) in kills.items() if n and not k),
    }
    return examples, summary

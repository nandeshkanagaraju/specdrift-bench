"""Freeze the test set and prove no training example overlaps it (docs/training-data-spec.md, section 7).

The test material is everything a model must never see while training:

* the three host projects, original code and every case's drifted code, plus their rules;
* the example projects under examples/, which are the second, unseen test set;
* the (find, replace) pair of every case.

`freeze` writes a manifest of fingerprints. `check` recomputes the material from the repository,
refuses to run if it no longer matches the manifest (the test set moved after it was frozen), and
then runs the overlap checks against one or more training files.
"""

from __future__ import annotations

import hashlib
import io
import json
import tokenize
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from specdrift.bench.builder import load_all_manifests, patched_sources
from specdrift.bench.schema import Chunk
from specdrift.code.chunker import chunk_source, chunk_workspace
from specdrift.data.schema import TrainingExample
from specdrift.spec.parser import load_project_rules

MANIFEST_VERSION = 1
MIN_CHUNK_TOKENS = 15       # shorter chunks (empty classes, bare imports) match by chance
NGRAM = 13
RULE_DISTANCE = 0.2         # normalised edit distance below this counts as the same rule
NGRAM_FAIL = 0.9            # a test chunk this covered by training n-grams is a near-copy
NGRAM_WARN = 0.5
CHECKS = ("projects", "chunks", "rules", "injections", "ngrams")

_SKIP_TOKENS = {
    tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT,
    tokenize.ENDMARKER,
}


# --------------------------------------------------------------------------- normalising


def code_tokens(source: str) -> list[str]:
    """Code as a token list with comments and layout removed, so edits to either do not hide a copy."""
    try:
        return [
            tok.string
            for tok in tokenize.generate_tokens(io.StringIO(source).readline)
            if tok.type not in _SKIP_TOKENS
        ]
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return source.split()


def token_hash(tokens: list[str]) -> str:
    return hashlib.sha256(" ".join(tokens).encode()).hexdigest()[:20]


def norm_text(text: str) -> str:
    return " ".join(text.lower().split())


def norm_code(text: str) -> str:
    return "".join(text.split())


def edit_distance_within(a: str, b: str, limit: int) -> int | None:
    """Levenshtein distance if it is at most `limit`, else None. Banded, so it stays cheap."""
    if abs(len(a) - len(b)) > limit:
        return None
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        current = [i] + [limit + 1] * len(b)
        low, high = max(1, i - limit), min(len(b), i + limit)
        for j in range(low, high + 1):
            cost = 0 if ca == b[j - 1] else 1
            current[j] = min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + cost)
        if min(current[low : high + 1], default=limit + 1) > limit:
            return None
        previous = current
    return previous[-1] if previous[-1] <= limit else None


def rules_are_near(a: str, b: str, threshold: float = RULE_DISTANCE) -> bool:
    """Normalised edit distance below `threshold`. A letter-count bound skips most pairs cheaply."""
    longest = max(len(a), len(b))
    if longest == 0:
        return True
    limit = int(threshold * longest)
    if limit and sum(((Counter(a) - Counter(b)) + (Counter(b) - Counter(a))).values()) > 2 * limit:
        return False
    distance = edit_distance_within(a, b, limit)
    return distance is not None and distance / longest < threshold


# --------------------------------------------------------------------------- test material


@dataclass
class TestChunk:
    __test__ = False  # not a pytest class

    id: str
    tokens: list[str]


@dataclass
class TestMaterial:
    __test__ = False

    cases: list[dict]
    projects: list[str]
    chunks: list[TestChunk]
    rules: dict[str, str]                    # normalised rule text -> "<project>:<rule id>"
    injections: set[tuple[str, str]]         # (normalised find, normalised replace)
    chunk_hashes: dict[str, str] = field(default_factory=dict)   # token hash -> chunk id

    def manifest(self) -> dict:
        body = {
            "cases": self.cases,
            "projects": self.projects,
            "chunk_hashes": sorted(self.chunk_hashes),
            "rules": sorted(self.rules),
            "injections": sorted(list(pair) for pair in self.injections),
        }
        fingerprint = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
        return {"version": MANIFEST_VERSION, "fingerprint": fingerprint, **body}


def _add_chunks(material: TestMaterial, chunks: Iterable[Chunk], prefix: str) -> None:
    for chunk in chunks:
        tokens = code_tokens(chunk.source)
        if len(tokens) < MIN_CHUNK_TOKENS:
            continue
        digest = token_hash(tokens)
        if digest in material.chunk_hashes:
            continue
        chunk_id = f"{prefix}{chunk.id}"
        material.chunk_hashes[digest] = chunk_id
        material.chunks.append(TestChunk(chunk_id, tokens))


def _add_project(material: TestMaterial, name: str, root: Path) -> None:
    material.projects.append(name)
    for subdir in ("src", "tests"):
        if (root / subdir).is_dir():
            _add_chunks(material, chunk_workspace(root, subdir), f"{name}/")
    for rule in load_project_rules(root):
        material.rules.setdefault(norm_text(rule.text), f"{name}:{rule.id}")


def collect_test_material(cases_dir: Path, projects_dir: Path, examples_dir: Path | None) -> TestMaterial:
    material = TestMaterial(cases=[], projects=[], chunks=[], rules={}, injections=set())
    cases = load_all_manifests(cases_dir)

    for name in sorted({case.project for case in cases}):
        _add_project(material, name, projects_dir / name)

    for case in cases:
        digest = hashlib.sha256(f"{case.file}\n{case.find}\n{case.replace}".encode()).hexdigest()[:16]
        material.cases.append(
            {"id": case.id, "project": case.project, "category": case.category, "label": case.label,
             "patch_sha": digest}
        )
        if case.find:
            material.injections.add((norm_code(case.find), norm_code(case.replace)))
            before, after = patched_sources(case, projects_dir)
            if after != before:
                _add_chunks(material, chunk_source(after, case.file), f"{case.id}/")

    if examples_dir and examples_dir.is_dir():
        for root in sorted(examples_dir.iterdir()):
            if (root / "spec.md").is_file():
                _add_project(material, f"examples/{root.name}", root)

    material.cases.sort(key=lambda c: c["id"])
    material.projects.sort()
    return material


# --------------------------------------------------------------------------- freeze


class ManifestMismatch(Exception):
    """The test set on disk is not the one that was frozen."""


def freeze(material: TestMaterial, path: Path, force: bool = False) -> dict:
    manifest = material.manifest()
    if path.exists() and not force:
        existing = json.loads(path.read_text())
        if existing.get("fingerprint") != manifest["fingerprint"]:
            raise ManifestMismatch(
                "the test set differs from the frozen manifest; pass --force only if you mean to re-freeze"
            )
        return existing
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n")
    return manifest


def verify_frozen(material: TestMaterial, path: Path) -> dict:
    if not path.exists():
        raise ManifestMismatch(f"{path} does not exist; run `specdrift data-freeze` first")
    frozen = json.loads(path.read_text())
    if frozen.get("version") != MANIFEST_VERSION:
        raise ManifestMismatch("manifest version not understood")
    if frozen["fingerprint"] != material.manifest()["fingerprint"]:
        raise ManifestMismatch(
            "the test set changed after it was frozen (cases, projects, rules or examples were edited)"
        )
    return frozen


# --------------------------------------------------------------------------- checks


@dataclass
class Finding:
    check: str
    example_id: str
    detail: str


@dataclass
class Report:
    examples: int = 0
    findings: list[Finding] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    ngram: dict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.findings

    def counts(self) -> dict[str, int]:
        tally = Counter(f.check for f in self.findings)
        return {name: tally.get(name, 0) for name in CHECKS}

    def as_dict(self) -> dict:
        return {
            "ok": self.ok, "examples": self.examples, "violations": self.counts(),
            "ngram": self.ngram, "notes": self.notes,
            "findings": [f.__dict__ for f in self.findings],
        }


def load_examples(paths: Iterable[Path]) -> list[TrainingExample]:
    examples: list[TrainingExample] = []
    for path in paths:
        with path.open(encoding="utf-8") as handle:
            for number, line in enumerate(handle, start=1):
                if line.strip():
                    try:
                        examples.append(TrainingExample.model_validate_json(line))
                    except ValueError as exc:
                        raise ValueError(f"{path}:{number} is not a valid training example: {exc}") from exc
    return examples


def check_projects(examples: list[TrainingExample], material: TestMaterial) -> list[Finding]:
    protected = {name.split("/")[-1] for name in material.projects} | set(material.projects)
    findings: list[Finding] = []
    splits: dict[str, set[str]] = defaultdict(set)
    for example in examples:
        splits[example.project_id].add(example.split)
        if example.project_id in protected:
            findings.append(Finding("projects", example.example_id,
                                    f"project_id {example.project_id!r} is a test project"))
    for project_id, seen in sorted(splits.items()):
        if len(seen) > 1:
            findings.append(Finding("projects", project_id, f"appears in more than one split: {sorted(seen)}"))
    return findings


def check_chunks(examples: list[TrainingExample], material: TestMaterial) -> list[Finding]:
    findings: list[Finding] = []
    for example in examples:
        for chunk in example.chunks:
            tokens = code_tokens(chunk.source)
            if len(tokens) < MIN_CHUNK_TOKENS:
                continue
            hit = material.chunk_hashes.get(token_hash(tokens))
            if hit:
                findings.append(Finding("chunks", example.example_id,
                                        f"chunk {chunk.id} equals test chunk {hit} (ignoring comments and layout)"))
    return findings


def check_rules(examples: list[TrainingExample], material: TestMaterial) -> list[Finding]:
    findings: list[Finding] = []
    cache: dict[str, str | None] = {}
    for example in examples:
        text = norm_text(example.rule.text)
        if text not in cache:
            cache[text] = next(
                (origin for known, origin in material.rules.items() if rules_are_near(text, known)), None
            )
        if cache[text]:
            findings.append(Finding("rules", example.example_id,
                                    f"rule text is within {RULE_DISTANCE:.0%} of test rule {cache[text]}"))
    return findings


def check_injections(examples: list[TrainingExample], report: Report, material: TestMaterial) -> list[Finding]:
    findings: list[Finding] = []
    recorded = 0
    for example in examples:
        notes = example.provenance.notes
        if "inject_find" not in notes:
            continue
        recorded += 1
        pair = (norm_code(notes["inject_find"]), norm_code(notes.get("inject_replace", "")))
        if pair in material.injections:
            findings.append(Finding("injections", example.example_id, "uses the find/replace pair of a test case"))
    skipped = len(examples) - recorded
    if skipped:
        report.notes.append(
            f"injections: {skipped} of {len(examples)} examples record no injection "
            "(provenance.notes inject_find / inject_replace), so this check could not apply to them"
        )
    return findings


def ngram_overlap(examples: list[TrainingExample], material: TestMaterial) -> dict:
    """How much of each test chunk's 13-grams also occur in training code."""
    seen: set[int] = set()
    for example in examples:
        for chunk in example.chunks:
            tokens = code_tokens(chunk.source)
            seen.update(hash(tuple(tokens[i : i + NGRAM])) for i in range(len(tokens) - NGRAM + 1))

    scored: list[tuple[float, str]] = []
    for test in material.chunks:
        grams = [hash(tuple(test.tokens[i : i + NGRAM])) for i in range(len(test.tokens) - NGRAM + 1)]
        if grams:
            scored.append((sum(g in seen for g in grams) / len(grams), test.id))
    scored.sort(reverse=True)
    values = [value for value, _ in scored]
    return {
        "n": NGRAM,
        "test_chunks": len(scored),
        "mean": round(sum(values) / len(values), 4) if values else 0.0,
        "max": round(values[0], 4) if values else 0.0,
        "above_warn": sum(v >= NGRAM_WARN for v in values),
        "above_fail": sum(v >= NGRAM_FAIL for v in values),
        "top": [{"chunk": cid, "overlap": round(v, 3)} for v, cid in scored[:5] if v > 0],
        "offenders": [{"chunk": cid, "overlap": round(v, 3)} for v, cid in scored if v >= NGRAM_WARN],
    }


def run_checks(
    examples: list[TrainingExample], material: TestMaterial, ngram_fail: float = NGRAM_FAIL
) -> Report:
    report = Report(examples=len(examples))
    report.findings += check_projects(examples, material)
    report.findings += check_chunks(examples, material)
    report.findings += check_rules(examples, material)
    report.findings += check_injections(examples, report, material)

    report.ngram = ngram_overlap(examples, material)
    for item in report.ngram["offenders"]:
        if item["overlap"] >= ngram_fail:
            report.findings.append(
                Finding("ngrams", item["chunk"], f"{item['overlap']:.0%} of its {NGRAM}-grams occur in training code")
            )
    report.notes.append(
        "hand review still required: the injection templates must differ from the strings used to author "
        "the 86 cases (spec section 7, check 5); it cannot be automated"
    )
    return report


def format_report(report: Report, frozen: dict) -> str:
    lines = [
        f"test set   {len(frozen['cases'])} cases, {len(frozen['projects'])} projects, "
        f"{len(frozen['chunk_hashes'])} chunks, {len(frozen['rules'])} rules (fingerprint {frozen['fingerprint'][:12]})",
        f"examples   {report.examples}",
    ]
    for name, count in report.counts().items():
        lines.append(f"  {'FAIL' if count else 'ok  '}  {name:<11}{count} violation(s)")
    ng = report.ngram
    lines.append(
        f"{NGRAM}-gram overlap of test chunks with training code: mean {ng['mean']:.3f}, max {ng['max']:.3f}, "
        f"{ng['above_warn']} chunk(s) >= {NGRAM_WARN:.0%}, {ng['above_fail']} >= {NGRAM_FAIL:.0%} "
        f"({ng['test_chunks']} chunks measured)"
    )
    for finding in report.findings[:15]:
        lines.append(f"  [{finding.check}] {finding.example_id}: {finding.detail}")
    if len(report.findings) > 15:
        lines.append(f"  ... and {len(report.findings) - 15} more")
    lines.extend(f"note: {note}" for note in report.notes)
    lines.append("RESULT: " + ("clean" if report.ok else f"{len(report.findings)} violation(s), do not train"))
    return "\n".join(lines)


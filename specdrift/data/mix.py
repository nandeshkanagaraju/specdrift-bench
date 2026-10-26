"""The mixer: many labelled pools in, one balanced train file and one validation file out.

It decides what the model learns from, so each choice is explicit and written to `mix.json`:

* **Splits are by project.** A Stage B project goes wholly to train or wholly to validation (the
  `val_fraction` of projects, at least one when there are two or more). Stage A keeps the split it
  was given: its projects are single tasks, already assigned by hash.
* **Caps.** At most `max_per_rule` examples per (project, rule, label), so a rule with many mutants
  cannot crowd out the others.
* **Diversity.** Examples are drawn round-robin across projects, and within a project across
  categories, so no mutation operator dominates a project.
* **No project dominates.** A project (or Stage A dataset) may supply at most `max_group_share` of
  any label. When the others cannot make up the rest, the mix shrinks; it is never padded from the
  big project. With a single project in a source the cap cannot apply and is skipped.
* **Label shares.** DRIFT, COMPLIANT and UNCERTAIN are sampled to the target shares. The binding
  label (the one that runs out first) fixes the size; the mixer reports it instead of padding.
* **Sources.** Stage A (`paper`) takes `paper_share` of the mix; the rest is Stage B. Stage A has no
  UNCERTAIN, so Stage B's UNCERTAIN share is raised until the overall share is met.
* **Nothing invalid gets through.** Every example is re-validated; the CLI then runs the leakage
  check on the result and refuses to write files that fail it.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path

from specdrift.data.schema import TrainingExample
from specdrift.data.validate import problems

LABELS = ("DRIFT", "COMPLIANT", "UNCERTAIN")
DEFAULT_SHARES = {"DRIFT": 0.35, "COMPLIANT": 0.55, "UNCERTAIN": 0.10}


@dataclass
class MixConfig:
    seed: int = 17
    shares: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_SHARES))
    paper_share: float = 0.3
    max_per_rule: int = 6
    max_group_share: float = 0.6              # no project (or Stage A dataset) may exceed this share of a label
    val_fraction: float = 0.2
    val_projects: tuple[str, ...] = ()        # name projects explicitly instead of drawing them
    exclude_sources: tuple[str, ...] = ()
    exclude_operators: tuple[str, ...] = ()     # hold a mutation or refactor family out (the H3-style ablation)
    total: int = 0                            # 0 = as large as the binding label allows

    def __post_init__(self) -> None:
        if abs(sum(self.shares.values()) - 1.0) > 1e-6 or set(self.shares) != set(LABELS):
            raise ValueError(f"shares must cover {LABELS} and sum to 1, got {self.shares}")
        if not 0 <= self.paper_share <= 1:
            raise ValueError("paper_share must be between 0 and 1")
        if not 0 < self.max_group_share <= 1:
            raise ValueError("max_group_share must be in (0, 1]")


# --------------------------------------------------------------------------- grouping


def group_of(example: TrainingExample) -> str:
    """What counts as one source for balancing: a Stage B project, or one Stage A dataset."""
    if example.source == "paper":
        return "paper:" + example.provenance.generator.split("/")[-1]
    return example.project_id


def content_key(example: TrainingExample) -> str:
    """Identity by what the model would see and be told, not by the id (ids restart in every run)."""
    body = json.dumps(
        [example.project_id, example.rule.id, example.rule.text, [c.source for c in example.chunks],
         example.target.model_dump()], sort_keys=True)
    return hashlib.sha256(body.encode()).hexdigest()


def _hash(seed: int, text: str) -> str:
    return hashlib.sha256(f"{seed}:{text}".encode()).hexdigest()


def choose_val_projects(projects: Iterable[str], cfg: MixConfig) -> set[str]:
    names = sorted(set(projects))
    if cfg.val_projects:
        unknown = set(cfg.val_projects) - set(names)
        if unknown:
            raise ValueError(f"validation projects not in the data: {sorted(unknown)}")
        return set(cfg.val_projects)
    if len(names) < 2:
        return set()
    count = max(1, round(cfg.val_fraction * len(names)))
    return set(sorted(names, key=lambda n: _hash(cfg.seed, n))[:count])


def resplit(examples: list[TrainingExample], cfg: MixConfig) -> list[TrainingExample]:
    """Stage A keeps its split; every other project goes wholly to one split."""
    synth_projects = {e.project_id for e in examples if e.source != "paper"}
    val = choose_val_projects(synth_projects, cfg)
    out = []
    for e in examples:
        split = e.split if e.source == "paper" else ("val" if e.project_id in val else "train")
        out.append(e if split == e.split else e.model_copy(update={"split": split}))
    return out


# --------------------------------------------------------------------------- sampling


def _kind(example: TrainingExample) -> str:
    """The mutation operator if there is one, else the category: the axis to keep diverse."""
    return example.provenance.notes.get("operator") or example.category


def _round_robin(buckets: dict[str, list], rng: random.Random) -> list:
    """Take one item from each bucket in turn (bucket order shuffled once), until all are empty."""
    keys = sorted(buckets)
    rng.shuffle(keys)
    queues = {k: list(buckets[k]) for k in keys}
    for queue in queues.values():
        rng.shuffle(queue)
    ordered = []
    while any(queues.values()):
        for k in keys:
            if queues[k]:
                ordered.append(queues[k].pop())
    return ordered


def _diverse_order(items: list[TrainingExample], rng: random.Random, outer: Callable, inner: Callable) -> list:
    """Items ordered so that taking a prefix is balanced across `outer` groups, then across `inner` kinds."""
    outer_buckets: dict[str, list] = defaultdict(list)
    for item in items:
        outer_buckets[outer(item)].append(item)
    per_outer = {}
    for key, group in outer_buckets.items():
        inner_buckets: dict[str, list] = defaultdict(list)
        for item in group:
            inner_buckets[inner(item)].append(item)
        per_outer[key] = _round_robin(inner_buckets, rng)
    keys = sorted(per_outer)
    rng.shuffle(keys)
    queues = {k: list(reversed(per_outer[k])) for k in keys}         # pop() takes the front of the balanced order
    ordered = []
    while any(queues.values()):
        for k in keys:
            if queues[k]:
                ordered.append(queues[k].pop())
    return ordered


def cap_per_rule(pool: list[TrainingExample], cfg: MixConfig, rng: random.Random) -> list[TrainingExample]:
    """At most `max_per_rule` per (project, rule, label), keeping a spread of operators."""
    buckets: dict[tuple, list] = defaultdict(list)
    for e in pool:
        buckets[(e.project_id, e.rule.id, e.label)].append(e)
    kept: list[TrainingExample] = []
    for key in sorted(buckets):
        ordered = _diverse_order(buckets[key], rng, outer=lambda e: e.project_id, inner=_kind)
        kept.extend(ordered[: cfg.max_per_rule])
    return kept


def quotas(total: int, shares: dict[str, float]) -> dict[str, int]:
    """Whole-number quotas that sum to `total` (largest remainder)."""
    raw = {label: total * share for label, share in shares.items()}
    quota = {label: math.floor(value) for label, value in raw.items()}
    for label in sorted(raw, key=lambda lab: raw[lab] - quota[lab], reverse=True)[: total - sum(quota.values())]:
        quota[label] += 1
    return quota


def fair_capacity(sizes: list[int], share: float) -> int:
    """Largest quota q such that no group supplies more than `share` of it, given what each group has.

    Taking equally from every group until it runs out gives the biggest group q minus what the others hold,
    so the cap holds exactly when q <= sum(min(size, share * q)).
    """
    sizes = [n for n in sizes if n > 0]
    if share >= 1 or len(sizes) <= 1:
        return sum(sizes)
    for q in range(sum(sizes), 0, -1):
        if q <= sum(min(n, share * q) for n in sizes) + 1e-9:
            return q
    return 0


def largest_total(available: dict[str, int], shares: dict[str, float]) -> tuple[int, str]:
    """Biggest mix the pools allow at these shares, and the label that limits it."""
    limits = {label: math.floor(available.get(label, 0) / share) for label, share in shares.items() if share > 0}
    binding = min(limits, key=lambda lab: limits[lab])
    return limits[binding], binding


# --------------------------------------------------------------------------- one split


def _group_shares(cfg: MixConfig, paper: bool, paper_weight: float | None = None) -> dict[str, float]:
    """Shares inside one source. Stage A has no UNCERTAIN, so Stage B carries the whole UNCERTAIN share."""
    d, c, u = (cfg.shares[label] for label in LABELS)
    if paper:
        return {"DRIFT": d / (d + c), "COMPLIANT": c / (d + c), "UNCERTAIN": 0.0}
    p = cfg.paper_share if paper_weight is None else paper_weight
    if p >= 1:
        return {"DRIFT": 0.0, "COMPLIANT": 0.0, "UNCERTAIN": 0.0}
    synth_u = min(u / (1 - p), 0.5)
    rest = 1 - synth_u
    return {"DRIFT": rest * d / (d + c), "COMPLIANT": rest * c / (d + c), "UNCERTAIN": synth_u}


def mix_split(examples: list[TrainingExample], cfg: MixConfig, rng: random.Random) -> tuple[list, dict]:
    """Balanced sample of one split. Returns (examples, report)."""
    report: dict = {"available": Counter(e.label for e in examples), "groups": {}}
    sources = {"paper": [e for e in examples if e.source == "paper"],
               "synth": [e for e in examples if e.source != "paper"]}
    capped = {name: cap_per_rule(pool, cfg, rng) for name, pool in sources.items()}
    report["after_cap"] = {name: dict(Counter(e.label for e in pool)) for name, pool in capped.items()}

    weights = {"paper": cfg.paper_share, "synth": 1 - cfg.paper_share}
    report["dropped_sources"] = []
    sizes: dict[str, int] = {}
    binding: dict[str, str] = {}
    shares: dict[str, dict[str, float]] = {}
    for _ in range(2):                         # a source that cannot meet its shares is dropped, then weights renormalise
        shares = {"paper": _group_shares(cfg, True), "synth": _group_shares(cfg, False, weights["paper"])}
        sizes, binding = {}, {}
        for name, pool in capped.items():
            if weights[name] <= 0:
                sizes[name] = 0
                continue
            by_group = {lab: Counter(group_of(e) for e in pool if e.label == lab) for lab in LABELS}
            have: dict[str, int] = {lab: fair_capacity(list(by_group[lab].values()), cfg.max_group_share) for lab in LABELS}
            group_total, binding[name] = largest_total(have, shares[name])
            sizes[name] = math.floor(group_total / weights[name]) if weights[name] < 1 else group_total
        dead = [n for n in capped if weights[n] > 0 and sizes[n] == 0]
        if not dead or len(dead) == len([n for n in capped if weights[n] > 0]):
            break
        report["dropped_sources"] += dead
        weights = {n: (0.0 if n in dead else w) for n, w in weights.items()}
        norm = sum(weights.values())
        weights = {n: w / norm for n, w in weights.items()}
    live = [name for name in capped if weights[name] > 0 and sizes[name] > 0]
    total = min(sizes[name] for name in live) if live else 0
    if cfg.total:
        total = min(total, cfg.total)
    report["total"] = total
    report["binding"] = {name: binding[name] for name in live}

    chosen: list[TrainingExample] = []
    for name in live:
        want = quotas(round(total * weights[name]), shares[name])
        for label in LABELS:
            pool = [e for e in capped[name] if e.label == label]
            ordered = _diverse_order(pool, rng, outer=group_of, inner=_kind)
            chosen.extend(ordered[: want[label]])
    rng.shuffle(chosen)
    return chosen, report


# --------------------------------------------------------------------------- the whole mix


def mix(examples: list[TrainingExample], cfg: MixConfig) -> tuple[dict[str, list[TrainingExample]], dict]:
    skipped: Counter = Counter()
    by_id: dict[str, TrainingExample] = {}
    for e in examples:
        earlier = by_id.get(e.example_id)
        if earlier is None:
            by_id[e.example_id] = e
        elif content_key(earlier) != content_key(e):
            raise ValueError(f"example id {e.example_id} appears twice with different content")
        else:
            skipped["same example in two inputs"] += 1     # e.g. the unchanged-code (N1) examples every run repeats
    examples = list(by_id.values())

    usable = []
    seen: set[str] = set()
    for e in examples:
        if e.source in cfg.exclude_sources:
            skipped["excluded source"] += 1
        elif e.provenance.notes.get("operator") in cfg.exclude_operators:
            skipped["excluded operator"] += 1
        elif problems(e):
            skipped["fails the validator"] += 1
        elif (key := content_key(e)) in seen:
            skipped["same content as an earlier example"] += 1       # e.g. two runs that mutated the same line
        else:
            seen.add(key)
            usable.append(e)

    usable = resplit(usable, cfg)
    out: dict[str, list[TrainingExample]] = {}
    reports: dict[str, dict] = {}
    for split in ("train", "val"):
        rng = random.Random(_hash(cfg.seed, split))
        out[split], reports[split] = mix_split([e for e in usable if e.split == split], cfg, rng)

    summary: dict = {
        "config": {k: (list(v) if isinstance(v, tuple) else v) for k, v in cfg.__dict__.items()},
        "input_examples": len(examples) + skipped["same example in two inputs"], "skipped": dict(skipped),
        "val_projects": sorted({e.project_id for e in usable if e.split == "val" and e.source != "paper"}),
        "splits": {},
    }
    for split, chosen in out.items():
        rep = reports[split]
        count = len(chosen)
        by_label: Counter = Counter(e.label for e in chosen)
        summary["splits"][split] = {
            "examples": count,
            "labels": dict(by_label),
            "label_shares": {k: round(v / count, 3) for k, v in by_label.items()} if count else {},
            "sources": dict(Counter(e.source for e in chosen)),
            "groups": dict(Counter(group_of(e) for e in chosen)),
            "categories": dict(Counter(e.category for e in chosen).most_common()),
            "rules_with_drift": len({(e.project_id, e.rule.id) for e in chosen if e.label == "DRIFT" and e.source != "paper"}),
            "available": dict(rep["available"]), "after_cap": rep["after_cap"], "binding_label": rep["binding"],
            "dropped_sources": rep["dropped_sources"],
            "largest_group_share": {
                lab: max(Counter(group_of(e) for e in chosen if e.label == lab).values(), default=0)
                / max(by_label.get(lab, 0), 1) for lab in LABELS},
        }
    return out, summary


def write_mix(out: dict[str, list[TrainingExample]], summary: dict, directory: Path, inputs: list[Path]) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for split, chosen in out.items():
        (directory / f"{split}.jsonl").write_text("".join(e.model_dump_json() + "\n" for e in chosen), encoding="utf-8")
    summary["inputs"] = {str(p): hashlib.sha256(p.read_bytes()).hexdigest()[:16] for p in inputs}
    (directory / "mix.json").write_text(json.dumps(summary, indent=1, sort_keys=True) + "\n", encoding="utf-8")

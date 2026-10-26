"""Shortlist Python repos for Stage B training data (docs/training-data-spec.md, section 5, step 1).

Two modes. The default reads GitHub's API only: nothing is downloaded or executed, so it is safe to
run anywhere, and it ends with a list of *candidates*. `--verify` then clones each candidate and runs
its test suite, which is the only way to know the suite passes offline; that executes third-party code
(always under `--sandbox require`) and is meant to be run by a person who has looked at the list.

A repo is accepted only if every check below passes, and `--verify` is what measures them:

  licence   permissive (MIT, BSD-2/3, Apache-2.0, ISC) according to GitHub's licence detector
  size      300 to 3000 non-blank, non-comment lines of library source (tests and docs excluded)
  tests     at least 10 tests, passing on a clean checkout with only the standard library and pytest
  sandbox   the suite runs with no network and writes confined to scratch space
  stable    the suite passes 3 times out of 3

Run:  .venv/bin/python scripts/shortlist_repos.py --out data/repos.csv                  # API only
      .venv/bin/python scripts/shortlist_repos.py --verify --workdir <empty dir> ...    # clones and runs tests
Needs `gh` (authenticated); `--verify` also needs `git`. Nothing downloaded is imported by this process;
each suite runs in a separate sandboxed pytest.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from specdrift.data.inject import run_pytest

LICENCES = ("mit", "bsd-3-clause", "bsd-2-clause", "apache-2.0", "isc")
MIN_LOC, MAX_LOC, MIN_TESTS, ROUNDS = 300, 3000, 10, 3
SKIP_WORDS = re.compile(
    r"django|flask|fastapi|aws|boto|selenium|tensorflow|torch|keras|scrap|crawl|telegram|discord|slack|"
    r"awesome|tutorial|course|bot\b|jupyter|notebook|opencv|numpy|pandas|scikit|kubernetes|docker|"
    r"cli tool|wrapper|client|sdk|plugin|bindings|cython|rust|wheel|installer",
    re.IGNORECASE,
)
NON_SOURCE = {"tests", "test", "testing", "docs", "doc", "examples", "example", "benchmarks", "build",
              "dist", "scripts", "tools", ".github", "node_modules", "venv", ".venv", "__pycache__"}
NON_SOURCE_FILES = {"setup.py", "conftest.py", "noxfile.py", "tasks.py", "fabfile.py", "docs.py"}
TEST_COUNT_RE = re.compile(r"(\d+) passed")


def gh_search(query: str, pages: int) -> list[dict]:
    found: list[dict] = []
    for page in range(1, pages + 1):
        out = subprocess.run(
            ["gh", "api", "-X", "GET", "search/repositories", "-f", f"q={query}", "-f", "sort=stars",
             "-f", "per_page=100", "-f", f"page={page}"],
            capture_output=True, text=True, timeout=60,
        )
        if out.returncode != 0:
            print(f"search failed: {out.stderr.strip()[:200]}", file=sys.stderr)
            break
        found += json.loads(out.stdout).get("items", [])
    return found


def seeded(path: Path) -> list[dict]:
    """GitHub's own record for each `owner/name` in the seed file; unknown or moved names are reported."""
    found: list[dict] = []
    for line in path.read_text().splitlines():
        name = line.split("#")[0].strip()
        if not re.fullmatch(r"[\w.-]+/[\w.-]+", name):
            continue
        repo = gh_json(f"repos/{name}")
        if isinstance(repo, dict) and repo.get("full_name"):
            found.append(repo)
        else:
            print(f"   seed {name}: not found on GitHub", file=sys.stderr)
    unique = {r["full_name"].lower(): r for r in found}      # a renamed repo can appear twice
    return list(unique.values())


def candidates(min_stars: int, limit: int) -> list[dict]:
    pool: dict[str, dict] = {}
    for licence in LICENCES:
        query = (f"language:python license:{licence} stars:>{min_stars} size:60..2500 "
                 "archived:false fork:false mirror:false")
        for repo in gh_search(query, pages=2):
            text = f"{repo['name']} {repo.get('description') or ''} {' '.join(repo.get('topics') or [])}"
            if not SKIP_WORDS.search(text):
                pool.setdefault(repo["full_name"], repo)
    ranked = sorted(pool.values(), key=lambda r: -r["stargazers_count"])
    return ranked[:limit]


def source_files(root: Path) -> list[Path]:
    src = root / "src"
    base = src if src.is_dir() and any(src.rglob("*.py")) else root
    files: list[Path] = []
    for path in sorted(base.rglob("*.py")):
        parts = set(path.relative_to(base).parts[:-1])
        if parts & NON_SOURCE or path.name in NON_SOURCE_FILES or path.name.startswith("test_"):
            continue
        if base == root and len(path.relative_to(base).parts) > 1 and not (
            (root / path.relative_to(base).parts[0] / "__init__.py").exists()
        ):
            continue                                # a stray folder of scripts, not a package
        files.append(path)
    return files


def count_loc(files: list[Path]) -> int:
    total = 0
    for path in files:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                total += 1
    return total


def gh_json(path: str) -> dict | list | None:
    out = subprocess.run(["gh", "api", path], capture_output=True, text=True, timeout=60)
    return json.loads(out.stdout) if out.returncode == 0 and out.stdout.strip() else None


def gh_text(repo: str, path: str) -> str:
    out = subprocess.run(["gh", "api", f"repos/{repo}/contents/{path}", "--jq", ".content"],
                         capture_output=True, text=True, timeout=60)
    if out.returncode != 0:
        return ""
    import base64

    try:
        return base64.b64decode(out.stdout.strip()).decode("utf-8", errors="replace")
    except ValueError:
        return ""


def declared_dependencies(repo: str, names: set[str]) -> int | None:
    """Runtime dependencies named in pyproject.toml, setup.cfg or setup.py (text only, nothing is run)."""
    import tomllib

    if "pyproject.toml" in names:
        try:
            data = tomllib.loads(gh_text(repo, "pyproject.toml"))
        except tomllib.TOMLDecodeError:
            data = {}
        project = data.get("project")
        if project is not None:
            if "dependencies" in project:
                return len(project["dependencies"])
            if "dependencies" not in project.get("dynamic", []):
                return 0                  # PEP 621: a [project] table with no `dependencies` has none
        if "tool" in data and "poetry" in data["tool"]:
            return len([d for d in data["tool"]["poetry"].get("dependencies", {}) if d != "python"])
    if "setup.cfg" in names:
        match = re.search(r"install_requires\s*=\s*((?:\n[ \t]+\S.*)+|[^\n]+)", gh_text(repo, "setup.cfg"))
        if match:
            return len([ln for ln in match.group(1).splitlines() if ln.strip()])
    if "setup.py" in names:
        text = gh_text(repo, "setup.py")
        match = re.search(r"install_requires\s*=\s*\[(.*?)\]", text, re.DOTALL)
        if match:
            return len(re.findall(r"['\"]", match.group(1))) // 2
        return None if "install_requires" in text else 0     # a variable or call we cannot read is unknown, not zero
    return None


BYTES_PER_LINE = 40          # rough average for Python with docstrings; the estimate, not the measure


def evaluate_metadata(repo: dict) -> dict:
    """Candidate check from the GitHub API alone: licence, estimated size, tests present, dependencies."""
    name = repo["full_name"]
    row = {
        "repo": name, "url": repo["html_url"], "licence": (repo.get("license") or {}).get("spdx_id", ""),
        "stars": repo["stargazers_count"], "description": (repo.get("description") or "")[:100],
        "sha": "", "loc": 0, "tests": 0, "seconds": 0.0, "verdict": "", "reason": "",
    }
    if (row["licence"] or "").lower() not in LICENCES:
        row.update(verdict="rejected", reason=f"licence {row['licence'] or 'not detected'} is not permissive")
        return row
    if repo.get("archived") or repo.get("fork"):
        row.update(verdict="rejected", reason="archived or a fork")
        return row
    branch = repo.get("default_branch", "HEAD")
    tree = gh_json(f"repos/{name}/git/trees/{branch}?recursive=1")
    if not tree or tree.get("truncated"):
        row.update(verdict="rejected", reason="file tree unavailable or too large")
        return row
    row["sha"] = tree["sha"]
    blobs = [b for b in tree["tree"] if b["type"] == "blob"]
    py = [b for b in blobs if b["path"].endswith(".py")]
    src_bytes, test_files = 0, 0
    for blob in py:
        parts = blob["path"].split("/")
        base = parts[-1]
        if set(parts[:-1]) & {"tests", "test", "testing"} or base.startswith("test_") or base.endswith("_test.py"):
            test_files += 1
        elif not (set(parts[:-1]) & NON_SOURCE) and base not in NON_SOURCE_FILES:
            src_bytes += blob.get("size", 0)
    row["loc"] = src_bytes // BYTES_PER_LINE
    row["tests"] = test_files                      # test *files*; the count of tests is only known after --verify
    if not (MIN_LOC * 0.7 <= row["loc"] <= MAX_LOC * 1.2):
        row.update(verdict="rejected", reason=f"about {row['loc']} source lines, outside the size band")
        return row
    if test_files < 2:
        row.update(verdict="rejected", reason=f"{test_files} test file(s)")
        return row
    deps = declared_dependencies(name, {b["path"] for b in blobs if "/" not in b["path"]})
    if deps:
        row.update(verdict="rejected", reason=f"declares {deps} runtime dependenc{'y' if deps == 1 else 'ies'}")
        return row
    row.update(verdict="candidate", reason="" if deps == 0 else "dependencies not declared in a file we can read")
    return row


def evaluate(repo: dict, workdir: Path, timeout: float) -> dict:
    name = repo["full_name"]
    row = {
        "repo": name, "url": repo["html_url"], "licence": (repo.get("license") or {}).get("spdx_id", ""),
        "stars": repo["stargazers_count"], "description": (repo.get("description") or "")[:100],
        "sha": "", "loc": 0, "tests": 0, "seconds": 0.0, "verdict": "", "reason": "",
    }
    target = workdir / name.replace("/", "__")
    try:
        subprocess.run(["git", "clone", "--depth", "1", "-q", repo["clone_url"], str(target)],
                       capture_output=True, check=True, timeout=180)
        row["sha"] = subprocess.run(["git", "-C", str(target), "rev-parse", "HEAD"], capture_output=True,
                                    text=True, check=True).stdout.strip()
    except (subprocess.SubprocessError, OSError) as exc:
        row.update(verdict="rejected", reason=f"clone failed: {exc}"[:80])
        return row

    files = source_files(target)
    row["loc"] = count_loc(files)
    if not MIN_LOC <= row["loc"] <= MAX_LOC:
        row.update(verdict="rejected", reason=f"{row['loc']} source lines is outside {MIN_LOC} to {MAX_LOC}")
        return row

    counts: list[int] = []
    for attempt in range(1, ROUNDS + 1):
        run = run_pytest(target, timeout, "require", targets=("-o", "addopts="))
        if run.status != "passed":
            detail = run.message or run.test or "no detail"
            row.update(verdict="rejected", reason=f"round {attempt}: tests {run.status}: {detail}"[:110])
            return row
        passed = TEST_COUNT_RE.search(run.output)
        counts.append(int(passed.group(1)) if passed else 0)
    row["tests"] = min(counts)
    if row["tests"] < MIN_TESTS:
        row.update(verdict="rejected", reason=f"only {row['tests']} tests")
        return row
    row.update(verdict="accepted", reason="")
    return row


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--verify", action="store_true",
                        help="Clone each repo and run its tests in the sandbox (executes third-party code).")
    parser.add_argument("--workdir", type=Path, help="An empty directory for the clones (--verify only).")
    parser.add_argument("--out", type=Path, default=Path("data/repos.csv"))
    parser.add_argument("--seeds", type=Path, help="File of owner/name lines to evaluate instead of searching.")
    parser.add_argument("--min-stars", type=int, default=150)
    parser.add_argument("--limit", type=int, default=120, help="Evaluate at most this many candidates.")
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--jobs", type=int, default=3)
    parser.add_argument("--keep", action="store_true", help="Keep the clones of accepted repos.")
    args = parser.parse_args()

    if args.verify:
        if not args.workdir:
            sys.exit("--verify needs --workdir, an empty directory for the clones")
        if args.workdir.exists() and any(args.workdir.iterdir()):
            sys.exit(f"{args.workdir} is not empty; clones of unknown code go in a fresh directory")
        args.workdir.mkdir(parents=True, exist_ok=True)

    pool = seeded(args.seeds) if args.seeds else candidates(args.min_stars, args.limit)
    print(f"{len(pool)} repos to evaluate", flush=True)
    if args.verify:
        # Only what passed the API checks (permissive licence, size, tests, no dependencies) is ever cloned or run.
        with ThreadPoolExecutor(max_workers=args.jobs) as executor:
            passed = [r for r, m in zip(pool, executor.map(evaluate_metadata, pool), strict=True)
                      if m["verdict"] == "candidate"]
        print(f"verifying {len(passed)} of {len(pool)}: {', '.join(r['full_name'] for r in passed)}", flush=True)
        pool = passed

    rows: list[dict] = []
    with ThreadPoolExecutor(max_workers=args.jobs) as executor:
        check = (lambda r: evaluate(r, args.workdir, args.timeout)) if args.verify else evaluate_metadata
        for row in executor.map(check, pool):
            rows.append(row)
            good = row["verdict"] in ("accepted", "candidate")
            unit = "tests" if args.verify else "test files"
            print(f"{'ok ' if good else '   '}{row['repo']:<42}{row['loc']:>5} loc {row['tests']:>4} {unit}  {row['reason']}",
                  flush=True)
            if args.verify and row["verdict"] != "accepted" and not args.keep:
                shutil.rmtree(args.workdir / row["repo"].replace("/", "__"), ignore_errors=True)

    rows.sort(key=lambda r: (r["verdict"] not in ("accepted", "candidate"), -r["stars"]))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    fields = ["repo", "url", "sha", "licence", "stars", "loc", "tests", "verdict", "reason", "description"]
    with args.out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    kept = sum(r["verdict"] in ("accepted", "candidate") for r in rows)
    label = "accepted" if args.verify else "candidates (unverified: nothing was downloaded or run)"
    print(f"\n{kept} {label} of {len(rows)} evaluated; written to {args.out}")


if __name__ == "__main__":
    main()

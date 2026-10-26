"""Fetch the exact commits recorded in data/repos_verified.csv into a fresh directory. Runs no repository code.

    .venv/bin/python scripts/fetch_pinned.py --dest /path/to/new/empty/dir pyflakes tabulate schema ...

Only `git init`, `git fetch --depth 1 <sha>` and `git checkout` are used: nothing from the repository is imported, built,
installed or tested, and no hook exists in a repository that was just initialised. Running a project's tests is a separate
step (`data-inject`, `data-assemble`) that executes third-party code inside the sandbox and needs its own approval.

Guards: only rows marked `accepted`, only https://github.com/ URLs, a destination that is missing or empty, a 40-character
SHA, and the checked-out HEAD must equal the pinned SHA. Names match the repo's short name (`python-` prefix optional).
"""

from __future__ import annotations

import argparse
import csv
import os
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = REPO_ROOT / "data" / "repos_verified.csv"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
URL_PREFIX = "https://github.com/"
LICENCE_NAMES = ("LICENSE", "LICENCE", "COPYING")


class FetchError(RuntimeError):
    pass


def short_names(repo: str) -> set[str]:
    base = repo.split("/")[-1].lower()
    return {base, base.removeprefix("python-")}


def select(rows: list[dict], names: list[str]) -> list[dict]:
    """The accepted row for each requested name; an unknown, rejected or ambiguous name is an error."""
    accepted = [r for r in rows if r["verdict"] == "accepted"]
    chosen: list[dict] = []
    for name in names:
        hits = [r for r in accepted if name.lower() in short_names(r["repo"]) or name.lower() == r["repo"].lower()]
        if not hits:
            rejected = [r["repo"] for r in rows if r["verdict"] != "accepted" and name.lower() in short_names(r["repo"])]
            raise FetchError(f"{name!r} is not an accepted repo in the CSV" + (" (it was rejected)" if rejected else ""))
        if len(hits) > 1:
            raise FetchError(f"{name!r} is ambiguous: {', '.join(r['repo'] for r in hits)}")
        if hits[0] not in chosen:
            chosen.append(hits[0])
    return chosen


def _git(*args: str, cwd: Path | None = None) -> str:
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    proc = subprocess.run(["git", *args], cwd=cwd, env=env, capture_output=True, text=True, timeout=300)
    if proc.returncode != 0:
        raise FetchError(f"git {args[0]} failed: {proc.stderr.strip()[:200]}")
    return proc.stdout.strip()


def fetch_pinned(url: str, sha: str, target: Path) -> dict:
    if not SHA_RE.match(sha):
        raise FetchError(f"{sha!r} is not a full 40-character SHA")
    if target.exists():
        raise FetchError(f"{target} already exists; fetch into a fresh directory")
    target.mkdir(parents=True)
    _git("init", "-q", cwd=target)
    _git("remote", "add", "origin", url, cwd=target)
    _git("fetch", "--depth", "1", "-q", "origin", sha, cwd=target)
    _git("checkout", "-q", "--detach", "FETCH_HEAD", cwd=target)
    head = _git("rev-parse", "HEAD", cwd=target)
    if head != sha:
        raise FetchError(f"checked out {head}, expected {sha}")
    licences = sorted(p.name for p in target.iterdir() if p.name.upper().startswith(LICENCE_NAMES))
    return {"head": head, "licence_files": licences}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("names", nargs="+", help="Short repo names, e.g. pyflakes tabulate schema.")
    parser.add_argument("--dest", required=True, type=Path, help="A directory that does not exist yet, or is empty.")
    parser.add_argument("--csv", type=Path, default=CSV_PATH)
    args = parser.parse_args(argv)

    dest: Path = args.dest.expanduser()
    if dest.exists() and any(dest.iterdir()):
        print(f"{dest} is not empty; unknown code goes in a fresh directory", file=sys.stderr)
        return 1
    rows = list(csv.DictReader(args.csv.open(encoding="utf-8")))
    try:
        chosen = select(rows, args.names)
        for row in chosen:
            if not row["url"].startswith(URL_PREFIX):
                raise FetchError(f"{row['repo']}: url {row['url']!r} is not under {URL_PREFIX}")
        if dest.exists():
            dest.rmdir()                                        # empty: recreate below so each repo gets its own folder
        for row in chosen:
            name = row["repo"].split("/")[-1]
            info = fetch_pinned(row["url"], row["sha"], dest / name)
            print(f"{name}: {info['head'][:12]}  licence files: {', '.join(info['licence_files']) or 'NONE FOUND'}")
    except FetchError as exc:
        print(f"stopped: {exc}", file=sys.stderr)
        return 1
    print(f"\nfetched into {dest}. Nothing was executed. Read each LICENSE before using the repo.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

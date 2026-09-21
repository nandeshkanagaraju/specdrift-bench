#!/usr/bin/env bash
# The 90-second demo: a check is deleted, its comment is left behind, and we see
# which detector notices. The host project is never modified - every case is built
# into work/<case id>/ - so this script is safe to run repeatedly.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

SPECDRIFT="${SPECDRIFT:-$ROOT/.venv/bin/specdrift}"
[ -x "$SPECDRIFT" ] || SPECDRIFT="specdrift"

# The helpers below import yaml, so they need the interpreter specdrift is installed into.
PYTHON="${PYTHON:-$ROOT/.venv/bin/python}"
[ -x "$PYTHON" ] || PYTHON="python3"

CASE="library-D7-01"
RULE="R09"

bold() { printf "\n\033[1m%s\033[0m\n" "$1"; }
dim()  { printf "\033[2m%s\033[0m\n" "$1"; }

bold "1. The rule, as written in projects/library/spec.md"
grep -E "\*\*${RULE}\*\*" projects/library/spec.md

bold "2. The change (category D7, comment decoy)"
dim "The suspension check is deleted. The comment above it still says it is enforced."
"$PYTHON" - "$CASE" <<'PY'
import difflib, sys, yaml
from pathlib import Path

case_id = sys.argv[1]
case = next(
    c for c in yaml.safe_load(Path("cases/library.yaml").read_text()) if c["id"] == case_id
)
join = lambda v: "\n".join(v) if isinstance(v, list) else (v or "")
before = Path("projects/library") / case["file"]
original = before.read_text()
patched = original.replace(join(case["find"]), join(case["replace"]), 1)

diff = difflib.unified_diff(
    original.splitlines(), patched.splitlines(),
    fromfile=f"a/{case['file']}", tofile=f"b/{case['file']}", lineterm="", n=3,
)
for line in diff:
    if line.startswith("+") and not line.startswith("+++"):
        print(f"\033[32m{line}\033[0m")
    elif line.startswith("-") and not line.startswith("---"):
        print(f"\033[31m{line}\033[0m")
    else:
        print(f"\033[2m{line}\033[0m")
PY

bold "3. Build the case into its own workspace"
"$SPECDRIFT" build --case "$CASE" >/dev/null
dim "work/$CASE/ now holds the patched copy."

bold "4. Does the project's own test suite notice?"
if (cd "work/$CASE" && "$PYTHON" -m pytest -q -p no:cacheprovider >/dev/null 2>&1); then
  printf "\033[33m   No. Every test still passes.\033[0m\n"
else
  printf "\033[32m   Yes - the test suite fails on this one.\033[0m\n"
fi

bold "5. The keyword baseline"
"$PYTHON" - "$CASE" "$RULE" <<'PY'
import sys

from specdrift.baselines.keyword import KeywordDetector
from specdrift.bench.pipeline import load_built
from specdrift.config import get_settings

case_id, rule_id = sys.argv[1], sys.argv[2]
settings = get_settings()
case = next(row for row in load_built(settings) if row.case_id == case_id)

verdict = next(v for v in KeywordDetector(settings).run_case(case) if v.rule_id == rule_id)
colour = "\033[31m" if verdict.verdict == "DRIFT" else "\033[33m"
print(f"   {rule_id}: {colour}{verdict.verdict}\033[0m (confidence {verdict.confidence:.2f})")
print("   \033[2mThe rule's words all still appear - in the comment that lies.\033[0m")
PY

bold "6. SpecGuard"
set +e
"$SPECDRIFT" check "work/$CASE"
STATUS=$?
set -e

bold "Done"
dim "specdrift check exited $STATUS (1 means drift was found)."
dim "Nothing under projects/ was modified; the patched copy lives in work/$CASE/."

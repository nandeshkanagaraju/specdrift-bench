#!/bin/bash
# The four steps of the pilot recipe that EXECUTE a cloned library's tests (inside the sandbox):
#   data-inject --focus-rules, data-inject --benign, data-assemble (focus), data-assemble (benign).
# Each uses --sandbox require, so it stops instead of running unsandboxed. Output goes to the terminal and to
#   /Users/nandeshjeya/Documents/Academic/MiniProject/clones8_logs/<name>.log
#
#   bash scripts/pilot_repo.sh <name> [subdir] [clone-dir-name]       e.g.  bash scripts/pilot_repo.sh iniconfig src
#   DRY=1 bash scripts/pilot_repo.sh iniconfig src                    prints the commands, runs nothing
#
# Needs data/pilot/<name>/rules.json (prompt A's answer) and the rendered spec.md, rules.yaml and oracles/ in the clone.

NAME="${1:?usage: pilot_repo.sh <name> [subdir] [clone-dir-name]}"
SUBDIR="${2:-src}"
CLONE="/Users/nandeshjeya/Documents/Academic/MiniProject/clones8/${3:-$NAME}"
PY="${PY:-/Users/nandeshjeya/Documents/Academic/MiniProject/specdrift-bench/.venv/bin/python}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOGDIR="/Users/nandeshjeya/Documents/Academic/MiniProject/clones8_logs"
LOG="$LOGDIR/$NAME.log"

mkdir -p "$LOGDIR" || { echo "cannot create $LOGDIR"; exit 2; }

step() {
    echo
    echo "\$ $*"
    if [ "${DRY:-0}" = "1" ]; then
        return 0
    fi
    "$@"
    local code=$?
    echo "[exit $code]"
    return $code
}

{
    echo "pilot_repo $NAME  subdir=$SUBDIR  clone=$CLONE  dry=${DRY:-0}  $(date)"
    cd "$ROOT" || { echo "cannot cd to $ROOT"; exit 2; }
    [ -d "$CLONE" ] || { echo "no clone at $CLONE"; exit 2; }
    [ -f "data/pilot/$NAME/rules.json" ] || { echo "no data/pilot/$NAME/rules.json"; exit 2; }
    [ -f "$CLONE/rules.yaml" ] || { echo "no rules.yaml in the clone; render the rules first"; exit 2; }

    step "$PY" -B -m specdrift.cli data-inject "$CLONE" --name "$NAME" --subdir "$SUBDIR" \
        --focus-rules "data/pilot/$NAME/rules.json" --sandbox require \
        --out "data/pilot/$NAME.focus.mutants.jsonl" || exit 1
    step "$PY" -B -m specdrift.cli data-inject "$CLONE" --name "$NAME" --subdir "$SUBDIR" \
        --benign --sandbox require --out "data/pilot/$NAME.benign.mutants.jsonl" || exit 1
    step "$PY" -B -m specdrift.cli data-assemble "$CLONE" --mutants "data/pilot/$NAME.focus.mutants.jsonl" \
        --subdir "$SUBDIR" --name "$NAME" --sandbox require --out "data/pilot/$NAME.focus.stage_b.jsonl" || exit 1
    step "$PY" -B -m specdrift.cli data-assemble "$CLONE" --mutants "data/pilot/$NAME.benign.mutants.jsonl" \
        --subdir "$SUBDIR" --name "$NAME" --sandbox require --out "data/pilot/$NAME.benign.stage_b.jsonl" || exit 1
    echo
    echo "all four steps finished"
} 2>&1 | tee "$LOG"
code=${PIPESTATUS[0]}
echo
echo "script exit: $code   log: $LOG"
exit "$code"

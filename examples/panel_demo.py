"""Upload each example project to a running `specdrift serve` and score the result.

    python examples/panel_demo.py [project ...] [--url http://127.0.0.1:8000] [--zips]

Every project has planted drift listed in expected.json, and its own tests pass.
The script prints, per rule, what SpecGuard said against what was planted.
--zips only writes examples/zips/<project>.zip for uploading by hand on /yours.
"""

from __future__ import annotations

import argparse
import io
import json
import sys
import urllib.request
import zipfile
from pathlib import Path

HERE = Path(__file__).parent
SKIP = {"tests", "__pycache__", ".pytest_cache"}
SKIP_FILES = {"pytest.ini"}


def build_zip(project: Path) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(project.rglob("*")):
            rel = path.relative_to(project)
            if path.is_dir() or SKIP & set(rel.parts) or rel.name in SKIP_FILES:
                continue
            zf.write(path, rel.as_posix())
    return buf.getvalue()


def post(url: str, data: bytes, ctype: str) -> urllib.request.addinfourl:
    req = urllib.request.Request(url, data, {"Content-Type": ctype})
    return urllib.request.urlopen(req, timeout=300)


def run(base: str, name: str, key: dict) -> dict[str, str]:
    upload = json.load(post(f"{base}/api/uploads/archive?name={name}", build_zip(HERE / name), "application/zip"))
    print(f"\n=== {name}: {len(upload['rules'])} rules, {len(upload['files'])} files (upload {upload['id']})")
    body = json.dumps({"upload_id": upload["id"]}).encode()
    verdicts: dict[str, dict] = {}
    event = ""
    for raw in post(f"{base}/api/check", body, "application/json"):
        line = raw.decode().rstrip("\n")
        if line.startswith("event: "):
            event = line[7:]
        elif line.startswith("data: ") and event == "verdict":
            payload = json.loads(line[6:])
            verdicts[payload["rule_id"]] = payload
    planted = key["drift"]
    caught = false_alarm = unsure = 0
    for rule in upload["rules"]:
        rid = rule["id"]
        got = verdicts.get(rid, {}).get("verdict", "?")
        want = "DRIFT" if rid in planted else "COMPLIANT"
        ok = got == want
        if ok:
            mark = "ok  "
        elif want == "DRIFT":
            mark = "MISS"
        elif got == "DRIFT":
            mark = "FALSE"
        else:
            mark = "unsr"
        caught += ok and want == "DRIFT"
        false_alarm += mark == "FALSE"
        unsure += mark == "unsr"
        print(f"  {mark} {rid}  planted={want:9} found={got:9} {rule['text'][:62]}")
        v = verdicts.get(rid, {})
        if got == "DRIFT" and v.get("evidence"):
            ev = v["evidence"]
            cx = v.get("counterexample") or {}
            print(f"        -> {ev['file']}:{ev['start_line']}  {cx.get('input','')} expected {cx.get('expected','')} got {cx.get('actual','')}")
        if want == "DRIFT" and not ok:
            print(f"        planted: {planted[rid]}")
    print(f"  planted drift caught {caught}/{len(planted)}, false alarms {false_alarm}, unsure on clean rules {unsure}")
    if key.get("unspecified"):
        print(f"  not rule-based (reverse check): {key['unspecified']}")
    return {"caught": caught, "planted": len(planted), "false": false_alarm, "unsure": unsure}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("projects", nargs="*")
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    ap.add_argument("--zips", action="store_true")
    args = ap.parse_args()
    expected = json.loads((HERE / "expected.json").read_text())
    names = args.projects or list(expected)
    if args.zips:
        out = HERE / "zips"
        out.mkdir(exist_ok=True)
        for name in names:
            (out / f"{name}.zip").write_bytes(build_zip(HERE / name))
            print(f"wrote {out / name}.zip")
        return 0
    totals = [run(args.url, n, expected[n]) for n in names]
    print(
        f"\nTOTAL caught {sum(t['caught'] for t in totals)}/{sum(t['planted'] for t in totals)}"
        f" planted drifts, {sum(t['false'] for t in totals)} false alarms,"
        f" {sum(t['unsure'] for t in totals)} unsure on clean rules"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

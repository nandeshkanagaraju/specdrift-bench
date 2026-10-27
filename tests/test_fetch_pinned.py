import csv
import importlib.util
import subprocess

import pytest

from specdrift.config import REPO_ROOT

spec = importlib.util.spec_from_file_location("fetch_pinned", REPO_ROOT / "scripts" / "fetch_pinned.py")
fp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fp)

EIGHT = ["pyflakes", "tabulate", "schema", "xmltodict", "iniconfig", "flashtext", "colorama", "tomli"]


def git(cwd, *args):
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=cwd, check=True,
                          capture_output=True, text=True).stdout.strip()


@pytest.fixture
def origin(tmp_path):
    """A local repo with two commits; the first is the one a test pins."""
    root = tmp_path / "origin"
    root.mkdir()
    git(root, "init", "-q")
    git(root, "config", "uploadpack.allowAnySHA1InWant", "true")
    (root / "LICENSE").write_text("MIT\n")
    (root / "a.py").write_text("VALUE = 1\n")
    git(root, "add", ".")
    git(root, "commit", "-q", "-m", "one")
    first = git(root, "rev-parse", "HEAD")
    (root / "a.py").write_text("VALUE = 2\n")
    git(root, "commit", "-q", "-am", "two")
    return root, first


def row(repo, sha="a" * 40, verdict="accepted", url="https://github.com/o/r"):
    return {"repo": repo, "url": url, "sha": sha, "verdict": verdict}


def test_it_checks_out_the_pinned_commit_not_the_latest_one(origin, tmp_path):
    root, first = origin
    info = fp.fetch_pinned(str(root), first, tmp_path / "out" / "repo")

    assert info == {"head": first, "licence_files": ["LICENSE"]}
    assert (tmp_path / "out" / "repo" / "a.py").read_text() == "VALUE = 1\n"       # commit one, not two


def test_a_short_or_malformed_sha_is_refused_before_anything_is_created(origin, tmp_path):
    root, first = origin
    for bad in (first[:12], first.upper(), "HEAD", ""):
        with pytest.raises(fp.FetchError, match="40-character"):
            fp.fetch_pinned(str(root), bad, tmp_path / "x")
    assert not (tmp_path / "x").exists()


def test_an_existing_target_is_refused_and_left_alone(origin, tmp_path):
    root, first = origin
    (tmp_path / "taken").mkdir()
    (tmp_path / "taken" / "keep.txt").write_text("mine")
    with pytest.raises(fp.FetchError, match="already exists"):
        fp.fetch_pinned(str(root), first, tmp_path / "taken")
    assert (tmp_path / "taken" / "keep.txt").read_text() == "mine"


def test_a_commit_that_does_not_exist_fails_loudly(origin, tmp_path):
    root, _ = origin
    with pytest.raises(fp.FetchError, match="git fetch failed"):
        fp.fetch_pinned(str(root), "f" * 40, tmp_path / "out")


def test_a_checkout_that_lands_on_a_different_commit_is_an_error(tmp_path, monkeypatch):
    monkeypatch.setattr(fp, "_git", lambda *args, cwd=None: "e" * 40 if args[0] == "rev-parse" else "")
    with pytest.raises(fp.FetchError, match="expected " + "d" * 40):
        fp.fetch_pinned("https://github.com/o/r", "d" * 40, tmp_path / "out")


def test_names_resolve_to_accepted_rows_only():
    rows = [row("PyCQA/pyflakes"), row("python-semver/python-semver"), row("astanin/python-tabulate"),
            row("hukkin/tomli"), row("hukkin/tomli-w", verdict="rejected"), row("pallets/markupsafe", verdict="rejected")]
    assert [r["repo"] for r in fp.select(rows, ["pyflakes", "semver", "tabulate", "tomli"])] == [
        "PyCQA/pyflakes", "python-semver/python-semver", "astanin/python-tabulate", "hukkin/tomli"]
    assert [r["repo"] for r in fp.select(rows, ["PyCQA/pyflakes", "pyflakes"])] == ["PyCQA/pyflakes"]    # no duplicates
    with pytest.raises(fp.FetchError, match="was rejected"):
        fp.select(rows, ["markupsafe"])
    with pytest.raises(fp.FetchError, match="tomli-w"):
        fp.select(rows, ["tomli-w"])
    with pytest.raises(fp.FetchError, match="not an accepted repo"):
        fp.select(rows, ["nonesuch"])
    with pytest.raises(fp.FetchError, match="ambiguous"):
        fp.select([row("a/x"), row("b/x")], ["x"])


def test_the_real_csv_resolves_all_eight_repos_to_their_pinned_shas(tmp_path, monkeypatch):
    asked = []
    monkeypatch.setattr(fp, "fetch_pinned",
                        lambda url, sha, target: asked.append((url, sha, target.name)) or {"head": sha, "licence_files": []})

    assert fp.main(["--dest", str(tmp_path / "new"), *EIGHT]) == 0

    csv_rows = {r["repo"].split("/")[-1]: r for r in csv.DictReader(fp.CSV_PATH.open())}
    assert [a[2] for a in asked] == ["pyflakes", "python-tabulate", "schema", "xmltodict", "iniconfig", "flashtext",
                                    "colorama", "tomli"]
    for url, sha, name in asked:
        assert sha == csv_rows[name]["sha"] and len(sha) == 40 and url.startswith("https://github.com/")


def test_a_non_empty_destination_is_refused_without_fetching(tmp_path, monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(fp, "fetch_pinned", lambda *a: calls.append(a))
    (tmp_path / "busy").mkdir()
    (tmp_path / "busy" / "file").write_text("x")

    assert fp.main(["--dest", str(tmp_path / "busy"), "pyflakes"]) == 1

    assert calls == [] and "not empty" in capsys.readouterr().err


def test_only_github_https_urls_are_ever_fetched(tmp_path, monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(fp, "fetch_pinned", lambda *a: calls.append(a))
    bad = tmp_path / "repos.csv"
    with bad.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["repo", "url", "sha", "verdict"])
        writer.writeheader()
        writer.writerow(row("o/evil", url="git@evil.example:o/evil.git", sha="b" * 40))

    assert fp.main(["--dest", str(tmp_path / "d"), "--csv", str(bad), "evil"]) == 1

    assert calls == [] and "not under https://github.com/" in capsys.readouterr().err

"""Turn a user-supplied spec and Python sources into a workspace the checker can read.

The live checker already accepts any directory that holds ``spec.md`` plus Python
under ``src/``. This module is the front door for a project that is not one of the
three built-in hosts: pasted files, or a zip of the same shape.
"""

from __future__ import annotations

import ast
import io
import re
import secrets
import zipfile
from dataclasses import dataclass
from pathlib import Path

from specdrift.bench.schema import Rule
from specdrift.code.chunker import chunk_workspace
from specdrift.config import Settings
from specdrift.spec.parser import DuplicateRuleError, parse_spec_text

MAX_TOTAL_BYTES = 1_500_000
MAX_FILES = 30
MAX_FILE_BYTES = 150_000
MAX_RULES = 80

_ID_RE = re.compile(r"^[a-f0-9]{16}$")
_SKIP_PARTS = {
    ".git",
    ".idea",
    ".vscode",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    "node_modules",
    "dist",
    "build",
    "tests",
}


class IntakeError(ValueError):
    """The submission cannot be checked, and the message is safe to show."""


@dataclass(frozen=True)
class UploadedFile:
    path: str
    lines: int
    source: str


@dataclass(frozen=True)
class UploadRecord:
    id: str
    name: str
    rules: list[Rule]
    files: list[UploadedFile]
    warnings: list[str]
    root: Path
    spec_path: str = ""


# A file with one of these names is the specification even if another markdown
# file happens to contain a numbered rule. Anything else is a spec only when it
# actually contains rules.
_SPEC_NAMES = ("spec.md", "specification.md", "specs.md")


def upload_root(settings: Settings, upload_id: str) -> Path | None:
    """The workspace for a previous upload, or None when the id is unknown or unsafe."""
    if not _ID_RE.fullmatch(upload_id):
        return None
    root = settings.work_dir / "uploads" / upload_id
    if not (root / "spec.md").is_file():
        return None
    return root


def load_upload(settings: Settings, upload_id: str) -> UploadRecord | None:
    root = upload_root(settings, upload_id)
    if root is None:
        return None
    spec = (root / "spec.md").read_text(encoding="utf-8")
    rules = parse_spec_text(spec)
    files = _read_sources(root)
    name = (root / "name.txt").read_text(encoding="utf-8").strip() if (root / "name.txt").exists() else "upload"
    return UploadRecord(id=upload_id, name=name, rules=rules, files=files, warnings=[], root=root)


def materialize_files(
    settings: Settings,
    name: str,
    spec_text: str,
    files: list[tuple[str, str]],
) -> UploadRecord:
    """Write a pasted spec and source files into a fresh workspace."""
    safe = [(_safe_relative(path), source) for path, source in files]
    return _materialize(settings, name, spec_text, safe, from_archive=False)


def materialize_zip(settings: Settings, name: str, data: bytes) -> UploadRecord:
    """Write a zip of ``spec.md`` plus Python sources into a fresh workspace."""
    entries, warnings = _read_zip(data)
    spec_path, spec_text, sources, pick_warnings = _pick_spec_and_sources(entries)
    return _materialize(
        settings,
        name,
        spec_text,
        sources,
        from_archive=True,
        extra_warnings=warnings + pick_warnings,
        spec_path=spec_path,
    )


def _materialize(
    settings: Settings,
    name: str,
    spec_text: str,
    files: list[tuple[str, str]],
    *,
    from_archive: bool,
    extra_warnings: list[str] | None = None,
    spec_path: str = "",
) -> UploadRecord:
    if not from_archive:
        spec_path, spec_text, files, extra_warnings = _normalize_pasted(spec_text, files)

    warnings = list(extra_warnings or [])
    rules = _rules_or_raise(spec_text)
    if not files:
        raise IntakeError("Add at least one Python file. The checker has nothing to read.")
    if len(files) > MAX_FILES:
        raise IntakeError(f"Too many files ({len(files)}). The limit is {MAX_FILES}.")

    total = len(spec_text.encode("utf-8"))
    for path, source in files:
        size = len(source.encode("utf-8"))
        if size > MAX_FILE_BYTES:
            raise IntakeError(f"{path} is larger than {MAX_FILE_BYTES // 1000} KB.")
        total += size
    if total > MAX_TOTAL_BYTES:
        raise IntakeError("That project is larger than 1.5 MB of text.")

    readable = 0
    for path, source in files:
        try:
            ast.parse(source)
        except SyntaxError as exc:
            warnings.append(f"{path} does not parse ({exc.msg}, line {exc.lineno}) and will be skipped.")
        else:
            readable += 1
    if readable == 0:
        raise IntakeError("None of the Python files parse, so there is no code to check.")

    upload_id = secrets.token_hex(8)
    root = settings.work_dir / "uploads" / upload_id
    src = root / "src"
    src.mkdir(parents=True)
    (root / "spec.md").write_text(spec_text, encoding="utf-8")
    (root / "name.txt").write_text(_slug(name), encoding="utf-8")

    written: list[UploadedFile] = []
    for path, source in files:
        relative = path[4:] if path.startswith("src/") else path
        dest = src / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(source, encoding="utf-8")
        stored = dest.relative_to(root).as_posix()
        written.append(UploadedFile(path=stored, lines=source.count("\n") + 1, source=source))

    if not chunk_workspace(root):
        raise IntakeError("The Python parsed, but it contains no checkable code.")

    written.sort(key=lambda item: item.path)
    return UploadRecord(
        id=upload_id,
        name=_slug(name),
        rules=rules,
        files=written,
        warnings=warnings,
        root=root,
        spec_path=spec_path or "spec.md",
    )


def _normalize_pasted(
    spec_text: str,
    files: list[tuple[str, str]],
) -> tuple[str, str, list[tuple[str, str]], list[str]]:
    """A paste or a folder may include the spec as one of the files."""
    warnings: list[str] = []
    spec_path = ""
    if spec_text.strip():
        if any(_is_spec_candidate(path) for path, _ in files):
            warnings.append("A specification was pasted as well as found in the files. The pasted text is the one checked.")
    else:
        spec_path, spec_text, found = _select_spec(files)
        warnings.extend(found)

    sources = [(path, source) for path, source in files if path.endswith(".py")]
    sources, pick_warnings = _prefer_src(sources)
    return spec_path, spec_text, sources, warnings + pick_warnings


def _pick_spec_and_sources(
    entries: list[tuple[str, str]],
) -> tuple[str, str, list[tuple[str, str]], list[str]]:
    entries = _strip_common_root(entries)
    sources = [
        (path, text)
        for path, text in entries
        if path.endswith(".py") and "tests" not in Path(path).parts
    ]
    skipped_tests = sum(
        1 for path, _ in entries if path.endswith(".py") and "tests" in Path(path).parts
    )
    warnings: list[str] = []
    if skipped_tests:
        warnings.append(
            f"Skipped {skipped_tests} file(s) under tests/. The checker reads the implementation."
        )
    sources, src_warnings = _prefer_src(sources)
    spec_path, spec_text, found = _select_spec(entries)
    return spec_path, spec_text, sources, warnings + src_warnings + found


def _prefer_src(sources: list[tuple[str, str]]) -> tuple[list[tuple[str, str]], list[str]]:
    under_src = [(path, text) for path, text in sources if path == "src" or path.startswith("src/")]
    if under_src and len(under_src) < len(sources):
        return under_src, ["A src/ directory is present, so only the files inside it are checked."]
    return sources, []


def _is_spec_candidate(path: str) -> bool:
    return Path(path).name.lower() in _SPEC_NAMES or path.lower().endswith(".md")


def _select_spec(entries: list[tuple[str, str]]) -> tuple[str, str, list[str]]:
    """Pick the specification out of a folder's files.

    A file named spec.md, specification.md, or specs.md wins. Otherwise the
    markdown file with the most numbered rules is the spec.
    """
    named = [(path, text) for path, text in entries if Path(path).name.lower() in _SPEC_NAMES]
    if named:
        named.sort(
            key=lambda item: (
                item[0].count("/"),
                _SPEC_NAMES.index(Path(item[0]).name.lower()),
                item[0],
            )
        )
        best = named[0]
        same = [
            path
            for path, _ in named
            if path.count("/") == best[0].count("/")
            and Path(path).name.lower() == Path(best[0]).name.lower()
        ]
        if len(same) > 1:
            raise IntakeError(f"Found more than one {Path(best[0]).name}: {', '.join(same)}")
        return best[0], best[1], [f"Using {best[0]} as the specification."]

    ranked: list[tuple[int, str, str]] = []
    for path, text in entries:
        if not path.lower().endswith(".md"):
            continue
        try:
            count = len(parse_spec_text(text))
        except DuplicateRuleError as exc:
            raise IntakeError(f"{path}: {exc}") from exc
        if count:
            ranked.append((count, path, text))
    if not ranked:
        raise IntakeError(
            "No specification found. Add spec.md, or a markdown file with lines like - **R01** …"
        )
    ranked.sort(key=lambda item: (-item[0], item[1].count("/"), item[1]))
    count, path, text = ranked[0]
    return path, text, [f"Using {path} as the specification ({count} rules)."]


def _rules_or_raise(spec_text: str) -> list[Rule]:
    if not spec_text.strip():
        raise IntakeError("The specification is empty.")
    try:
        rules = parse_spec_text(spec_text)
    except DuplicateRuleError as exc:
        raise IntakeError(str(exc)) from exc
    if not rules:
        raise IntakeError(
            "No numbered rules found. Write each one as a list item, for example: "
            "- **R01** A member MUST be at least 18."
        )
    if len(rules) > MAX_RULES:
        raise IntakeError(f"Too many rules ({len(rules)}). The limit is {MAX_RULES}.")
    return rules


def _read_zip(data: bytes) -> tuple[list[tuple[str, str]], list[str]]:
    if not data:
        raise IntakeError("The archive is empty.")
    if len(data) > MAX_TOTAL_BYTES:
        raise IntakeError("The archive is larger than 1.5 MB.")
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise IntakeError("That file is not a zip archive.") from exc

    warnings: list[str] = []
    entries: list[tuple[str, str]] = []
    total = 0
    skipped_tests = 0
    for info in archive.infolist():
        if info.is_dir():
            continue
        raw_name = info.filename.replace("\\", "/")
        if raw_name.startswith("/") or raw_name.startswith("../") or "/../" in f"/{raw_name}/":
            raise IntakeError(f"The archive contains an unsafe path: {info.filename}")
        parts = [part for part in raw_name.split("/") if part not in ("", ".")]
        if any(part == ".." for part in parts):
            raise IntakeError(f"The archive contains an unsafe path: {info.filename}")
        if "tests" in parts and raw_name.endswith(".py"):
            skipped_tests += 1
            continue
        if any(part in _SKIP_PARTS or part.startswith(".") for part in parts):
            continue
        name = "/".join(parts)
        if not name.endswith(".py") and not name.lower().endswith(".md"):
            continue
        if info.file_size > MAX_FILE_BYTES:
            raise IntakeError(f"{name} is larger than {MAX_FILE_BYTES // 1000} KB.")
        total += info.file_size
        if total > MAX_TOTAL_BYTES:
            raise IntakeError("The uncompressed archive is larger than 1.5 MB.")
        try:
            text = archive.read(info).decode("utf-8")
        except UnicodeDecodeError as exc:
            raise IntakeError(f"{name} is not UTF-8 text.") from exc
        entries.append((name, text))
        if len(entries) > MAX_FILES:
            raise IntakeError(f"Too many files. The limit is {MAX_FILES}.")

    if skipped_tests:
        warnings.append(
            f"Skipped {skipped_tests} file(s) under tests/. The checker reads the implementation."
        )
    if not entries:
        warnings.append("The archive had no spec.md and no Python files in the places that are checked.")
    return entries, warnings


def _strip_common_root(entries: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Drop a single wrapping folder, the shape GitHub gives a downloaded zip."""
    parts = [path.split("/") for path, _ in entries]
    if not parts or any(len(item) < 2 for item in parts):
        return entries
    head = parts[0][0]
    if any(item[0] != head for item in parts):
        return entries
    return [("/".join(path.split("/")[1:]), text) for path, text in entries]


def _safe_relative(path: str) -> str:
    raw = path.replace("\\", "/").strip()
    if not raw:
        raise IntakeError("A file is missing its path.")
    parts = [part for part in raw.split("/") if part not in ("", ".")]
    if not parts or any(part == ".." for part in parts) or raw.startswith("/"):
        raise IntakeError(f"Unsafe path: {path}")
    if any(part in _SKIP_PARTS for part in parts):
        raise IntakeError(f"{path} sits in a directory the checker does not read.")
    return "/".join(parts)


def _read_sources(root: Path) -> list[UploadedFile]:
    files: list[UploadedFile] = []
    for path in sorted((root / "src").rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        files.append(
            UploadedFile(
                path=path.relative_to(root).as_posix(),
                lines=text.count("\n") + 1,
                source=text,
            )
        )
    return files


def _slug(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return (slug or "upload")[:40]

/**
 * Read a drop or a chosen folder into a spec plus the Python the checker should see.
 *
 * A folder is identified here the same way the server does: spec.md (or
 * specification.md / specs.md) wins, otherwise the markdown file with the most
 * numbered rules. Python under src/ is preferred when that directory exists.
 */
import { previewRules } from "./yours";

export interface DroppedSource {
  path: string;
  source: string;
}

export interface DroppedProject {
  kind: "files";
  spec: string | null;
  files: DroppedSource[];
  skipped: number;
}

export interface DroppedZip {
  kind: "zip";
  file: File;
}

const SPEC_NAMES = ["spec.md", "specification.md", "specs.md"];

export interface IdentifiedFolder {
  name: string;
  specPath: string;
  spec: string;
  files: DroppedSource[];
}

/** Turn a folder picked with a directory input into a spec and its Python sources. */
export async function identifyFolder(fileList: File[]): Promise<IdentifiedFolder> {
  const rows: { path: string; text: string }[] = [];
  for (const file of fileList) {
    const path = (file.webkitRelativePath || file.name).replaceAll("\\", "/");
    if (skippedPath(path)) continue;
    const base = path.split("/").pop()?.toLowerCase() ?? "";
    if (!base.endsWith(".py") && !base.endsWith(".md")) continue;
    rows.push({ path, text: await file.text() });
  }

  const root = sharedRoot(rows.map((row) => row.path));
  const relative = rows.map((row) => ({
    path: root ? row.path.slice(root.length + 1) : row.path,
    text: row.text,
  }));
  const spec = chooseSpec(relative);
  if (!spec) {
    throw new Error(
      "No specification found. Add spec.md, or a markdown file with lines like - **R01** …",
    );
  }

  let sources = relative.filter(
    (row) => row.path.endsWith(".py") && !row.path.split("/").includes("tests"),
  );
  const underSrc = sources.filter((row) => row.path === "src" || row.path.startsWith("src/"));
  if (underSrc.length > 0 && underSrc.length < sources.length) sources = underSrc;
  if (sources.length === 0) throw new Error("No Python files found in that folder.");

  return {
    name: root || "upload",
    specPath: spec.path,
    spec: spec.text,
    files: sources.map((row) => ({
      path: row.path.replace(/^src\//, ""),
      source: row.text,
    })),
  };
}

function skippedPath(path: string): boolean {
  return path.split("/").some((part) => SKIP.has(part) || part.startsWith("."));
}

function sharedRoot(paths: string[]): string {
  const heads = paths.map((path) => path.split("/")[0]);
  if (paths.length > 0 && paths.every((path) => path.includes("/")) && heads.every((head) => head === heads[0])) {
    return heads[0];
  }
  return "";
}

function chooseSpec(entries: { path: string; text: string }[]): { path: string; text: string } | null {
  const named = entries.filter((entry) =>
    SPEC_NAMES.includes(entry.path.split("/").pop()?.toLowerCase() ?? ""),
  );
  if (named.length > 0) {
    named.sort((a, b) => {
      const depth = a.path.split("/").length - b.path.split("/").length;
      if (depth !== 0) return depth;
      const rank =
        SPEC_NAMES.indexOf(a.path.split("/").pop()!.toLowerCase()) -
        SPEC_NAMES.indexOf(b.path.split("/").pop()!.toLowerCase());
      if (rank !== 0) return rank;
      return a.path.localeCompare(b.path);
    });
    return named[0];
  }

  const ranked = entries
    .filter((entry) => entry.path.toLowerCase().endsWith(".md"))
    .map((entry) => ({ entry, count: previewRules(entry.text).rules.length }))
    .filter((item) => item.count > 0)
    .sort(
      (a, b) =>
        b.count - a.count ||
        a.entry.path.split("/").length - b.entry.path.split("/").length ||
        a.entry.path.localeCompare(b.entry.path),
    );
  return ranked[0]?.entry ?? null;
}

const SKIP = new Set([
  "node_modules",
  ".git",
  ".venv",
  "__pycache__",
  "dist",
  "build",
  ".pytest_cache",
  "tests",
  ".idea",
  ".vscode",
]);

export async function readDrop(data: DataTransfer): Promise<DroppedProject | DroppedZip | null> {
  const entries = await entriesFrom(data);
  if (entries.length === 1 && entries[0].path.toLowerCase().endsWith(".zip")) {
    return { kind: "zip", file: entries[0].file };
  }

  const kept: { path: string; text: string }[] = [];
  let skipped = 0;

  for (const entry of entries) {
    const parts = entry.path.split("/");
    if (parts.some((part) => SKIP.has(part) || part.startsWith("."))) {
      skipped += 1;
      continue;
    }
    const name = parts[parts.length - 1].toLowerCase();
    if (!name.endsWith(".py") && !name.endsWith(".md")) {
      skipped += 1;
      continue;
    }
    kept.push({ path: entry.path, text: await entry.file.text() });
  }

  const spec = chooseSpec(kept);
  const files = kept
    .filter((entry) => entry.path.endsWith(".py"))
    .map((entry) => ({ path: entry.path, source: entry.text }))
    .sort((a, b) => a.path.localeCompare(b.path));

  if (!spec && files.length === 0) return null;
  return { kind: "files", spec: spec?.text ?? null, files, skipped };
}

interface ListedFile {
  path: string;
  file: File;
}

async function entriesFrom(data: DataTransfer): Promise<ListedFile[]> {
  const items = [...data.items];
  const webkit = items
    .map((item) => item.webkitGetAsEntry?.())
    .filter((entry): entry is FileSystemEntry => entry !== null && entry !== undefined);

  if (webkit.length > 0) {
    const nested = await Promise.all(webkit.map((entry) => walk(entry)));
    return nested.flat();
  }

  return [...data.files].map((file) => ({
    path: file.webkitRelativePath || file.name,
    file,
  }));
}

async function walk(entry: FileSystemEntry): Promise<ListedFile[]> {
  if (entry.isFile) {
    const file = await fileOf(entry as FileSystemFileEntry);
    const path = entry.fullPath.replace(/^\//, "") || file.name;
    return [{ path, file }];
  }
  if (!entry.isDirectory) return [];

  const reader = (entry as FileSystemDirectoryEntry).createReader();
  const children: FileSystemEntry[] = [];
  for (;;) {
    const batch = await readBatch(reader);
    if (batch.length === 0) break;
    children.push(...batch);
  }
  const nested = await Promise.all(children.map((child) => walk(child)));
  return nested.flat();
}

function fileOf(entry: FileSystemFileEntry): Promise<File> {
  return new Promise((resolve, reject) => entry.file(resolve, reject));
}

function readBatch(reader: FileSystemDirectoryReader): Promise<FileSystemEntry[]> {
  return new Promise((resolve, reject) => reader.readEntries(resolve, reject));
}

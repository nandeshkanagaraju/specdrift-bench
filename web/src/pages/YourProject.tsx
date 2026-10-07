/**
 * Check a project the visitor brings themselves.
 *
 * Paste, drop a folder, or drop a zip. A second check of an edited copy shows
 * which rules flipped, and each verdict can be opened onto the code it cited.
 */
import { AnimatePresence, motion } from "framer-motion";
import {
  AlertTriangle,
  CheckCircle2,
  Download,
  FolderUp,
  HelpCircle,
  Loader2,
  Play,
  Plus,
  Trash2,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState, type InputHTMLAttributes } from "react";
import { CodeBlock } from "../components/ui/CodeBlock";
import { ConfidenceBar, VerdictPill } from "../components/ui/VerdictPill";
import { Caption, Card, ErrorState } from "../components/ui/primitives";
import { api, runCheck, uploadArchive, uploadProject } from "../lib/api";
import { identifyFolder, readDrop } from "../lib/drop";
import { cn } from "../lib/format";
import type { CheckSummary, UploadRecord, Verdict, VerdictValue } from "../lib/types";
import { citedExcerpt, downloadText, flippedRules, previewRules, reportMarkdown } from "../lib/yours";

const SPEC_PLACEHOLDER = `# My service

## Limits

- **R01** A request MUST be rejected once the caller has made 10 calls.
- **R02** Rejection MUST raise \`RateLimited\`.
`;

const CODE_PLACEHOLDER = `LIMIT = 10

class RateLimited(Exception):
    pass

def allow(calls: int) -> None:
    if calls >= LIMIT:
        raise RateLimited()
`;

const STORAGE_KEY = "specdrift.yours.v1";

interface DraftFile {
  key: number;
  path: string;
  source: string;
}

interface SavedDraft {
  name: string;
  spec: string;
  files: DraftFile[];
  upload: UploadRecord | null;
  verdicts: Verdict[];
  summary: CheckSummary | null;
  prior: Verdict[];
  readToken: string | null;
}

let fileKey = 1;

function readSaved(): SavedDraft | null {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as SavedDraft;
  } catch {
    return null;
  }
}

function nextKey(): number {
  fileKey += 1;
  return fileKey;
}

export function YourProjectPage() {
  const saved = useState(() => {
    const data = readSaved();
    if (data?.files?.length) fileKey = Math.max(fileKey, ...data.files.map((file) => file.key));
    return data;
  })[0];
  const [mode, setMode] = useState<"paste" | "zip">("paste");
  const [name, setName] = useState(saved?.name ?? "my-project");
  const [spec, setSpec] = useState(saved?.spec ?? "");
  const [files, setFiles] = useState<DraftFile[]>(
    saved?.files?.length ? saved.files : [{ key: fileKey, path: "service.py", source: "" }],
  );
  const [archive, setArchive] = useState<File | null>(null);
  const [dragging, setDragging] = useState(false);
  const [dropNote, setDropNote] = useState<string | null>(null);

  const [preparing, setPreparing] = useState(false);
  const [prepareError, setPrepareError] = useState<string | null>(null);
  const [upload, setUpload] = useState<UploadRecord | null>(saved?.upload ?? null);
  const [readToken, setReadToken] = useState<string | null>(saved?.readToken ?? null);

  const [verdicts, setVerdicts] = useState<Verdict[]>(saved?.verdicts ?? []);
  const [summary, setSummary] = useState<CheckSummary | null>(saved?.summary ?? null);
  const [prior, setPrior] = useState<Verdict[]>(saved?.prior ?? []);
  const [running, setRunning] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const [filter, setFilter] = useState<"all" | VerdictValue>("all");
  const [openRule, setOpenRule] = useState<string | null>(null);
  const abort = useRef<AbortController | null>(null);
  const dragDepth = useRef(0);
  const folderInput = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const payload: SavedDraft = { name, spec, files, upload, verdicts, summary, prior, readToken };
    const text = JSON.stringify(payload);
    if (text.length < 500_000) sessionStorage.setItem(STORAGE_KEY, text);
  }, [name, spec, files, upload, verdicts, summary, prior, readToken]);

  const draftToken =
    mode === "paste"
      ? JSON.stringify({ name, spec, files: files.map((file) => [file.path, file.source]) })
      : archive
        ? `zip:${archive.name}:${archive.size}:${archive.lastModified}`
        : "";
  const stale = Boolean(upload && readToken && draftToken !== readToken);

  const preview = useMemo(() => previewRules(spec), [spec]);
  const flips = useMemo(() => flippedRules(prior, verdicts), [prior, verdicts]);
  const visible = verdicts.filter((verdict) => filter === "all" || verdict.verdict === filter);

  const applyFiles = (incoming: { path: string; source: string }[], nextSpec: string | null) => {
    setMode("paste");
    setArchive(null);
    if (nextSpec !== null) setSpec(nextSpec);
    if (incoming.length === 0) return;
    setFiles(
      incoming.map((file) => ({
        key: nextKey(),
        path: file.path.replace(/^[^/]+\/(?=src\/)/, "").replace(/^src\//, ""),
        source: file.source,
      })),
    );
  };

  const runPayload = async (
    projectName: string,
    specText: string,
    sources: { path: string; source: string }[],
  ) => {
    setFailure(null);
    setPrepareError(null);
    setMode("paste");
    setName(projectName);
    setSpec(specText);
    setFiles(sources.map((file) => ({ key: nextKey(), path: file.path, source: file.source })));
    setArchive(null);
    setPreparing(true);
    let record: UploadRecord;
    try {
      record = await uploadProject({
        name: projectName,
        spec: specText,
        files: sources.map((file) => ({ path: file.path, source: file.source })),
      });
    } catch (error) {
      setPrepareError(error instanceof Error ? error.message : String(error));
      setPreparing(false);
      return;
    }
    setPreparing(false);
    setUpload(record);
    setReadToken(
      JSON.stringify({
        name: projectName,
        spec: specText,
        files: sources.map((file) => [file.path, file.source]),
      }),
    );
    if (verdicts.length > 0) setPrior(verdicts);
    abort.current?.abort();
    abort.current = new AbortController();
    setVerdicts([]);
    setSummary(null);
    setOpenRule(null);
    setFilter("all");
    setRunning(true);
    try {
      await runCheck(
        { upload_id: record.id },
        {
          onVerdict: (verdict) => setVerdicts((rows) => [...rows, verdict]),
          onSummary: setSummary,
          onError: setFailure,
        },
        abort.current.signal,
      );
    } catch (error) {
      if (!abort.current.signal.aborted) {
        setFailure(error instanceof Error ? error.message : String(error));
      }
    } finally {
      setRunning(false);
    }
  };

  const onFolder = async (list: File[]) => {
    setPrepareError(null);
    setDropNote(null);
    try {
      const found = await identifyFolder(list);
      setDropNote(
        `Using ${found.specPath} and ${found.files.length} Python ${found.files.length === 1 ? "file" : "files"}.`,
      );
      await runPayload(found.name, found.spec, found.files);
    } catch (error) {
      setPrepareError(error instanceof Error ? error.message : String(error));
    }
  };

  const onDrop = async (event: React.DragEvent) => {
    event.preventDefault();
    setDragging(false);
    setPrepareError(null);
    try {
      const dropped = await readDrop(event.dataTransfer);
      if (!dropped) {
        setDropNote("Nothing in that drop was a spec.md, a Python file, or a zip.");
        return;
      }
      if (dropped.kind === "zip") {
        setMode("zip");
        setArchive(dropped.file);
        setName(dropped.file.name.replace(/\.zip$/i, "") || name);
        setDropNote(dropped.file.name);
        return;
      }
      if (!dropped.spec || dropped.files.length === 0) {
        applyFiles(dropped.files, dropped.spec);
        setPrepareError(
          dropped.spec
            ? "No Python files found in that folder."
            : "No specification found. Add spec.md, or a markdown file with lines like - **R01** …",
        );
        return;
      }
      const sources = dropped.files.map((file) => ({
        path: file.path.replace(/^[^/]+\/(?=src\/)/, "").replace(/^src\//, ""),
        source: file.source,
      }));
      const folder = dropped.files[0]?.path.split("/")[0];
      setDropNote(
        `Using the specification and ${sources.length} Python ${sources.length === 1 ? "file" : "files"}.`,
      );
      await runPayload(folder && dropped.files[0].path.includes("/") ? folder : name, dropped.spec, sources);
    } catch (error) {
      setPrepareError(error instanceof Error ? error.message : String(error));
    }
  };

  const loadExample = async () => {
    setPrepareError(null);
    setPreparing(true);
    try {
      const [projects, code] = await Promise.all([api.projects(), api.projectCode("library")]);
      const library = projects.find((project) => project.name === "library");
      if (!library) throw new Error("The library example is not available.");
      setMode("paste");
      setName("library");
      setSpec(library.spec);
      setFiles(
        code.map((file) => ({
          key: nextKey(),
          path: file.path.replace(/^src\//, ""),
          source: file.source,
        })),
      );
      setUpload(null);
      setReadToken(null);
      setVerdicts([]);
      setSummary(null);
      setPrior([]);
      setArchive(null);
    } catch (error) {
      setPrepareError(error instanceof Error ? error.message : String(error));
    } finally {
      setPreparing(false);
    }
  };

  const prepare = async (): Promise<UploadRecord | null> => {
    setPrepareError(null);
    setPreparing(true);
    try {
      const record =
        mode === "zip"
          ? await uploadArchive(archive!, name || archive?.name.replace(/\.zip$/i, "") || "upload")
          : await uploadProject({
              name,
              spec,
              files: files
                .filter((file) => file.path.trim() && file.source.trim())
                .map((file) => ({ path: file.path.trim(), source: file.source })),
            });
      setUpload(record);
      setReadToken(draftToken);
      return record;
    } catch (error) {
      setPrepareError(error instanceof Error ? error.message : String(error));
      return null;
    } finally {
      setPreparing(false);
    }
  };

  const start = async () => {
    setFailure(null);
    let record = upload;
    if (!record || draftToken !== readToken) {
      record = await prepare();
      if (!record) return;
    }
    if (verdicts.length > 0) setPrior(verdicts);

    abort.current?.abort();
    abort.current = new AbortController();
    setVerdicts([]);
    setSummary(null);
    setOpenRule(null);
    setFilter("all");
    setRunning(true);
    try {
      await runCheck(
        { upload_id: record.id },
        {
          onVerdict: (verdict) => setVerdicts((rows) => [...rows, verdict]),
          onSummary: setSummary,
          onError: setFailure,
        },
        abort.current.signal,
      );
    } catch (error) {
      if (!abort.current.signal.aborted) {
        setFailure(error instanceof Error ? error.message : String(error));
      }
    } finally {
      setRunning(false);
    }
  };

  const ruleText = new Map((upload?.rules ?? []).map((rule) => [rule.id, rule.text]));
  const canPrepare =
    mode === "zip"
      ? archive !== null
      : spec.trim().length > 0 && files.some((file) => file.path.trim() && file.source.trim());

  return (
    <div className="space-y-5">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-[22px] font-semibold tracking-tight">Your code</h1>
          <p className="mt-1 max-w-[68ch] text-[13px] leading-relaxed text-muted">
            Upload a folder that contains the specification and the Python. The spec file and the
            code are picked out automatically, and the report starts as soon as they are found.
          </p>
        </div>
        {summary && upload && (
          <button
            type="button"
            onClick={() =>
              downloadText(
                `${upload.name}-specdrift.md`,
                reportMarkdown(upload, verdicts, summary, flips),
              )
            }
            className="inline-flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-[12px] text-muted hover:text-text"
          >
            <Download size={14} />
            Download report
          </button>
        )}
      </header>

      <Card
        title="The project"
        action={
          <button
            type="button"
            onClick={loadExample}
            disabled={preparing}
            className="text-[12px] text-accent hover:underline disabled:opacity-50"
          >
            Fill with the library example
          </button>
        }
      >
        <div
          onDragEnter={(event) => {
            event.preventDefault();
            dragDepth.current += 1;
            setDragging(true);
          }}
          onDragOver={(event) => event.preventDefault()}
          onDragLeave={() => {
            dragDepth.current -= 1;
            if (dragDepth.current <= 0) {
              dragDepth.current = 0;
              setDragging(false);
            }
          }}
          onDrop={onDrop}
          className={cn(
            "rounded-xl border border-dashed px-3 py-3 transition-colors",
            dragging ? "border-accent bg-[var(--accent-soft)]" : "border-transparent",
          )}
        >
          <button
            type="button"
            disabled={preparing || running}
            onClick={() => folderInput.current?.click()}
            className={cn(
              "mb-3 flex w-full flex-col items-center gap-1 rounded-lg px-4 py-6 text-center",
              preparing || running
                ? "bg-surface-2 text-muted"
                : "bg-accent text-[#04231f] hover:opacity-90",
            )}
          >
            {preparing || running ? (
              <Loader2 size={18} className="animate-spin" />
            ) : (
              <FolderUp size={18} />
            )}
            <span className="text-[14px] font-medium">
              {preparing || running ? "Checking the folder…" : "Upload a folder"}
            </span>
            <span className={cn("text-[12px]", preparing || running ? "text-muted" : "text-[#04231f]/80")}>
              spec.md, or any markdown with numbered rules, plus the Python
            </span>
          </button>
          <input
            ref={folderInput}
            type="file"
            className="sr-only"
            multiple
            disabled={preparing || running}
            // The directory flag is not in React's input types. It has to be on the
            // element before the click, and the chosen files must be copied before
            // the input is cleared: clearing it empties the live file list.
            {...({ webkitdirectory: "", directory: "" } as InputHTMLAttributes<HTMLInputElement>)}
            onChange={(event) => {
              const chosen = Array.from(event.target.files ?? []);
              event.target.value = "";
              if (chosen.length) void onFolder(chosen);
            }}
          />
          <p className="mb-3 text-[12px] text-muted">
            {dragging ? "Drop the folder here." : "You can also drop the folder on this card."}
            {dropNote ? ` ${dropNote}` : ""}
          </p>

          <div className="mb-4 flex gap-2">
            {(
              [
                ["paste", "Paste spec and code"],
                ["zip", "Upload a zip"],
              ] as const
            ).map(([id, label]) => (
              <button
                key={id}
                type="button"
                onClick={() => setMode(id)}
                className={cn(
                  "rounded-full border px-3 py-1 text-[13px] transition-colors",
                  mode === id
                    ? "border-accent bg-[var(--accent-soft)] text-accent"
                    : "border-border text-muted hover:text-text",
                )}
              >
                {label}
              </button>
            ))}
          </div>

          <label className="mb-4 flex max-w-xs flex-col gap-1">
            <span className="text-[11px] uppercase tracking-[0.06em] text-muted">Name</span>
            <input
              value={name}
              onChange={(event) => setName(event.target.value)}
              className="rounded-lg border border-border bg-surface-2 px-3 py-2 text-[13px] outline-none"
            />
          </label>

          {mode === "paste" ? (
            <div className="space-y-4">
              <label className="flex flex-col gap-1">
                <span className="text-[11px] uppercase tracking-[0.06em] text-muted">
                  Specification
                </span>
                <textarea
                  value={spec}
                  onChange={(event) => setSpec(event.target.value)}
                  placeholder={SPEC_PLACEHOLDER}
                  spellCheck={false}
                  rows={8}
                  className="min-h-[160px] rounded-lg border border-border bg-surface-2 px-3 py-2 font-mono text-[12px] leading-relaxed outline-none"
                />
              </label>
              <p className="text-[12px] text-muted">
                {spec.trim()
                  ? `${preview.rules.length} numbered ${preview.rules.length === 1 ? "rule" : "rules"} recognized${
                      preview.duplicates.length > 0
                        ? `. ${preview.duplicates.join(", ")} ${preview.duplicates.length === 1 ? "is" : "are"} repeated`
                        : ""
                    }.`
                  : "Each rule is one list item: - **R01** …"}
              </p>

              <div className="space-y-3">
                {files.map((file) => (
                  <div key={file.key} className="rounded-lg border border-border">
                    <div className="flex items-center gap-2 border-b border-border px-3 py-2">
                      <input
                        value={file.path}
                        onChange={(event) =>
                          setFiles((rows) =>
                            rows.map((row) =>
                              row.key === file.key ? { ...row, path: event.target.value } : row,
                            ),
                          )
                        }
                        aria-label="File path"
                        className="min-w-0 flex-1 bg-transparent font-mono text-[12px] outline-none"
                        placeholder="service.py"
                      />
                      <button
                        type="button"
                        aria-label={`Remove ${file.path || "file"}`}
                        onClick={() =>
                          setFiles((rows) =>
                            rows.length === 1 ? rows : rows.filter((row) => row.key !== file.key),
                          )
                        }
                        className="text-muted hover:text-drift"
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                    <textarea
                      value={file.source}
                      onChange={(event) =>
                        setFiles((rows) =>
                          rows.map((row) =>
                            row.key === file.key ? { ...row, source: event.target.value } : row,
                          ),
                        )
                      }
                      placeholder={files.length === 1 ? CODE_PLACEHOLDER : ""}
                      spellCheck={false}
                      rows={7}
                      className="w-full resize-y bg-transparent px-3 py-2 font-mono text-[12px] leading-relaxed outline-none"
                    />
                  </div>
                ))}
                <button
                  type="button"
                  onClick={() =>
                    setFiles((rows) => [...rows, { key: nextKey(), path: "", source: "" }])
                  }
                  className="inline-flex items-center gap-1.5 text-[12px] text-muted hover:text-text"
                >
                  <Plus size={14} /> Add a Python file
                </button>
              </div>
            </div>
          ) : (
            <div>
              <label className="flex cursor-pointer flex-col items-center gap-2 rounded-lg border border-dashed border-border bg-surface-2 px-4 py-8 text-center">
                <span className="text-[13px] text-text">
                  {archive ? archive.name : "Choose a .zip"}
                </span>
                <span className="text-[12px] text-muted">
                  spec.md plus Python under src/, or beside the spec. Up to 1.5 MB.
                </span>
                <input
                  type="file"
                  accept=".zip,application/zip"
                  className="sr-only"
                  onChange={(event) => setArchive(event.target.files?.[0] ?? null)}
                />
              </label>
              <Caption>
                Files under tests/, .git, and virtualenvs are left out. A wrapping folder is
                unwrapped.
              </Caption>
            </div>
          )}
        </div>

        {prepareError && (
          <div className="mt-4">
            <ErrorState message={prepareError} />
          </div>
        )}

        <div className="mt-4 flex flex-wrap items-center gap-3">
          <button
            type="button"
            onClick={() => void prepare()}
            disabled={preparing || running || !canPrepare}
            className={cn(
              "inline-flex items-center gap-2 rounded-lg border border-border px-4 py-2 text-[13px] font-medium transition-colors",
              preparing || !canPrepare ? "text-muted" : "hover:text-text",
            )}
          >
            {preparing && <Loader2 size={15} className="animate-spin" />}
            {preparing ? "Reading…" : "Read rules"}
          </button>
          <button
            type="button"
            onClick={() => void start()}
            disabled={preparing || running || !canPrepare}
            className={cn(
              "inline-flex items-center gap-2 rounded-lg px-4 py-2 text-[13px] font-medium transition-colors",
              preparing || running || !canPrepare
                ? "bg-surface-2 text-muted"
                : "bg-accent text-[#04231f] hover:opacity-90",
            )}
          >
            {running ? <Loader2 size={15} className="animate-spin" /> : <Play size={15} />}
            {running ? "Checking…" : stale || !upload ? "Read and check" : "Run check"}
          </button>
          {stale && (
            <span className="text-[12px] text-uncertain">
              Edited since the last read. The next check uses what is on screen now.
            </span>
          )}
        </div>
      </Card>

      {upload && (
        <Card
          title={`${upload.name} · ${upload.rules.length} ${upload.rules.length === 1 ? "rule" : "rules"} · ${upload.files.length} ${upload.files.length === 1 ? "file" : "files"}`}
        >
          {upload.warnings.length > 0 && (
            <ul className="mb-3 space-y-1 text-[12px] text-uncertain">
              {upload.warnings.map((warning) => (
                <li key={warning}>{warning}</li>
              ))}
            </ul>
          )}
          <ul className="max-h-[200px] space-y-2 overflow-y-auto">
            {upload.rules.map((rule) => (
              <li key={rule.id} className="flex gap-2.5 text-[12.5px] leading-relaxed">
                <span className="shrink-0 font-mono text-[11px] text-accent">{rule.id}</span>
                <span className="text-muted">{rule.text}</span>
              </li>
            ))}
          </ul>
          <p className="mt-3 font-mono text-[11px] text-muted">
            {upload.files.map((file) => `${file.path} (${file.lines})`).join(" · ")}
          </p>
        </Card>
      )}

      {failure && <ErrorState message={failure} />}

      {flips.length > 0 && !running && (
        <Card title={`${flips.length} ${flips.length === 1 ? "rule" : "rules"} changed since the previous check`}>
          <ul className="space-y-2">
            {flips.map((flip) => (
              <li key={flip.ruleId} className="flex flex-wrap items-center gap-2 text-[13px]">
                <span className="w-10 font-mono text-[11px] text-accent">{flip.ruleId}</span>
                <VerdictPill verdict={flip.from} size="sm" />
                <span className="text-muted">→</span>
                <VerdictPill verdict={flip.to} size="sm" />
                <span className="min-w-0 flex-1 truncate text-[12px] text-muted">
                  {ruleText.get(flip.ruleId) ?? ""}
                </span>
              </li>
            ))}
          </ul>
        </Card>
      )}

      {(running || verdicts.length > 0) && (
        <Card
          title={`${verdicts.length} of ${summary?.rules ?? upload?.rules.length ?? "…"} rules`}
          action={
            <div className="flex gap-1">
              {(["all", "DRIFT", "UNCERTAIN", "COMPLIANT"] as const).map((value) => (
                <button
                  key={value}
                  type="button"
                  onClick={() => setFilter(value)}
                  className={cn(
                    "rounded-full px-2 py-0.5 text-[11px]",
                    filter === value ? "bg-[var(--accent-soft)] text-accent" : "text-muted hover:text-text",
                  )}
                >
                  {value === "all" ? "All" : value === "DRIFT" ? "Drift" : value === "COMPLIANT" ? "Matches" : "Unsure"}
                </button>
              ))}
            </div>
          }
        >
          <ul className="divide-y divide-border">
            <AnimatePresence initial={false}>
              {visible.map((verdict) => {
                const excerpt = upload ? citedExcerpt(upload.files, verdict) : null;
                const open = openRule === verdict.rule_id;
                return (
                  <motion.li
                    key={verdict.rule_id}
                    initial={{ opacity: 0, y: 6 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.18, ease: "easeOut" }}
                    className="py-2.5"
                  >
                    <button
                      type="button"
                      onClick={() => setOpenRule(open ? null : verdict.rule_id)}
                      className="flex w-full flex-wrap items-center gap-3 text-left"
                    >
                      <span className="w-10 shrink-0 font-mono text-[11px] text-accent">
                        {verdict.rule_id}
                      </span>
                      <VerdictPill verdict={verdict.verdict} size="sm" />
                      <div className="w-24 shrink-0">
                        <ConfidenceBar value={verdict.confidence} label={false} />
                      </div>
                      <span className="min-w-0 flex-1 truncate text-[12px] text-muted">
                        {ruleText.get(verdict.rule_id) ?? ""}
                      </span>
                    </button>
                    {open && (
                      <div className="mt-2 space-y-2 pl-[52px]">
                        {verdict.violated_clause && (
                          <p className="text-[12px] leading-relaxed text-drift">{verdict.violated_clause}</p>
                        )}
                        {(verdict.counterexample.input ||
                          verdict.counterexample.expected ||
                          verdict.counterexample.actual) && (
                          <p className="text-[12px] leading-relaxed text-muted">
                            Input {verdict.counterexample.input || "—"}. Expected{" "}
                            {verdict.counterexample.expected || "—"}. Actual{" "}
                            {verdict.counterexample.actual || "—"}.
                          </p>
                        )}
                        {verdict.downgraded && (
                          <p className="text-[12px] text-uncertain">
                            Downgraded: a drift claim needs a quoted clause and a counterexample.
                          </p>
                        )}
                        {excerpt && (
                          <div>
                            <p className="mb-1 font-mono text-[11px] text-muted">
                              {excerpt.path}:{excerpt.start}
                            </p>
                            <CodeBlock code={excerpt.code} startLine={excerpt.start} maxHeight="220px" />
                          </div>
                        )}
                        {verdict.retrieved_chunks.length > 0 && (
                          <p className="font-mono text-[11px] text-muted">
                            Retrieved {verdict.retrieved_chunks.map((id) => id.split("::")[1] ?? id).join(", ")}
                          </p>
                        )}
                      </div>
                    )}
                  </motion.li>
                );
              })}
            </AnimatePresence>
          </ul>
          {visible.length === 0 && (
            <p className="py-3 text-[12px] text-muted">Nothing in this filter.</p>
          )}
        </Card>
      )}

      {summary && <SummaryBanner summary={summary} />}
    </div>
  );
}

function SummaryBanner({ summary }: { summary: CheckSummary }) {
  const style = {
    PASS: {
      className: "border-compliant/40 bg-[rgba(52,211,153,.09)] text-compliant",
      Icon: CheckCircle2,
      title: "PASS",
    },
    DRIFT: {
      className: "border-drift/40 bg-[rgba(251,113,133,.09)] text-drift",
      Icon: AlertTriangle,
      title: "DRIFT",
    },
    NEEDS_HUMAN: {
      className: "border-uncertain/40 bg-[rgba(251,191,36,.09)] text-uncertain",
      Icon: HelpCircle,
      title: "NEEDS HUMAN",
    },
  }[summary.status];

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className={cn("flex flex-wrap items-center gap-4 rounded-xl border px-4 py-3", style.className)}
    >
      <style.Icon size={20} aria-hidden />
      <div className="min-w-0 flex-1">
        <p className="text-sm font-semibold">{style.title}</p>
        <p className="text-[12px] text-muted">
          {summary.counts.DRIFT} drift · {summary.counts.COMPLIANT} compliant ·{" "}
          {summary.counts.UNCERTAIN} uncertain, over {summary.rules} rules and {summary.chunks}{" "}
          chunks (model {summary.model}).
        </p>
      </div>
    </motion.div>
  );
}

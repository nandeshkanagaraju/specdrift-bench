/**
 * The front door, written for someone who has never seen this project.
 *
 * It reads top to bottom as one story: here are the two inputs, here is an optional
 * bug we can plant in them, press the button, watch every rule get checked live,
 * read the answer. The full dashboard is still there, one link away.
 */
import { AnimatePresence, motion } from "framer-motion";
import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  FileCode2,
  FileText,
  HelpCircle,
  Loader2,
  Moon,
  Play,
  Sun,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api, runCheck, runSweep } from "../lib/api";
import { cn, pct } from "../lib/format";
import { useTheme } from "../lib/theme";
import type {
  CaseDetail,
  CaseRow,
  CheckSummary,
  RuleDetail,
  StageEvent,
  SweepCase,
  SweepResult,
  Verdict,
  VerdictValue,
} from "../lib/types";
import { useApi } from "../lib/useApi";

/* The three words the detector answers with, said the way a person would say them. */
const PLAIN: Record<VerdictValue, { label: string; colour: string; Icon: typeof CheckCircle2 }> = {
  COMPLIANT: { label: "Code matches the rule", colour: "text-compliant", Icon: CheckCircle2 },
  DRIFT: { label: "Code broke this rule", colour: "text-drift", Icon: AlertTriangle },
  UNCERTAIN: { label: "Not sure — send to a human", colour: "text-uncertain", Icon: HelpCircle },
};

const SHORT: Record<VerdictValue, string> = {
  COMPLIANT: "Matches",
  DRIFT: "Broken",
  UNCERTAIN: "Not sure",
};

/**
 * The six steps a run actually takes, in order. Each one is a separate call in
 * specdrift/live.py and reports its own real count, so nothing here is decoration.
 */
const STEPS = [
  {
    id: "setup",
    title: "Start the checker",
    plain: "Connect the language model and load the code-search index.",
    tech: "model adapter + embedder",
  },
  {
    id: "spec",
    title: "Read the specification",
    plain: "Split spec.md into separate numbered rules, one requirement each.",
    tech: "text parsing",
  },
  {
    id: "chunk",
    title: "Read the code",
    plain: "Cut every Python file into its functions, methods and classes.",
    tech: "AST parsing",
  },
  {
    id: "rank",
    title: "Stage 1 · Find the right code",
    plain: "Score every piece of code against every rule and keep the closest few.",
    tech: "embedding search, cosine similarity",
  },
  {
    id: "verify",
    title: "Stage 2 · Judge each rule",
    plain: "Ask the model, one rule at a time, whether that code still obeys it.",
    tech: "semantic check",
  },
  {
    id: "gate",
    title: "Check the proof",
    plain: "A drift claim without a quoted clause and a worked example is not accepted.",
    tech: "evidence gate",
  },
] as const;

type StageState = "waiting" | "running" | "done";

export function DemoPage() {
  const { theme, toggle } = useTheme();

  const projects = useApi((signal) => api.projects(signal));
  const allCases = useApi((signal) => api.cases({ label: "drift", page_size: "1000" }, signal));
  const summaryData = useApi((signal) => api.summary(signal));

  const [project, setProject] = useState("library");
  const [caseId, setCaseId] = useState("");

  const code = useApi((signal) => api.projectCode(project, signal), [project]);
  const injected = useApi<CaseDetail | null>(
    (signal) => (caseId ? api.caseDetail(caseId, signal) : Promise.resolve(null)),
    [caseId],
  );

  const [stages, setStages] = useState<Record<string, { state: StageState; detail?: string }>>({});
  const [verdicts, setVerdicts] = useState<Verdict[]>([]);
  const [details, setDetails] = useState<Map<string, RuleDetail>>(new Map());
  const [checking, setChecking] = useState<string | null>(null);
  const [result, setResult] = useState<CheckSummary | null>(null);
  const [running, setRunning] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const abort = useRef<AbortController | null>(null);
  const liveRef = useRef<HTMLDivElement | null>(null);

  const [sweepCases, setSweepCases] = useState<SweepCase[]>([]);
  const [sweepResults, setSweepResults] = useState<Map<string, SweepResult>>(new Map());
  const [sweeping, setSweeping] = useState(false);
  const sweepAbort = useRef<AbortController | null>(null);

  const startSweep = async () => {
    sweepAbort.current?.abort();
    sweepAbort.current = new AbortController();
    setSweepCases([]);
    setSweepResults(new Map());
    setSweeping(true);
    try {
      await runSweep(
        {
          onCase: (row) => setSweepCases((rows) => [...rows, row]),
          onResult: (row) =>
            setSweepResults((rows) => new Map(rows).set(row.category, row)),
          onSummary: () => {},
          onError: setFailure,
        },
        sweepAbort.current.signal,
      );
    } catch (error) {
      if (!sweepAbort.current.signal.aborted) {
        setFailure(error instanceof Error ? error.message : String(error));
      }
    } finally {
      setSweeping(false);
    }
  };

  const current = projects.data?.find((p) => p.name === project);
  const rules = current?.rules ?? [];

  /* Grouped by drift category so the picker reads as a taxonomy, not a flat list. */
  const projectCases = useMemo(
    () =>
      (allCases.data?.items ?? [])
        .filter((row) => row.project === project)
        .sort((a, b) => a.id.localeCompare(b.id)),
    [allCases.data, project],
  );
  const casesByCategory = useMemo(() => {
    const groups = new Map<string, { name: string; rows: CaseRow[] }>();
    for (const row of projectCases) {
      const group = groups.get(row.category) ?? { name: row.category_name, rows: [] };
      group.rows.push(row);
      groups.set(row.category, group);
    }
    return [...groups.entries()].sort(([a], [b]) => a.localeCompare(b));
  }, [projectCases]);
  const chosenCase: CaseRow | undefined = projectCases.find((row) => row.id === caseId);

  useEffect(
    () => () => {
      abort.current?.abort();
      sweepAbort.current?.abort();
    },
    [],
  );

  const start = async () => {
    abort.current?.abort();
    abort.current = new AbortController();

    setStages({});
    setVerdicts([]);
    setDetails(new Map());
    setChecking(null);
    setResult(null);
    setFailure(null);
    setRunning(true);
    liveRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });

    try {
      await runCheck(
        { project, case_id: caseId || null },
        {
          onStage: (stage: StageEvent) =>
            setStages((s) => ({ ...s, [stage.stage]: { state: stage.state, detail: stage.detail } })),
          onRuleStart: (rule) => setChecking(rule.rule_id),
          onRuleDetail: (detail) =>
            setDetails((rows) => new Map(rows).set(detail.rule_id, detail)),
          onVerdict: (verdict) => {
            setVerdicts((rows) => [...rows, verdict]);
            setChecking(null);
          },
          onSummary: setResult,
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
      setChecking(null);
    }
  };

  const byRule = new Map(verdicts.map((v) => [v.rule_id, v]));

  return (
    <div className="mx-auto w-full max-w-[980px] px-4 py-8 md:px-6">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="font-mono text-[20px] font-semibold tracking-tight">
            Spec<span className="text-accent">Guard</span>
          </h1>
          <p className="mt-1 max-w-[62ch] text-[14px] leading-relaxed text-muted">
            A project is written from a <strong className="text-text">specification</strong> — a list
            of rules in plain English. Over time the <strong className="text-text">code</strong>{" "}
            quietly stops obeying some of them, and the tests keep passing anyway. SpecGuard reads
            both and says, rule by rule, which ones the code still keeps.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={toggle}
            aria-label="Toggle theme"
            className="rounded-lg border border-border p-2 text-muted hover:text-text"
          >
            {theme === "dark" ? <Moon size={15} /> : <Sun size={15} />}
          </button>
        </div>
      </header>

      <Flow />

      {/* ---------------------------------------------------------- step 1 */}
      <Step n={1} title="The two inputs" hint="Everything SpecGuard is given, before it runs.">
        <div className="mb-4 flex flex-wrap items-center gap-2">
          <span className="text-[13px] text-muted">Project:</span>
          {(projects.data ?? []).map((p) => (
            <button
              key={p.name}
              type="button"
              onClick={() => {
                setProject(p.name);
                setCaseId("");
                setVerdicts([]);
                setResult(null);
                setStages({});
              }}
              className={cn(
                "rounded-full border px-3 py-1 text-[13px] transition-colors",
                p.name === project
                  ? "border-accent bg-[var(--accent-soft)] text-accent"
                  : "border-border text-muted hover:text-text",
              )}
            >
              {p.name}
            </button>
          ))}
        </div>
        <p className="mb-4 text-[13px] text-muted">
          These three are built in so the walkthrough has something to show.{" "}
          <Link to="/yours" className="text-accent hover:underline">
            Check a specification and code you provide
          </Link>
          .
        </p>

        <div className="grid gap-4 md:grid-cols-2">
          <InputPanel
            Icon={FileText}
            kind="Input 1"
            title="The specification"
            subtitle={`${rules.length} numbered rules, written by hand in spec.md`}
          >
            <ol className="max-h-[300px] space-y-2 overflow-y-auto pr-1">
              {rules.map((rule) => (
                <li key={rule.id} className="flex gap-2.5 text-[12.5px] leading-relaxed">
                  <span className="shrink-0 font-mono text-[11px] text-accent">{rule.id}</span>
                  <span className="text-muted">{rule.text}</span>
                </li>
              ))}
              {projects.loading && <li className="text-[13px] text-muted">loading…</li>}
            </ol>
          </InputPanel>

          <InputPanel
            Icon={FileCode2}
            kind="Input 2"
            title="The code"
            subtitle={`${code.data?.length ?? 0} Python files, ${
              code.data?.reduce((n, f) => n + f.lines, 0) ?? 0
            } lines — a working app`}
          >
            <div className="max-h-[300px] space-y-2 overflow-y-auto pr-1">
              {(code.data ?? []).map((file) => (
                <FileRow key={file.path} path={file.path} lines={file.lines} source={file.source} />
              ))}
              {code.loading && <p className="text-[13px] text-muted">loading…</p>}
            </div>
          </InputPanel>
        </div>
      </Step>

      {/* ---------------------------------------------------------- step 2 */}
      <Step
        n={2}
        title="Optional: plant a bug first"
        hint="So you can watch SpecGuard find something you already know is there."
      >
        <div className="flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-1">
            <span className="text-[11px] uppercase tracking-[0.06em] text-muted">
              Change one line of the code
            </span>
            <select
              value={caseId}
              onChange={(event) => setCaseId(event.target.value)}
              className="min-w-[320px] rounded-lg border border-border bg-surface-2 px-3 py-2 text-[13px] outline-none"
            >
              <option value="">Nothing — check the code exactly as written</option>
              {casesByCategory.map(([category, group]) => (
                <optgroup key={category} label={`${category} · ${group.name}`}>
                  {group.rows.map((row) => (
                    <option key={row.id} value={row.id}>
                      {row.note || row.id}
                    </option>
                  ))}
                </optgroup>
              ))}
            </select>
          </label>
        </div>

        {!caseId && (
          <p className="mt-3 max-w-[72ch] text-[13px] leading-relaxed text-muted">
            With nothing planted, the code is the original working project. SpecGuard should come
            back clean — that is the check that it does not cry wolf. Plant one and it will not
            always be caught: the detector is near-perfect on a changed constant (D2) or a weakened
            condition (D4), and unreliable on wrong ordering (D5) and error handling (D6). Measuring
            that gap is the whole point of the benchmark, so the misses are shown, not hidden.
          </p>
        )}

        {chosenCase && (
          <InjectedBug detail={injected.data} row={chosenCase} loading={injected.loading} />
        )}
      </Step>

      {/* ---------------------------------------------------------- step 3 */}
      <Step n={3} title="Run the check" hint="Every rule is checked against the code, one at a time.">
        <button
          type="button"
          onClick={start}
          disabled={running}
          className={cn(
            "inline-flex items-center gap-2 rounded-lg px-5 py-2.5 text-[14px] font-medium transition-colors",
            running ? "bg-surface-2 text-muted" : "bg-accent text-[#04231f] hover:opacity-90",
          )}
        >
          {running ? <Loader2 size={16} className="animate-spin" /> : <Play size={16} />}
          {running ? "Checking…" : `Check all ${rules.length} rules`}
        </button>

        {failure && (
          <div className="mt-3 rounded-lg border border-drift/40 bg-[rgba(251,113,133,.08)] px-3 py-2 text-[13px] text-drift">
            {failure}
            <span className="mt-1 block text-muted">
              Is the API running? Start it with <code className="font-mono">specdrift serve</code>.
            </span>
          </div>
        )}
      </Step>

      {/* ------------------------------------------------- the live section */}
      <div ref={liveRef} className="scroll-mt-4">
        {(running || verdicts.length > 0) && (
          <LiveRun
            rules={rules}
            byRule={byRule}
            details={details}
            checking={checking}
            stages={stages}
            running={running}
            result={result}
            targets={chosenCase?.target_rules ?? []}
          />
        )}

        {result && <Answer result={result} chosenCase={chosenCase} verdicts={verdicts} />}
      </div>

      {/* ------------------------------------------- all nine categories */}
      <Step
        n={4}
        title="Now try all 9 kinds of drift"
        hint="One representative bug from each category, checked one after another."
      >
        <CategorySweep
          cases={sweepCases}
          results={sweepResults}
          running={sweeping}
          onStart={startSweep}
        />
      </Step>

      {/* -------------------------------------------------- the numbers */}
      {summaryData.data && (
        <Step
          n={5}
          title="And the research question behind the demo"
          hint="One run of each detector over every labelled case in the benchmark."
        >
          <div className="grid gap-3 sm:grid-cols-3">
            <Tile
              value={String(summaryData.data.valid_cases)}
              label="labelled test cases"
              sub={`${summaryData.data.drift_cases} with a planted bug, ${summaryData.data.negative_cases} deliberately clean`}
            />
            <Tile
              value={pct(summaryData.data.escapes_rate)}
              label="of planted bugs still pass every test"
              sub="which is exactly why a test suite is not enough"
            />
            <Tile
              value={String(summaryData.data.projects.length)}
              label="working host projects"
              sub={summaryData.data.projects.join(", ")}
            />
          </div>

          <div className="mt-4 overflow-x-auto">
            <table className="w-full min-w-[520px] text-[13px]">
              <thead>
                <tr className="border-b border-border text-left text-[11px] uppercase tracking-[0.06em] text-muted">
                  <th className="py-2 font-medium">Method</th>
                  <th className="py-2 text-right font-medium">Bugs found</th>
                  <th className="py-2 text-right font-medium">False alarms</th>
                  <th className="py-2 text-right font-medium">F1</th>
                </tr>
              </thead>
              <tbody>
                {summaryData.data.detectors
                  .filter((d) => d.scored)
                  .map((d) => (
                    <tr key={d.name} className="border-b border-border/60">
                      <td className="py-2 pr-3">
                        <span className="font-medium">{d.name}</span>
                        <span className="ml-2 text-muted">{DETECTOR_BLURB[d.name] ?? ""}</span>
                      </td>
                      <td className="tabular py-2 text-right">{pct(d.recall)}</td>
                      <td className="tabular py-2 text-right">{pct(d.false_alarm_rate)}</td>
                      <td className="tabular py-2 text-right">{d.f1.toFixed(2)}</td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
          <p className="mt-3 max-w-[70ch] text-[13px] leading-relaxed text-muted">
            The two model-based methods fail in opposite directions. Showing the model a short,
            relevant excerpt (SpecGuard) finds far more real bugs than one prompt over the whole
            codebase — and raises far more false alarms. Measuring both sides is the point of the
            benchmark.
          </p>
        </Step>
      )}

      <footer className="mt-10 flex flex-wrap items-center justify-between gap-3 border-t border-border pt-5 text-[12.5px] text-muted">
        <span>
          SpecDrift-Bench · every number here is read from a completed run, never computed live.
        </span>
        <Link to="/dashboard" className="text-accent hover:underline">
          Full dashboard — all cases, per-category scores, retrieval →
        </Link>
      </footer>
    </div>
  );
}

const DETECTOR_BLURB: Record<string, string> = {
  specguard: "find the relevant code first, then ask the model",
  wholefile: "one prompt, the whole codebase at once",
  keyword: "no model at all — just word matching",
};

/* ------------------------------------------------------------------ pieces */

function Flow() {
  const boxes = [
    { title: "Specification", body: "Rules in English" },
    { title: "SpecGuard", body: "Find the code, then judge it" },
    { title: "One answer per rule", body: "Kept · Broken · Not sure" },
  ];
  return (
    <div className="mt-6 grid gap-2 sm:grid-cols-[1fr_auto_1fr_auto_1fr] sm:items-center">
      {boxes.map((box, i) => (
        <div key={box.title} className="contents">
          <div className="hairline rounded-xl bg-surface px-4 py-3 text-center">
            <p className="text-[13px] font-semibold">{box.title}</p>
            <p className="mt-0.5 text-[12px] text-muted">{box.body}</p>
          </div>
          {i < boxes.length - 1 && (
            <span aria-hidden className="hidden text-center text-muted sm:block">
              →
            </span>
          )}
        </div>
      ))}
    </div>
  );
}

function Step({
  n,
  title,
  hint,
  children,
}: {
  n: number;
  title: string;
  hint: string;
  children: React.ReactNode;
}) {
  return (
    <section className="mt-8">
      <div className="mb-3 flex items-baseline gap-3">
        <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-[var(--accent-soft)] text-[12px] font-semibold text-accent">
          {n}
        </span>
        <div>
          <h2 className="text-[16px] font-semibold tracking-tight">{title}</h2>
          <p className="text-[13px] text-muted">{hint}</p>
        </div>
      </div>
      <div className="hairline rounded-xl bg-surface p-4">{children}</div>
    </section>
  );
}

function InputPanel({
  Icon,
  kind,
  title,
  subtitle,
  children,
}: {
  Icon: typeof FileText;
  kind: string;
  title: string;
  subtitle: string;
  children: React.ReactNode;
}) {
  return (
    <div className="hairline rounded-xl bg-surface-2/60 p-3.5">
      <div className="mb-2.5 flex items-start gap-2.5">
        <Icon size={17} className="mt-0.5 shrink-0 text-accent" aria-hidden />
        <div>
          <p className="text-[11px] uppercase tracking-[0.06em] text-accent">{kind}</p>
          <p className="text-[14px] font-semibold">{title}</p>
          <p className="text-[12px] text-muted">{subtitle}</p>
        </div>
      </div>
      {children}
    </div>
  );
}

function FileRow({ path, lines, source }: { path: string; lines: number; source: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="rounded-lg border border-border bg-surface">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-2 px-2.5 py-1.5 text-left"
        aria-expanded={open}
      >
        <ChevronDown
          size={13}
          className={cn("shrink-0 text-muted transition-transform", open && "rotate-180")}
          aria-hidden
        />
        <span className="min-w-0 flex-1 truncate font-mono text-[12px]">{path}</span>
        <span className="tabular shrink-0 text-[11px] text-muted">{lines} lines</span>
      </button>
      {open && (
        <pre className="max-h-[240px] overflow-auto border-t border-border px-3 py-2 font-mono text-[11px] leading-relaxed text-muted">
          {source}
        </pre>
      )}
    </div>
  );
}

function InjectedBug({
  detail,
  row,
  loading,
}: {
  detail: CaseDetail | null;
  row: CaseRow;
  loading: boolean;
}) {
  /**
   * Every case is one find/replace that matched exactly once, so trimming the
   * shared head and tail leaves precisely the lines that changed.
   */
  const diff = useMemo(() => {
    if (!detail || !detail.before_source) return null;
    const before = detail.before_source.split("\n");
    const after = detail.after_source.split("\n");

    let head = 0;
    while (head < before.length && head < after.length && before[head] === after[head]) head += 1;

    let tail = 0;
    while (
      tail < before.length - head &&
      tail < after.length - head &&
      before[before.length - 1 - tail] === after[after.length - 1 - tail]
    ) {
      tail += 1;
    }

    const context = 2;
    return {
      removed: before.slice(head, before.length - tail),
      added: after.slice(head, after.length - tail),
      above: after.slice(Math.max(0, head - context), head),
      below: after.slice(after.length - tail, after.length - tail + context),
      line: head + 1,
    };
  }, [detail]);

  return (
    <div className="mt-4 rounded-xl border border-uncertain/40 bg-[rgba(251,191,36,.06)] p-3.5">
      <p className="text-[13px]">
        <strong>What changed:</strong> {row.note || "one line in the source"}
      </p>
      <p className="mt-1 text-[12.5px] text-muted">
        Type of change: <strong className="text-text">{row.category_name}</strong> · it should break{" "}
        {row.target_rules.length ? (
          <strong className="font-mono text-text">{row.target_rules.join(", ")}</strong>
        ) : (
          <strong className="text-text">no named rule — it adds behaviour nobody asked for</strong>
        )}{" "}
        · the project's own tests still{" "}
        <strong className={row.escapes_tests ? "text-drift" : "text-text"}>
          {row.escapes_tests ? "pass, so they miss it entirely" : "catch it"}
        </strong>
        .
      </p>
      <p className="mt-1 font-mono text-[11.5px] text-muted">
        {row.file}
        {diff && <span> · line {diff.line}</span>}
      </p>

      {loading && <p className="mt-2 text-[13px] text-muted">loading the diff…</p>}

      {diff && (
        <pre className="mt-2 overflow-x-auto rounded-lg border border-border bg-surface px-3 py-2 font-mono text-[11.5px] leading-relaxed">
          {diff.above.map((line, i) => (
            <div key={`a${i}`} className="text-muted">
              {"  "}
              {line}
            </div>
          ))}
          {diff.removed.map((line, i) => (
            <div key={`r${i}`} className="text-drift">
              -{line}
            </div>
          ))}
          {diff.added.map((line, i) => (
            <div key={`n${i}`} className="text-compliant">
              +{line}
            </div>
          ))}
          {diff.below.map((line, i) => (
            <div key={`b${i}`} className="text-muted">
              {"  "}
              {line}
            </div>
          ))}
        </pre>
      )}
    </div>
  );
}

function LiveRun({
  rules,
  byRule,
  details,
  checking,
  stages,
  running,
  result,
  targets,
}: {
  rules: { id: string; text: string }[];
  byRule: Map<string, Verdict>;
  details: Map<string, RuleDetail>;
  checking: string | null;
  stages: Record<string, { state: StageState; detail?: string }>;
  running: boolean;
  result: CheckSummary | null;
  targets: string[];
}) {
  const counts = { COMPLIANT: 0, DRIFT: 0, UNCERTAIN: 0 } as Record<VerdictValue, number>;
  let cacheHits = 0;
  let downgraded = 0;
  for (const verdict of byRule.values()) {
    counts[verdict.verdict] += 1;
    if (verdict.cache_hit) cacheHits += 1;
    if (verdict.downgraded) downgraded += 1;
  }

  return (
    <section className="mt-8">
      <h2 className="text-[16px] font-semibold tracking-tight">
        The run &mdash; {STEPS.length} steps, {rules.length} rules
      </h2>
      <p className="mb-3 max-w-[74ch] text-[13px] text-muted">
        Every step below is a separate piece of the checker, and they run in this order.
        Step 5 is the one that repeats: it checks the rules one at a time, and each of those
        is listed inside it.
      </p>

      <div className="grid gap-4 md:grid-cols-[236px_minmax(0,1fr)] md:items-start">
        <StatusPanel
          done={byRule.size}
          total={rules.length}
          counts={counts}
          running={running}
          result={result}
          cacheHits={cacheHits}
          downgraded={downgraded}
        />
        <PipelineTimeline
          stages={stages}
          rules={rules}
          byRule={byRule}
          details={details}
          checking={checking}
          targets={targets}
        />
      </div>
    </section>
  );
}

/** The sidebar: the same few numbers, in the same place, for the whole run. */
function StatusPanel({
  done,
  total,
  counts,
  running,
  result,
  cacheHits,
  downgraded,
}: {
  done: number;
  total: number;
  counts: Record<VerdictValue, number>;
  running: boolean;
  result: CheckSummary | null;
  cacheHits: number;
  downgraded: number;
}) {
  const headline = running
    ? { label: "Running…", colour: "text-accent" }
    : result
      ? {
          PASS: { label: "Clean", colour: "text-compliant" },
          DRIFT: { label: "Drift found", colour: "text-drift" },
          NEEDS_HUMAN: { label: "Needs a human", colour: "text-uncertain" },
        }[result.status]
      : { label: "Ready", colour: "text-muted" };

  const pct = total ? Math.round((done / total) * 100) : 0;

  return (
    <aside className="hairline rounded-xl bg-surface p-3.5 md:sticky md:top-4">
      <p className="text-[11px] uppercase tracking-[0.06em] text-muted">Status</p>
      <p className={cn("mt-0.5 text-[16px] font-semibold", headline.colour)}>{headline.label}</p>

      <div className="mt-3">
        <div className="flex items-baseline justify-between text-[12px]">
          <span className="text-muted">Rules checked</span>
          <span className="tabular font-mono">
            {done} / {total}
          </span>
        </div>
        <div
          className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-surface-2"
          role="progressbar"
          aria-valuenow={pct}
          aria-valuemin={0}
          aria-valuemax={100}
        >
          <div
            className="h-full rounded-full bg-accent transition-[width] duration-300"
            style={{ width: `${pct}%` }}
          />
        </div>
      </div>

      <ul className="mt-3.5 space-y-1.5">
        {(["DRIFT", "COMPLIANT", "UNCERTAIN"] as VerdictValue[]).map((value) => {
          const plain = PLAIN[value];
          return (
            <li key={value} className="flex items-center gap-2 text-[12.5px]">
              <plain.Icon size={14} className={cn("shrink-0", plain.colour)} aria-hidden />
              <span className="min-w-0 flex-1 truncate text-muted">{SHORT[value]}</span>
              <span className="tabular font-mono">{counts[value]}</span>
            </li>
          );
        })}
      </ul>

      <dl className="mt-4 space-y-1 border-t border-border pt-2.5 text-[11.5px]">
        <Fact label="Answers reused" value={`${cacheHits} cached`} />
        <Fact label="Claims downgraded" value={String(downgraded)} />
        {result && <Fact label="Code inspected" value={`${result.chunks} chunks`} />}
        {result && <Fact label="Model" value={result.model} mono />}
      </dl>
    </aside>
  );
}

function Fact({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex items-baseline justify-between gap-2">
      <dt className="text-muted">{label}</dt>
      <dd className={cn("truncate text-right", mono && "font-mono text-[11px]")}>{value}</dd>
    </div>
  );
}

/** The timeline: the six pipeline steps, with the per-rule checks inside step 5. */
function PipelineTimeline({
  stages,
  rules,
  byRule,
  details,
  checking,
  targets,
}: {
  stages: Record<string, { state: StageState; detail?: string }>;
  rules: { id: string; text: string }[];
  byRule: Map<string, Verdict>;
  details: Map<string, RuleDetail>;
  checking: string | null;
  targets: string[];
}) {
  return (
    <ol className="hairline rounded-xl bg-surface py-1.5 pl-4 pr-3">
      {STEPS.map((step, i) => {
        const state = stages[step.id]?.state ?? "waiting";
        const detail =
          step.id === "verify" && state === "running"
            ? `${byRule.size} of ${rules.length} checked`
            : stages[step.id]?.detail;
        const last = i === STEPS.length - 1;

        return (
          <li key={step.id} className="flex gap-3">
            <div className="flex flex-col items-center pt-3">
              <StepNode state={state} index={i + 1} />
              {!last && (
                <span
                  aria-hidden
                  className={cn(
                    "mt-1 w-px flex-1 transition-colors",
                    state === "done" ? "bg-accent/40" : "bg-border",
                  )}
                />
              )}
            </div>

            <div className={cn("min-w-0 flex-1 py-3", !last && "border-b border-border/50")}>
              <p
                className={cn(
                  "text-[13.5px] font-medium transition-colors",
                  state === "waiting" ? "text-muted" : "text-text",
                )}
              >
                {step.title}
                <span className="ml-2 font-mono text-[10.5px] font-normal text-muted">
                  {step.tech}
                </span>
              </p>
              <p className="text-[12.5px] text-muted">{step.plain}</p>
              {detail && <p className="mt-0.5 text-[12px] text-accent">{detail}</p>}

              {step.id === "verify" && (byRule.size > 0 || state === "running") && (
                <ol className="mt-2.5 rounded-lg border border-border bg-surface-2/40">
                  {rules.map((rule, j) => (
                    <ChecklistRow
                      key={rule.id}
                      index={j + 1}
                      rule={rule}
                      verdict={byRule.get(rule.id)}
                      detail={details.get(rule.id)}
                      busy={checking === rule.id}
                      isTarget={targets.includes(rule.id)}
                      last={j === rules.length - 1}
                    />
                  ))}
                </ol>
              )}
            </div>
          </li>
        );
      })}
    </ol>
  );
}

function StepNode({ state, index }: { state: StageState; index: number }) {
  return (
    <span
      className={cn(
        "flex h-[24px] w-[24px] shrink-0 items-center justify-center rounded-full border transition-colors",
        state === "done"
          ? "border-transparent bg-[var(--accent-soft)]"
          : state === "running"
            ? "border-accent bg-[var(--accent-soft)]"
            : "border-border",
      )}
    >
      {state === "done" ? (
        <CheckCircle2 size={15} className="text-accent" aria-label="done" />
      ) : state === "running" ? (
        <Loader2 size={13} className="animate-spin text-accent" aria-label="running" />
      ) : (
        <span className="tabular font-mono text-[10px] text-muted">{index}</span>
      )}
    </span>
  );
}

function ChecklistRow({
  index,
  rule,
  verdict,
  detail,
  busy,
  isTarget,
  last,
}: {
  index: number;
  rule: { id: string; text: string };
  verdict: Verdict | undefined;
  detail: RuleDetail | undefined;
  busy: boolean;
  isTarget: boolean;
  last: boolean;
}) {
  const [open, setOpen] = useState(false);
  const plain = verdict ? PLAIN[verdict.verdict] : null;
  const expandable = verdict?.verdict === "DRIFT";

  return (
    <li className="flex gap-3">
      {/* the line itself: a node per check, joined top to bottom */}
      <div className="flex flex-col items-center pt-2.5">
        <span
          className={cn(
            "flex h-[22px] w-[22px] shrink-0 items-center justify-center rounded-full border transition-colors",
            plain
              ? "border-transparent bg-surface-2"
              : busy
                ? "border-accent bg-[var(--accent-soft)]"
                : "border-border",
          )}
        >
          {plain ? (
            <motion.span initial={{ scale: 0.6, opacity: 0 }} animate={{ scale: 1, opacity: 1 }}>
              <plain.Icon size={14} className={plain.colour} aria-hidden />
            </motion.span>
          ) : busy ? (
            <Loader2 size={12} className="animate-spin text-accent" aria-hidden />
          ) : (
            <span className="tabular font-mono text-[10px] text-muted">{index}</span>
          )}
        </span>
        {!last && (
          <span
            aria-hidden
            className={cn(
              "mt-1 w-px flex-1 transition-colors",
              plain ? "bg-accent/40" : "bg-border",
            )}
          />
        )}
      </div>

      <div className={cn("min-w-0 flex-1", !last && "border-b border-border/50")}>
        <button
          type="button"
          onClick={() => expandable && setOpen((v) => !v)}
          className={cn(
            "flex w-full items-center gap-3 rounded-lg py-2.5 pr-2 text-left transition-colors",
            !expandable && "cursor-default",
            isTarget && "bg-[var(--accent-soft)] px-2",
            busy && !isTarget && "bg-surface-2/60 px-2",
          )}
          aria-expanded={expandable ? open : undefined}
        >
          <span className="min-w-0 flex-1">
            <span className="block text-[13px]">
              <span className="mr-2 font-mono text-[11px] text-accent">{rule.id}</span>
              {rule.text}
            </span>
            <span className={cn("block text-[12px]", plain ? plain.colour : "text-muted")}>
              {plain ? plain.label : busy ? "checking…" : "waiting"}
              {isTarget && <span className="text-accent"> · the bug was aimed here</span>}
            </span>
            {detail && (
              <span className="block text-[11px] text-muted">
                shown {detail.retrieved} piece{detail.retrieved === 1 ? "" : "s"} of code
                {detail.constant_context > 0 &&
                  ` + ${detail.constant_context} for the constants they use`}
                {verdict?.cache_hit && " · answer reused from cache"}
              </span>
            )}
          </span>

          {expandable && (
            <ChevronDown
              size={14}
              className={cn("shrink-0 text-muted transition-transform", open && "rotate-180")}
              aria-hidden
            />
          )}
        </button>

        <AnimatePresence initial={false}>
          {open && verdict && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: "auto", opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              className="overflow-hidden"
            >
              <div className="space-y-2 pb-3 pr-2 text-[12.5px]">
                <p className="text-muted">
                  A drift answer is only accepted with proof. SpecGuard makes the model quote the
                  clause and give a concrete example; without both, step 6 downgrades it to{" "}
                  <em>not sure</em>.
                </p>
                {verdict.violated_clause && (
                  <p>
                    <span className="text-muted">The clause it says was broken: </span>
                    <span className="italic">“{verdict.violated_clause}”</span>
                  </p>
                )}
                {verdict.counterexample.input && (
                  <p className="font-mono text-[11.5px]">
                    <span className="font-sans text-muted">Example: </span>
                    {verdict.counterexample.input}
                    <span className="font-sans text-muted"> → spec says </span>
                    {verdict.counterexample.expected}
                    <span className="font-sans text-muted">, code does </span>
                    <span className="text-drift">{verdict.counterexample.actual}</span>
                  </p>
                )}
                {verdict.evidence.file && (
                  <p className="font-mono text-[11.5px] text-muted">
                    {verdict.evidence.file}:{verdict.evidence.start_line}–
                    {verdict.evidence.end_line}
                  </p>
                )}
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </li>
  );
}

function Answer({
  result,
  chosenCase,
  verdicts,
}: {
  result: CheckSummary;
  chosenCase: CaseRow | undefined;
  verdicts: Verdict[];
}) {
  const style = {
    PASS: {
      className: "border-compliant/40 bg-[rgba(52,211,153,.09)] text-compliant",
      Icon: CheckCircle2,
      title: "Clean — the code keeps every rule",
    },
    DRIFT: {
      className: "border-drift/40 bg-[rgba(251,113,133,.09)] text-drift",
      Icon: AlertTriangle,
      title: "Drift found — the code broke at least one rule",
    },
    NEEDS_HUMAN: {
      className: "border-uncertain/40 bg-[rgba(251,191,36,.09)] text-uncertain",
      Icon: HelpCircle,
      title: "Needs a human — nothing proven either way",
    },
  }[result.status];

  const flagged = new Set(verdicts.filter((v) => v.verdict === "DRIFT").map((v) => v.rule_id));
  const targets = chosenCase?.target_rules ?? [];
  const caught = targets.length > 0 && targets.some((rule) => flagged.has(rule));

  return (
    <motion.section
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className="mt-6"
    >
      <h2 className="mb-3 text-[16px] font-semibold tracking-tight">The answer</h2>
      <div className={cn("rounded-xl border px-4 py-3.5", style.className)}>
        <div className="flex items-start gap-3">
          <style.Icon size={20} className="mt-0.5 shrink-0" aria-hidden />
          <div className="min-w-0">
            <p className="text-[14px] font-semibold">{style.title}</p>
            <p className="mt-0.5 text-[12.5px] text-muted">
              Out of {result.rules} rules: {result.counts.DRIFT} broken, {result.counts.COMPLIANT}{" "}
              kept, {result.counts.UNCERTAIN} unclear. Judged against {result.chunks} pieces of code
              by <span className="font-mono">{result.model}</span>.
            </p>
          </div>
        </div>

        {chosenCase && targets.length > 0 && (
          <p className="mt-3 border-t border-current/20 pt-3 text-[13px] text-text">
            {caught ? (
              <>
                <strong className="text-compliant">Caught it.</strong> The planted bug was aimed at{" "}
                <span className="font-mono">{targets.join(", ")}</span>, and that is what SpecGuard
                flagged.
              </>
            ) : (
              <>
                <strong className="text-drift">Missed it.</strong> The planted bug was aimed at{" "}
                <span className="font-mono">{targets.join(", ")}</span>, which SpecGuard did not
                flag. Misses like this are what the benchmark exists to count.
              </>
            )}
          </p>
        )}
      </div>
    </motion.section>
  );
}

/**
 * The nine drift categories, each one planted and checked in turn.
 *
 * This measures recall only: whether the bug aimed at a rule made that rule turn.
 * False alarms are a separate question, asked of the control cases, and they are in
 * the table below. Misses are shown exactly as they happen -- the spread between
 * categories is the result the project exists to report.
 */
function CategorySweep({
  cases,
  results,
  running,
  onStart,
}: {
  cases: SweepCase[];
  results: Map<string, SweepResult>;
  running: boolean;
  onStart: () => void;
}) {
  const caught = [...results.values()].filter((r) => r.caught).length;
  const started = cases.length > 0;

  return (
    <div>
      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={onStart}
          disabled={running}
          className={cn(
            "inline-flex items-center gap-2 rounded-lg px-4 py-2 text-[13.5px] font-medium transition-colors",
            running ? "bg-surface-2 text-muted" : "bg-accent text-[#04231f] hover:opacity-90",
          )}
        >
          {running ? <Loader2 size={15} className="animate-spin" /> : <Play size={15} />}
          {running ? "Running…" : "Run all 9 categories"}
        </button>

        {started && (
          <p className="text-[13px]">
            <span className="tabular font-mono">
              {caught} of {results.size}
            </span>{" "}
            <span className="text-muted">caught so far</span>
          </p>
        )}
      </div>

      {!started && !running && (
        <p className="mt-3 max-w-[74ch] text-[13px] leading-relaxed text-muted">
          The same detector runs every time — there is no special handling per category.
          What changes is the kind of bug planted. Running all nine shows where that one
          method is reliable and where it is not, which is the finding the project reports.
        </p>
      )}

      {started && (
        <ol className="mt-4">
          {cases.map((row, i) => (
            <SweepRow
              key={row.category}
              row={row}
              result={results.get(row.category)}
              last={i === cases.length - 1}
            />
          ))}
        </ol>
      )}

      {started && !running && (
        <p className="mt-3 max-w-[74ch] text-[12.5px] leading-relaxed text-muted">
          This is recall, one case per category. It does not ask about false alarms — that
          question is put to the unchanged and refactored control cases, and the answer is in
          the table below.
        </p>
      )}
    </div>
  );
}

function SweepRow({
  row,
  result,
  last,
}: {
  row: SweepCase;
  result: SweepResult | undefined;
  last: boolean;
}) {
  const state = result ? (result.caught ? "caught" : "missed") : "checking";

  return (
    <li className="flex gap-3">
      <div className="flex flex-col items-center pt-3">
        <span
          className={cn(
            "flex h-[24px] w-[24px] shrink-0 items-center justify-center rounded-full border",
            state === "caught"
              ? "border-transparent bg-[rgba(52,211,153,.14)]"
              : state === "missed"
                ? "border-transparent bg-[rgba(251,113,133,.14)]"
                : "border-accent bg-[var(--accent-soft)]",
          )}
        >
          {state === "caught" ? (
            <CheckCircle2 size={15} className="text-compliant" aria-label="caught" />
          ) : state === "missed" ? (
            <AlertTriangle size={14} className="text-drift" aria-label="missed" />
          ) : (
            <Loader2 size={13} className="animate-spin text-accent" aria-hidden />
          )}
        </span>
        {!last && (
          <span
            aria-hidden
            className={cn("mt-1 w-px flex-1", result ? "bg-accent/40" : "bg-border")}
          />
        )}
      </div>

      <div className={cn("min-w-0 flex-1 py-3", !last && "border-b border-border/50")}>
        <div className="flex flex-wrap items-baseline gap-x-2.5 gap-y-1">
          <span className="font-mono text-[11px] text-accent">{row.category}</span>
          <span className="text-[13.5px] font-medium">{row.category_name}</span>
          <span
            className={cn(
              "ml-auto text-[12px] font-semibold",
              state === "caught"
                ? "text-compliant"
                : state === "missed"
                  ? "text-drift"
                  : "text-muted",
            )}
          >
            {state === "caught" ? "CAUGHT" : state === "missed" ? "MISSED" : "checking…"}
          </span>
        </div>

        <p className="mt-0.5 text-[12.5px] text-muted">{row.note}</p>

        {(row.before || row.after) && (
          <pre className="mt-1.5 overflow-x-auto rounded-lg border border-border bg-surface-2/50 px-2.5 py-1.5 font-mono text-[11px] leading-relaxed">
            {row.before && <div className="text-drift">- {row.before}</div>}
            {row.after && <div className="text-compliant">+ {row.after}</div>}
          </pre>
        )}

        <p className="mt-1 text-[11.5px] text-muted">
          {row.target_rules.length ? (
            <>
              aimed at <span className="font-mono text-text">{row.target_rules.join(", ")}</span>
            </>
          ) : (
            <>no rule authorises this, so every rule was checked</>
          )}
          {result?.caught && result.flagged_rules.length > 0 && (
            <>
              {" · flagged "}
              <span className="font-mono text-compliant">{result.flagged_rules.join(", ")}</span>
            </>
          )}
          {row.escapes_tests && <span className="text-drift"> · the tests still pass</span>}
        </p>
      </div>
    </li>
  );
}

function Tile({ value, label, sub }: { value: string; label: string; sub: string }) {
  return (
    <div className="hairline rounded-xl bg-surface-2/60 px-3.5 py-3">
      <p className="tabular text-[24px] font-semibold leading-none">{value}</p>
      <p className="mt-1.5 text-[13px]">{label}</p>
      <p className="mt-0.5 text-[12px] leading-relaxed text-muted">{sub}</p>
    </div>
  );
}

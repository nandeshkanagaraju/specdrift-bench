import { AnimatePresence, motion } from "framer-motion";
import { AlertTriangle, CheckCircle2, HelpCircle, Loader2, Play } from "lucide-react";
import { useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { ConfidenceBar, VerdictPill } from "../components/ui/VerdictPill";
import { Caption, Card, ErrorState, Skeleton } from "../components/ui/primitives";
import { api, runCheck } from "../lib/api";
import { cn } from "../lib/format";
import type { CheckSummary, Verdict } from "../lib/types";
import { useApi } from "../lib/useApi";

export function LiveCheckPage() {
  const projects = useApi((signal) => api.projects(signal));
  const cases = useApi((signal) => api.cases({ label: "drift", page_size: "1000" }, signal));

  const [project, setProject] = useState("library");
  const [caseId, setCaseId] = useState("");
  const [verdicts, setVerdicts] = useState<Verdict[]>([]);
  const [summary, setSummary] = useState<CheckSummary | null>(null);
  const [running, setRunning] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const abort = useRef<AbortController | null>(null);

  const ruleText = useMemo(() => {
    const found = projects.data?.find((p) => p.name === project);
    return new Map((found?.rules ?? []).map((rule) => [rule.id, rule.text]));
  }, [projects.data, project]);

  const projectCases = useMemo(
    () => (cases.data?.items ?? []).filter((row) => row.project === project),
    [cases.data, project],
  );

  const start = async () => {
    abort.current?.abort();
    abort.current = new AbortController();

    setVerdicts([]);
    setSummary(null);
    setFailure(null);
    setRunning(true);

    try {
      await runCheck(
        { project, case_id: caseId || null },
        {
          onVerdict: (verdict) => setVerdicts((rows) => [...rows, verdict]),
          onSummary: (payload) => setSummary(payload),
          onError: (message) => setFailure(message),
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

  if (projects.error) return <ErrorState message={projects.error} />;

  return (
    <div className="space-y-5">
      <header>
        <h1 className="text-[22px] font-semibold tracking-tight">Live Check</h1>
        <p className="mt-1 text-[13px] text-muted">
          Run the two-stage detector against a project right now, rule by rule.
        </p>
      </header>

      <Card>
        <div className="flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-1">
            <span className="text-[11px] uppercase tracking-[0.06em] text-muted">Project</span>
            <select
              value={project}
              onChange={(event) => {
                setProject(event.target.value);
                setCaseId("");
              }}
              className="min-w-[160px] rounded-lg border border-border bg-surface-2 px-3 py-2 text-[13px] outline-none"
            >
              {projects.loading && <option>loading…</option>}
              {(projects.data ?? []).map((p) => (
                <option key={p.name} value={p.name}>
                  {p.name} ({p.rule_count} rules)
                </option>
              ))}
            </select>
          </label>

          <label className="flex flex-col gap-1">
            <span className="text-[11px] uppercase tracking-[0.06em] text-muted">Inject a drift case</span>
            <select
              value={caseId}
              onChange={(event) => setCaseId(event.target.value)}
              className="min-w-[260px] rounded-lg border border-border bg-surface-2 px-3 py-2 text-[13px] outline-none"
            >
              <option value="">none — check the project as written</option>
              {projectCases.map((row) => (
                <option key={row.id} value={row.id}>
                  {row.id} · {row.category_name}
                </option>
              ))}
            </select>
          </label>

          <button
            type="button"
            onClick={start}
            disabled={running}
            className={cn(
              "inline-flex items-center gap-2 rounded-lg px-4 py-2 text-[13px] font-medium transition-colors",
              running ? "bg-surface-2 text-muted" : "bg-accent text-[#04231f] hover:opacity-90",
            )}
          >
            {running ? <Loader2 size={15} className="animate-spin" /> : <Play size={15} />}
            {running ? "Checking…" : "Run check"}
          </button>
        </div>
        <Caption>
          With no case selected this checks the pristine project, which should come back clean. Pick a
          case to inject its drift first and watch which rule turns.
        </Caption>
      </Card>

      {failure && <ErrorState message={failure} />}

      {(running || verdicts.length > 0) && (
        <Card title={`${verdicts.length} of ${summary?.rules ?? "…"} rules`}>
          <ul className="divide-y divide-border">
            <AnimatePresence initial={false}>
              {verdicts.map((verdict, index) => (
                <motion.li
                  key={verdict.rule_id}
                  initial={{ opacity: 0, y: 6 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.18, delay: Math.min(index * 0.01, 0.2), ease: "easeOut" }}
                  className="flex flex-wrap items-center gap-3 py-2.5"
                >
                  <span className="w-10 shrink-0 font-mono text-[11px] text-accent">{verdict.rule_id}</span>
                  <VerdictPill verdict={verdict.verdict} size="sm" />
                  <div className="w-24 shrink-0">
                    <ConfidenceBar value={verdict.confidence} label={false} />
                  </div>
                  <span className="min-w-0 flex-1 truncate text-[12px] text-muted">
                    {ruleText.get(verdict.rule_id) ?? ""}
                  </span>
                  <span className="shrink-0 font-mono text-[11px] text-muted">
                    {verdict.retrieved_chunks[0]?.split("::")[1] ?? ""}
                  </span>
                </motion.li>
              ))}
            </AnimatePresence>
          </ul>

          {running && verdicts.length === 0 && (
            <div className="space-y-2 py-2">
              {Array.from({ length: 5 }).map((_, i) => (
                <Skeleton key={i} className="h-8 rounded-md" />
              ))}
            </div>
          )}
        </Card>
      )}

      {summary && <SummaryBanner summary={summary} caseId={caseId} />}
    </div>
  );
}

function SummaryBanner({ summary, caseId }: { summary: CheckSummary; caseId: string }) {
  const style = {
    PASS: { className: "border-compliant/40 bg-[rgba(52,211,153,.09)] text-compliant", Icon: CheckCircle2, title: "PASS" },
    DRIFT: { className: "border-drift/40 bg-[rgba(251,113,133,.09)] text-drift", Icon: AlertTriangle, title: "DRIFT" },
    NEEDS_HUMAN: { className: "border-uncertain/40 bg-[rgba(251,191,36,.09)] text-uncertain", Icon: HelpCircle, title: "NEEDS HUMAN" },
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
          {summary.counts.UNCERTAIN} uncertain, over {summary.rules} rules and {summary.chunks} chunks
          (model {summary.model}).
        </p>
      </div>
      {caseId && (
        <Link to={`/cases/${caseId}`} className="shrink-0 text-[12px] underline hover:opacity-80">
          Open the case detail
        </Link>
      )}
    </motion.div>
  );
}

import { ArrowLeft, Crosshair } from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { DiffView } from "../components/ui/DiffView";
import { ConfidenceBar, VerdictPill } from "../components/ui/VerdictPill";
import { Badge, Caption, Card, ErrorState, Skeleton } from "../components/ui/primitives";
import { api } from "../lib/api";
import { cn } from "../lib/format";
import type { CaseDetail, Verdict } from "../lib/types";
import { useApi } from "../lib/useApi";

export function CaseDetailPage() {
  const { caseId = "" } = useParams();
  const { data, error, loading } = useApi((signal) => api.caseDetail(caseId, signal), [caseId]);
  const [scrollTo, setScrollTo] = useState<number | null>(null);

  if (error) return <ErrorState message={error} />;
  if (loading || !data) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-72" />
        <div className="grid gap-4 lg:grid-cols-[260px_minmax(0,1fr)_320px]">
          <Skeleton className="h-64 rounded-xl" />
          <Skeleton className="h-64 rounded-xl" />
          <Skeleton className="h-64 rounded-xl" />
        </div>
      </div>
    );
  }

  const { case: row } = data;
  const detectors = Object.keys(data.verdicts);

  return (
    <div className="space-y-5">
      <header className="flex flex-wrap items-center gap-3">
        <Link to="/explorer" className="inline-flex items-center gap-1 text-[12px] text-muted hover:text-text">
          <ArrowLeft size={13} /> Explorer
        </Link>
        <h1 className="font-mono text-[18px] font-semibold tracking-tight">{row.id}</h1>
        <Badge tone={row.label === "drift" ? "drift" : "neutral"}>
          {row.category} · {row.category_name}
        </Badge>
        {row.escapes_tests && <Badge tone="uncertain">passes its own tests</Badge>}
      </header>

      {row.note && <p className="text-[13px] text-muted">{row.note}</p>}

      <div className="grid gap-4 lg:grid-cols-[260px_minmax(0,1fr)_330px]">
        {/* Left: the rules this case is about. */}
        <div className="space-y-4">
          <Card title="Rules">
            <ul className="space-y-3">
              {data.rules.map((rule) => (
                <li key={rule.id}>
                  <p className="font-mono text-[11px] text-accent">{rule.id}</p>
                  <p className="mt-0.5 text-[13px] leading-relaxed">{rule.text}</p>
                  {rule.section && <p className="mt-1 text-[11px] text-muted">{rule.section}</p>}
                </li>
              ))}
            </ul>
          </Card>

          <Card title="Case">
            <dl className="space-y-2 text-[12px]">
              <Row label="Project" value={row.project} />
              <Row label="File" value={row.file || "—"} mono />
              <Row label="Gold chunk" value={row.gold_symbol || "—"} mono />
              <Row label="Label" value={row.label} />
              <Row label="Status" value={row.status} />
            </dl>
          </Card>
        </div>

        {/* Centre: what actually changed. */}
        <Card title="The change">
          <DiffView
            before={data.before_source}
            after={data.after_source}
            changedLines={data.changed_lines}
            scrollTo={scrollTo}
          />
          <Caption>
            {data.changed_lines.length
              ? `${data.changed_lines.length} line(s) changed in ${row.file}.`
              : "No patch: this is the project exactly as written."}
          </Caption>
        </Card>

        {/* Right: what each detector concluded, and what it was shown. */}
        <div className="space-y-4">
          {detectors.map((name) => (
            <DetectorCard
              key={name}
              name={name}
              verdicts={data.verdicts[name]}
              detail={data}
              onJumpTo={setScrollTo}
            />
          ))}
        </div>
      </div>

      <Card title="Stage 1 retrieval">
        {Object.entries(data.retrieved).length === 0 ? (
          <p className="text-[13px] text-muted">This case names no target rule, so there is nothing to rank against.</p>
        ) : (
          Object.entries(data.retrieved).map(([ruleId, hits]) => (
            <div key={ruleId} className="mb-4 last:mb-0">
              <p className="mb-2 font-mono text-[11px] text-accent">{ruleId}</p>
              <ul className="space-y-1.5">
                {hits.map((hit) => (
                  <li key={hit.chunk_id} className="flex items-center gap-3">
                    <span className={cn("w-[300px] shrink-0 truncate font-mono text-[11px]", hit.is_gold ? "text-compliant" : "text-muted")}>
                      {hit.qualname}
                      <span className="ml-1 opacity-60">{hit.file}</span>
                    </span>
                    <div className="h-1.5 w-full max-w-[220px] overflow-hidden rounded-full bg-surface-2">
                      <div
                        className={cn("h-full rounded-full", hit.is_gold ? "bg-compliant" : "bg-accent/60")}
                        style={{ width: `${Math.max(2, hit.score * 100)}%` }}
                      />
                    </div>
                    <span className="tabular w-10 font-mono text-[11px] text-muted">{hit.score.toFixed(2)}</span>
                    {hit.is_gold && (
                      <span className="inline-flex items-center gap-1 text-[11px] text-compliant">
                        <Crosshair size={11} /> gold
                      </span>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          ))
        )}
        <Caption>
          The gold chunk is the one the injection actually touched. If it never appears here, a miss
          is a retrieval failure; if it does and the verdict was still COMPLIANT, it is a reasoning failure.
        </Caption>
      </Card>
    </div>
  );
}

function Row({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex justify-between gap-3">
      <dt className="shrink-0 text-muted">{label}</dt>
      <dd className={cn("truncate text-right", mono && "font-mono text-[11px]")}>{value}</dd>
    </div>
  );
}

function DetectorCard({
  name,
  verdicts,
  detail,
  onJumpTo,
}: {
  name: string;
  verdicts: Verdict[];
  detail: CaseDetail;
  onJumpTo: (line: number) => void;
}) {
  const targets = detail.case.target_rules;
  // An empty array is truthy, so this cannot be written as a `||` fallback.
  const relevant = verdicts.filter((v) => v.verdict === "DRIFT" || targets.includes(v.rule_id));
  const interesting = (relevant.length ? relevant : verdicts.slice(0, 1)).slice(0, 4);
  const outcome = detail.outcomes[name];

  return (
    <Card
      title={<span className="font-mono">{name}</span>}
      action={
        outcome && (
          <Badge tone={outcome.outcome === "TP" ? "compliant" : outcome.outcome === "FP" ? "drift" : "neutral"}>
            {outcome.outcome}
            {outcome.attribution && outcome.attribution !== "n/a" ? ` · ${outcome.attribution}` : ""}
          </Badge>
        )
      }
    >
      {interesting.length === 0 && <p className="text-[13px] text-muted">Nothing flagged on this case.</p>}

      <div className="space-y-4">
        {interesting.map((verdict) => (
          <div key={verdict.rule_id} className="space-y-2">
            <div className="flex items-center justify-between gap-2">
              <span className="font-mono text-[11px] text-muted">{verdict.rule_id}</span>
              <VerdictPill verdict={verdict.verdict} size="sm" />
            </div>
            <ConfidenceBar value={verdict.confidence} />

            {verdict.violated_clause && (
              <blockquote className="border-l-2 border-accent bg-surface-2 px-2.5 py-1.5 text-[12px] leading-snug">
                {verdict.violated_clause}
              </blockquote>
            )}

            {verdict.counterexample.input && (
              <dl className="grid grid-cols-[62px_1fr] gap-x-2 gap-y-0.5 text-[12px]">
                <dt className="text-muted">Input</dt>
                <dd>{verdict.counterexample.input}</dd>
                <dt className="text-muted">Expected</dt>
                <dd>{verdict.counterexample.expected}</dd>
                <dt className="text-muted">Actual</dt>
                <dd>{verdict.counterexample.actual}</dd>
              </dl>
            )}

            {verdict.evidence.file && verdict.evidence.start_line > 0 && (
              <button
                type="button"
                onClick={() => onJumpTo(verdict.evidence.start_line)}
                className="font-mono text-[11px] text-accent hover:underline"
              >
                {verdict.evidence.file}:{verdict.evidence.start_line}-{verdict.evidence.end_line}
              </button>
            )}
          </div>
        ))}
      </div>
    </Card>
  );
}

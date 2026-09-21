import { useNavigate } from "react-router-dom";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { ChartFrame, ChartTooltipStyle, useChartColors } from "../components/Chart";
import { Caption, Card, ErrorState, Skeleton } from "../components/ui/primitives";
import { api } from "../lib/api";
import { CATEGORY_ORDER, cn, fixed, metricTone, pct } from "../lib/format";
import { useApi } from "../lib/useApi";

export function ComparePage() {
  const { data, error, loading } = useApi((signal) => api.metrics(undefined, signal));
  const colors = useChartColors();
  const tooltip = ChartTooltipStyle();
  const navigate = useNavigate();

  if (error) return <ErrorState message={error} />;
  if (loading || !data) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-[320px] rounded-xl" />
        <Skeleton className="h-[280px] rounded-xl" />
      </div>
    );
  }

  const detectors = data.detectors;
  const retrieval = data.retrieval;

  const recallAtK = retrieval
    ? [1, 3, 5].map((k) => ({
        k: `@${k}`,
        overall: Number(((retrieval.overall[`recall@${k}`] ?? 0) * 100).toFixed(1)),
      }))
    : [];

  const attributionRows = detectors.map((d) => ({
    name: d.detector,
    Retrieval: d.attribution.retrieval ?? 0,
    Reasoning: d.attribution.reasoning ?? 0,
    "No retrieval stage": d.attribution["n/a"] ?? 0,
  }));

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-[22px] font-semibold tracking-tight">Detector Comparison</h1>
        <p className="mt-1 text-[13px] text-muted">
          Every detector was scored by the same code over the same {detectors[0]?.cases_scored ?? 0} cases.
        </p>
      </header>

      <Card title="Headline">
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-[13px]">
            <thead>
              <tr className="text-[11px] uppercase tracking-[0.05em] text-muted">
                <th className="border-b border-border px-3 py-2 text-left">Detector</th>
                <th className="border-b border-border px-3 py-2 text-left">Model</th>
                {["Precision", "Recall", "F1", "False alarms", "Uncertain"].map((h) => (
                  <th key={h} className="border-b border-border px-3 py-2 text-right">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {detectors.map((d) => (
                <tr key={d.detector} className="border-b border-border/70">
                  <td className="px-3 py-2 font-mono">{d.detector}</td>
                  <td className="px-3 py-2 text-[12px] text-muted">{d.model}</td>
                  <td className="tabular px-3 py-2 text-right font-mono">{fixed(d.overall.precision)}</td>
                  <td className="tabular px-3 py-2 text-right font-mono">{fixed(d.overall.recall)}</td>
                  <td className="tabular px-3 py-2 text-right font-mono">{fixed(d.overall.f1)}</td>
                  <td className="tabular px-3 py-2 text-right font-mono">{fixed(d.overall.false_alarm_rate)}</td>
                  <td className="tabular px-3 py-2 text-right font-mono">{fixed(d.overall.uncertain_rate)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <Card title="Category × detector">
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-[13px]">
            <thead>
              <tr className="text-[11px] uppercase tracking-[0.05em] text-muted">
                <th className="border-b border-border px-3 py-2 text-left">Cat</th>
                <th className="border-b border-border px-3 py-2 text-left">Category</th>
                <th className="border-b border-border px-3 py-2 text-right">n</th>
                {detectors.map((d) => (
                  <th key={d.detector} className="border-b border-border px-3 py-2 text-right font-mono">
                    {d.detector}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {CATEGORY_ORDER.map((cat) => {
                const sample = detectors[0]?.per_category.find((c) => c.category === cat);
                if (!sample) return null;

                return (
                  <tr key={cat} className="border-b border-border/70">
                    <td className="px-3 py-2 font-mono">{cat}</td>
                    <td className="px-3 py-2">
                      {sample.name}
                      {!sample.is_drift && <span className="ml-2 text-[11px] text-muted">control</span>}
                    </td>
                    <td className="tabular px-3 py-2 text-right text-muted">{sample.n}</td>
                    {detectors.map((d) => {
                      const cell = d.per_category.find((c) => c.category === cat);
                      if (!cell) return <td key={d.detector} className="px-3 py-2 text-right text-muted">—</td>;
                      const tone = metricTone(cell.value, cell.is_drift);
                      return (
                        <td key={d.detector} className="px-1.5 py-1.5 text-right">
                          <button
                            type="button"
                            onClick={() => navigate(`/explorer?category=${cat}`)}
                            title={`${cell.metric} · click to open these ${cell.n} cases`}
                            className={cn(
                              "tabular w-full rounded-md px-2 py-1.5 text-right font-mono text-[12px] transition-colors",
                              tone === "good" && "bg-[rgba(52,211,153,.16)] text-compliant",
                              tone === "mid" && "bg-[rgba(251,191,36,.14)] text-uncertain",
                              tone === "bad" && "bg-[rgba(251,113,133,.14)] text-drift",
                              "hover:ring-1 hover:ring-accent",
                            )}
                          >
                            {pct(cell.value)}
                          </button>
                        </td>
                      );
                    })}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <Caption>
          D rows are recall, so green is good. N rows are the false-alarm rate on controls that must
          never be flagged, so for those green means quiet. Click a cell to open its cases.
        </Caption>
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Stage 1 · Recall@k">
          {retrieval ? (
            <>
              <ChartFrame height={230}>
                <ResponsiveContainer>
                  <LineChart data={recallAtK} margin={{ top: 8, right: 10, left: -20, bottom: 0 }}>
                    <CartesianGrid stroke={colors.grid} vertical={false} />
                    <XAxis dataKey="k" stroke={colors.axis} fontSize={11} tickLine={false} axisLine={false} />
                    <YAxis stroke={colors.axis} fontSize={11} tickLine={false} axisLine={false} unit="%" domain={[0, 100]} />
                    <Tooltip {...tooltip} formatter={(v: number) => `${v}%`} />
                    <Line type="monotone" dataKey="overall" stroke={colors.series[0]} strokeWidth={2} dot={{ r: 3 }} />
                  </LineChart>
                </ResponsiveContainer>
              </ChartFrame>
              <Caption>
                How often the chunk the injection touched was in the top k that Stage 1 returned, over{" "}
                {retrieval.n_rule_queries} rule queries. Embedder: {retrieval.embedder}.
              </Caption>
            </>
          ) : (
            <p className="text-[13px] text-muted">
              Run <code className="font-mono">specdrift retrieval-eval</code> to populate this chart.
            </p>
          )}
        </Card>

        <Card title="Why drift was missed">
          <ChartFrame height={230}>
            <ResponsiveContainer>
              <BarChart data={attributionRows} margin={{ top: 8, right: 10, left: -22, bottom: 0 }}>
                <CartesianGrid stroke={colors.grid} vertical={false} />
                <XAxis dataKey="name" stroke={colors.axis} fontSize={11} tickLine={false} axisLine={false} />
                <YAxis stroke={colors.axis} fontSize={11} tickLine={false} axisLine={false} allowDecimals={false} />
                <Tooltip {...tooltip} />
                <Legend wrapperStyle={{ fontSize: 11 }} />
                <Bar dataKey="Retrieval" stackId="a" fill={colors.series[1]} maxBarSize={48} />
                <Bar dataKey="Reasoning" stackId="a" fill={colors.series[2]} maxBarSize={48} />
                <Bar dataKey="No retrieval stage" stackId="a" fill={colors.grid} maxBarSize={48} radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </ChartFrame>
          <Caption>
            A miss counts as retrieval when the injected chunk was never shown, and as reasoning when
            it was shown and read wrongly. That split says which half of the pipeline to fix.
          </Caption>
        </Card>
      </div>
    </div>
  );
}

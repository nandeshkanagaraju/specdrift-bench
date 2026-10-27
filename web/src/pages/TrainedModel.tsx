import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { ChartFrame, ChartTooltipStyle, useChartColors } from "../components/Chart";
import { Badge, Caption, Card, ErrorState, Skeleton } from "../components/ui/primitives";
import { StatCard } from "../components/ui/StatCard";
import { api } from "../lib/api";
import { fixed, pct } from "../lib/format";
import { useApi } from "../lib/useApi";
import type { Stat } from "../lib/types";

const interval = (s: Stat) => `${fixed(s.mean)} [${fixed(s.ci95[0])}, ${fixed(s.ci95[1])}]`;

const th = "px-3 py-2 text-left text-[11px] font-medium uppercase tracking-[0.06em] text-muted";
const td = "tabular px-3 py-2 text-[13px]";

export function TrainedModelPage() {
  const { data, error, loading } = useApi((signal) => api.trainedModel(signal));
  const colors = useChartColors();
  const tooltip = ChartTooltipStyle();

  if (error) return <ErrorState message={error} />;
  if (loading || !data) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-9 w-2/3 max-w-lg" />
        <Skeleton className="h-[92px] rounded-xl" />
        <Skeleton className="h-[300px] rounded-xl" />
      </div>
    );
  }

  const tuned = data.benchmark_arms.find((a) => a.name.endsWith("sft-r0"));
  const zeroShot = data.benchmark_arms.find((a) => a.name.startsWith("gpt-4o-mini"));
  const chartRows = data.benchmark_arms.map((a) => ({
    name: a.label.replace("Qwen2.5-Coder-1.5B", "Qwen 1.5B"),
    Recall: Number((a.recall.mean * 100).toFixed(1)),
    "False alarms": Number((a.false_alarm_rate.mean * 100).toFixed(1)),
  }));
  const vsGpt = data.paired_tuned_minus_baseline["vs_gpt-4o-mini"];

  return (
    <div className="space-y-8">
      <header>
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone="drift">{data.verdict.headline}</Badge>
          <span className="text-[12px] text-muted">Recorded {data.generated}</span>
        </div>
        <h1 className="mt-2 max-w-2xl text-[26px] font-semibold leading-tight tracking-tight">{data.title}</h1>
        <p className="mt-1.5 max-w-2xl text-[13px] text-muted">{data.verdict.text}</p>
      </header>

      {tuned && zeroShot && (
        <div className="flex flex-wrap gap-3">
          <StatCard
            hero
            label="Tuned false-alarm rate"
            value={tuned.false_alarm_rate.mean}
            format={(v) => pct(v)}
            hint={`gpt-4o-mini: ${pct(zeroShot.false_alarm_rate.mean)}`}
          />
          <StatCard
            label="Tuned recall"
            value={tuned.recall.mean}
            format={(v) => pct(v)}
            hint={`gpt-4o-mini: ${pct(zeroShot.recall.mean)}`}
          />
          <StatCard
            label="Training examples"
            value={data.training.examples}
            format={(v) => Math.round(v).toLocaleString("en-US")}
            hint={`${data.training.libraries} libraries + function-level data`}
          />
          <StatCard label="Optimiser steps" value={data.training.steps} hint={data.training.method} />
        </div>
      )}

      <Card title="Recall against false alarms, 86 frozen cases">
        <ChartFrame>
          <ResponsiveContainer>
            <BarChart data={chartRows} margin={{ top: 4, right: 8, left: -18, bottom: 0 }}>
              <CartesianGrid stroke={colors.grid} vertical={false} />
              <XAxis dataKey="name" stroke={colors.axis} fontSize={11} tickLine={false} axisLine={false} />
              <YAxis stroke={colors.axis} fontSize={11} tickLine={false} axisLine={false} unit="%" domain={[0, 100]} />
              <Tooltip {...tooltip} formatter={(v: number) => `${v}%`} />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Bar dataKey="Recall" fill={colors.series[0]} radius={[4, 4, 0, 0]} maxBarSize={44} />
              <Bar dataKey="False alarms" fill={colors.series[1]} radius={[4, 4, 0, 0]} maxBarSize={44} />
            </BarChart>
          </ResponsiveContainer>
        </ChartFrame>
        <Caption>
          The fine-tuned model has no false alarms, but it also catches almost no drift: it answers COMPLIANT on
          94% of rule checks. A useful verifier needs the first bar tall and the second short. Against gpt-4o-mini
          its false-alarm rate is {fixed(Math.abs(vsGpt.false_alarm_rate.difference))} lower and its recall{" "}
          {fixed(Math.abs(vsGpt.recall.difference))} lower, so the hypothesis (fewer false alarms at equal or better
          recall) is not supported.
        </Caption>
      </Card>

      <Card title="All four arms, with 95% intervals">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[640px] border-collapse">
            <thead>
              <tr className="border-b border-border">
                <th className={th}>Arm</th>
                <th className={th}>Runs</th>
                <th className={th}>Recall</th>
                <th className={th}>Precision</th>
                <th className={th}>False-alarm rate</th>
              </tr>
            </thead>
            <tbody>
              {data.benchmark_arms.map((a) => (
                <tr key={a.name} className="border-b border-border last:border-0">
                  <td className="px-3 py-2 text-[13px] font-medium">{a.label}</td>
                  <td className={td}>{a.runs}</td>
                  <td className={td}>{interval(a.recall)}</td>
                  <td className={td}>{interval(a.precision)}</td>
                  <td className={td}>{interval(a.false_alarm_rate)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <Caption>
          Greedy decoding is deterministic, so the Qwen arms ran once and their intervals cover case sampling only.
          The two Qwen arms on the unseen example projects: tuned recall{" "}
          {interval(data.unseen_projects["qwen2.5-coder-1.5b-sft-r0"].recall)} against untuned{" "}
          {interval(data.unseen_projects["qwen2.5-coder-1.5b-untuned"].recall)}.
        </Caption>
      </Card>

      <Card title="Three training runs, same settings">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[560px] border-collapse">
            <thead>
              <tr className="border-b border-border">
                <th className={th}>Run</th>
                <th className={th}>False alarms (clean)</th>
                <th className={th}>Drift caught</th>
                <th className={th}>Gate</th>
                <th className={th}>Note</th>
              </tr>
            </thead>
            <tbody>
              <tr className="border-b border-border text-muted">
                <td className="px-3 py-2 text-[13px]">Untuned</td>
                <td className={td}>{data.untuned_gate.false_alarms} / {data.untuned_gate.clean}</td>
                <td className={td}>{data.untuned_gate.caught} / {data.untuned_gate.drift}</td>
                <td className="px-3 py-2">—</td>
                <td className="px-3 py-2 text-[13px]">baseline</td>
              </tr>
              {data.gate_runs.map((r) => (
                <tr key={r.run} className="border-b border-border last:border-0">
                  <td className="px-3 py-2 text-[13px] font-medium">Run {r.run}</td>
                  <td className={td}>{r.false_alarms} / {r.clean}</td>
                  <td className={td}>{r.caught} / {r.drift}</td>
                  <td className="px-3 py-2">
                    <Badge tone={r.gate === "GO" ? "compliant" : "uncertain"}>{r.gate}</Badge>
                  </td>
                  <td className="px-3 py-2 text-[13px] text-muted">{r.note}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <Caption>
          The false-alarm cut repeated in every run; recall never rose above the untuned model's, and the gate verdict
          flipped between runs with the same data and settings. Validation is a single project, so it cannot resolve a
          recall change of 0.05.
        </Caption>
      </Card>

      <Card title="Can the model's confidence be re-thresholded? Ranking AUC">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[520px] border-collapse">
            <thead>
              <tr className="border-b border-border">
                <th className={th}>Evaluation set</th>
                <th className={th}>Untuned</th>
                <th className={th}>Tuned [95% CI]</th>
              </tr>
            </thead>
            <tbody>
              {data.ranking_auc.map((r) => (
                <tr key={r.set} className="border-b border-border last:border-0">
                  <td className="px-3 py-2 text-[13px] font-medium">{r.set}</td>
                  <td className={td}>{fixed(r.untuned)}</td>
                  <td className={td}>
                    {fixed(r.tuned)} [{fixed(r.tuned_ci95[0])}, {fixed(r.tuned_ci95[1])}]
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <Caption>
          AUC of 0.5 means the model cannot rank drifted rule checks above clean ones. On the benchmark the tuned model
          is at chance, so moving the decision threshold cannot recover the missing recall: the training signal for
          project-level drift is what needs to change.
        </Caption>
      </Card>

      <Card title="Read this before quoting a number">
        <ul className="list-disc space-y-1.5 pl-5 text-[13px] leading-relaxed text-muted">
          {data.caveats.map((c) => (
            <li key={c}>{c}</li>
          ))}
        </ul>
      </Card>
    </div>
  );
}

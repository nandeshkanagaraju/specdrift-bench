import { ArrowRight } from "lucide-react";
import { Link } from "react-router-dom";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { ChartFrame, ChartTooltipStyle, useChartColors } from "../components/Chart";
import { Card, Caption, ErrorState, Skeleton } from "../components/ui/primitives";
import { StatCard } from "../components/ui/StatCard";
import { api } from "../lib/api";
import { pct } from "../lib/format";
import { useApi } from "../lib/useApi";

export function OverviewPage() {
  const { data, error, loading } = useApi((signal) => api.summary(signal));
  const colors = useChartColors();
  const tooltip = ChartTooltipStyle();

  if (error) return <ErrorState message={error} />;

  if (loading || !data) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-9 w-2/3 max-w-lg" />
        <div className="flex flex-wrap gap-3">
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-[92px] flex-1 min-w-[150px] rounded-xl" />
          ))}
        </div>
        <Skeleton className="h-[300px] rounded-xl" />
      </div>
    );
  }

  const detectorRows = data.detectors
    .filter((d) => d.scored)
    .map((d) => ({
      name: d.name,
      Recall: Number((d.recall * 100).toFixed(1)),
      "False alarms": Number((d.false_alarm_rate * 100).toFixed(1)),
    }));

  const escapeRows = data.categories
    .filter((c) => c.is_drift)
    .map((c) => ({
      category: c.category,
      name: c.name,
      rate: Number((c.escapes_rate * 100).toFixed(1)),
      n: c.n,
    }));

  return (
    <div className="space-y-8">
      <header>
        <h1 className="max-w-2xl text-[26px] font-semibold leading-tight tracking-tight">
          Does the code still do what the spec says?
        </h1>
        <p className="mt-1.5 max-w-2xl text-[13px] text-muted">
          {data.valid_cases} labelled cases across {data.projects.join(", ")}, scored against{" "}
          {data.detectors.length} detectors. Generated {data.generated}.
        </p>
      </header>

      <div className="flex flex-wrap gap-3">
        <StatCard label="Valid cases" value={data.valid_cases} hint={`${data.drift_cases} drift · ${data.negative_cases} controls`} />
        <StatCard label="Drift categories" value={data.categories.filter((c) => c.is_drift).length} hint="plus 3 negative controls" />
        <StatCard label="Detectors" value={data.detectors.length} hint="scored by identical code" />
        <StatCard
          hero
          label="Drift that passes tests"
          value={data.escapes_rate}
          format={(v) => pct(v)}
          hint={`${data.escapes_tests} of ${data.drift_cases} drift cases`}
        />
      </div>

      <Card title="Recall against false alarms">
        <ChartFrame>
          <ResponsiveContainer>
            <BarChart data={detectorRows} margin={{ top: 4, right: 8, left: -18, bottom: 0 }}>
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
          A detector is only useful when the teal bar is tall and the pink bar is short: catching
          drift matters no more than staying quiet on code that never drifted.
        </Caption>
      </Card>

      <Card
        title="Drift that survives the test suite"
        action={
          <Link to="/explorer?escapes_tests=true" className="inline-flex items-center gap-1 text-[12px] text-accent hover:underline">
            See the cases <ArrowRight size={12} />
          </Link>
        }
      >
        <ChartFrame>
          <ResponsiveContainer>
            <BarChart data={escapeRows} margin={{ top: 4, right: 8, left: -18, bottom: 0 }}>
              <CartesianGrid stroke={colors.grid} vertical={false} />
              <XAxis dataKey="category" stroke={colors.axis} fontSize={11} tickLine={false} axisLine={false} />
              <YAxis stroke={colors.axis} fontSize={11} tickLine={false} axisLine={false} unit="%" domain={[0, 100]} />
              <Tooltip
                {...tooltip}
                formatter={(v: number) => `${v}% still pass`}
                labelFormatter={(label) => {
                  const row = escapeRows.find((r) => r.category === label);
                  return row ? `${row.category} · ${row.name} (n=${row.n})` : String(label);
                }}
              />
              <Bar dataKey="rate" radius={[4, 4, 0, 0]} maxBarSize={44}>
                {escapeRows.map((row) => (
                  <Cell key={row.category} fill={row.rate >= 50 ? colors.series[1] : colors.series[0]} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </ChartFrame>
        <Caption>
          Each bar is the share of that category's cases whose project still passes every one of its
          own tests after the drift was injected. Unauthorised scope creep (D8) is invisible to tests
          by construction — the tests were written before the behaviour existed.
        </Caption>
      </Card>
    </div>
  );
}

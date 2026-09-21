import { DataTable } from "../components/ui/DataTable";
import { DiffView } from "../components/ui/DiffView";
import { StatCard } from "../components/ui/StatCard";
import { ConfidenceBar, VerdictPill } from "../components/ui/VerdictPill";
import {
  Badge,
  Caption,
  Card,
  EmptyState,
  ErrorState,
  FilterChip,
  Skeleton,
  Tabs,
  Tooltip,
} from "../components/ui/primitives";
import { useState } from "react";
import { pct } from "../lib/format";

const BEFORE = `def borrow(self, member_id, isbn, day):
    if len(self.active_loans(member_id)) >= MAX_ACTIVE_LOANS:
        raise LoanLimitExceeded("too many")
    return Loan(member_id, isbn, day)
`;
const AFTER = `def borrow(self, member_id, isbn, day):
    if len(self.active_loans(member_id)) > MAX_ACTIVE_LOANS:
        raise LoanLimitExceeded("too many")
    return Loan(member_id, isbn, day)
`;

/** Every component in one place, to eyeball both themes at once. */
export function KitchenSink() {
  const [tab, setTab] = useState<"a" | "b">("a");
  const [chip, setChip] = useState("D1");

  return (
    <div className="space-y-6">
      <h1 className="text-[22px] font-semibold tracking-tight">Kitchen sink</h1>

      <div className="flex flex-wrap gap-3">
        <StatCard label="Valid cases" value={86} />
        <StatCard label="Escapes tests" value={0.22} format={(v) => pct(v)} hero hint="13 of 59" />
      </div>

      <Card title="Verdicts and confidence">
        <div className="flex flex-wrap items-center gap-3">
          <VerdictPill verdict="COMPLIANT" />
          <VerdictPill verdict="DRIFT" />
          <VerdictPill verdict="UNCERTAIN" />
          <VerdictPill />
          <div className="w-40"><ConfidenceBar value={0.82} /></div>
        </div>
      </Card>

      <Card title="Badges, chips, tabs, tooltip">
        <div className="flex flex-wrap items-center gap-3">
          <Badge>neutral</Badge>
          <Badge tone="accent">accent</Badge>
          <Badge tone="drift">D7</Badge>
          <Badge tone="compliant">TP</Badge>
          <Badge tone="uncertain">passes tests</Badge>
          {["D1", "D8", "N2"].map((c) => (
            <FilterChip key={c} label={c} active={chip === c} onClick={() => setChip(c)} count={8} />
          ))}
          <Tabs value={tab} options={[{ value: "a", label: "One" }, { value: "b", label: "Two" }]} onChange={setTab} />
          <Tooltip label="the gold chunk is the one the patch touched">
            <span className="text-[13px] underline decoration-dotted">gold</span>
          </Tooltip>
        </div>
      </Card>

      <Card title="Diff">
        <DiffView before={BEFORE} after={AFTER} changedLines={[2]} context={4} />
      </Card>

      <Card title="Table">
        <DataTable
          rows={[
            { id: "library-D1-01", cat: "D1", verdict: "DRIFT" as const },
            { id: "library-N2-03", cat: "N2", verdict: "COMPLIANT" as const },
          ]}
          rowKey={(row) => row.id}
          columns={[
            { key: "id", header: "Case", sortValue: (r) => r.id, render: (r) => <span className="font-mono text-[12px]">{r.id}</span> },
            { key: "cat", header: "Category", render: (r) => <Badge>{r.cat}</Badge> },
            { key: "v", header: "Verdict", align: "right", render: (r) => <VerdictPill verdict={r.verdict} size="sm" /> },
          ]}
        />
      </Card>

      <div className="grid gap-4 md:grid-cols-2">
        <Card title="Empty and loading">
          <EmptyState title="No cases match" hint="Clear a filter, or widen the search." />
          <div className="mt-3 space-y-2">
            <Skeleton className="h-8 rounded-md" />
            <Skeleton className="h-8 w-2/3 rounded-md" />
          </div>
        </Card>
        <Card title="Error">
          <ErrorState message="500 Internal Server Error for /api/summary" />
          <Caption>Captions read like this, one line, plain language.</Caption>
        </Card>
      </div>
    </div>
  );
}

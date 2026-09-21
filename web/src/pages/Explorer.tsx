import { Search } from "lucide-react";
import { useMemo } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Badge, Caption, Card, EmptyState, ErrorState, FilterChip, Skeleton } from "../components/ui/primitives";
import { DataTable, type Column } from "../components/ui/DataTable";
import { VerdictPill } from "../components/ui/VerdictPill";
import { api } from "../lib/api";
import { CATEGORY_ORDER } from "../lib/format";
import type { CaseRow } from "../lib/types";
import { useApi } from "../lib/useApi";

export function ExplorerPage() {
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();

  const project = params.get("project") ?? "";
  const category = params.get("category") ?? "";
  const label = params.get("label") ?? "";
  const escapes = params.get("escapes_tests") ?? "";
  const q = params.get("q") ?? "";

  const { data, error, loading } = useApi(
    (signal) =>
      api.cases(
        {
          project: project || undefined,
          category: category || undefined,
          label: label || undefined,
          escapes_tests: escapes || undefined,
          q: q || undefined,
          page_size: "1000",
        },
        signal,
      ),
    [project, category, label, escapes, q],
  );

  const summary = useApi((signal) => api.summary(signal));

  // Filters live in the URL, so any view of the Explorer can be pasted to someone else.
  const setFilter = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (!value || next.get(key) === value) next.delete(key);
    else next.set(key, value);
    setParams(next, { replace: true });
  };

  const detectors = summary.data?.detectors.map((d) => d.name) ?? [];

  const columns: Column<CaseRow>[] = useMemo(() => {
    const base: Column<CaseRow>[] = [
      {
        key: "id",
        header: "Case",
        width: "210px",
        sortValue: (row) => row.id,
        render: (row) => <span className="font-mono text-[12px]">{row.id}</span>,
      },
      {
        key: "project",
        header: "Project",
        sortValue: (row) => row.project,
        render: (row) => <span className="text-muted">{row.project}</span>,
      },
      {
        key: "category",
        header: "Category",
        sortValue: (row) => row.category,
        render: (row) => (
          <Badge tone={row.label === "drift" ? "drift" : "neutral"} title={row.category_name}>
            {row.category}
          </Badge>
        ),
      },
      {
        key: "rules",
        header: "Target rules",
        render: (row) => (
          <span className="font-mono text-[11px] text-muted">
            {row.target_rules.length ? row.target_rules.join(", ") : "—"}
          </span>
        ),
      },
      {
        key: "escapes",
        header: "Passes tests",
        align: "right",
        sortValue: (row) => (row.escapes_tests ? 1 : 0),
        render: (row) =>
          row.escapes_tests ? (
            <span className="text-[12px] text-uncertain">yes</span>
          ) : (
            <span className="text-[12px] text-muted">no</span>
          ),
      },
    ];

    for (const name of detectors) {
      base.push({
        key: name,
        header: name,
        sortValue: (row) => row.verdicts[name] ?? "",
        render: (row) => <VerdictPill verdict={row.verdicts[name]} size="sm" />,
      });
    }
    return base;
  }, [detectors]);

  if (error) return <ErrorState message={error} />;

  const counts = summary.data?.categories ?? [];

  return (
    <div className="space-y-5">
      <header>
        <h1 className="text-[22px] font-semibold tracking-tight">Benchmark Explorer</h1>
        <p className="mt-1 text-[13px] text-muted">
          Every case, what it injects, and what each detector said about it.
        </p>
      </header>

      <Card>
        <div className="space-y-3">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="mr-1 text-[11px] uppercase tracking-[0.06em] text-muted">Project</span>
            {(summary.data?.projects ?? []).map((name) => (
              <FilterChip key={name} label={name} active={project === name} onClick={() => setFilter("project", name)} />
            ))}
          </div>

          <div className="flex flex-wrap items-center gap-1.5">
            <span className="mr-1 text-[11px] uppercase tracking-[0.06em] text-muted">Category</span>
            {CATEGORY_ORDER.map((cat) => (
              <FilterChip
                key={cat}
                label={cat}
                active={category === cat}
                count={counts.find((c) => c.category === cat)?.n}
                onClick={() => setFilter("category", cat)}
              />
            ))}
          </div>

          <div className="flex flex-wrap items-center gap-1.5">
            <span className="mr-1 text-[11px] uppercase tracking-[0.06em] text-muted">Label</span>
            <FilterChip label="drift" active={label === "drift"} onClick={() => setFilter("label", "drift")} />
            <FilterChip label="no drift" active={label === "no_drift"} onClick={() => setFilter("label", "no_drift")} />
            <span className="mx-2 h-4 w-px bg-border" />
            <FilterChip
              label="passes its own tests"
              active={escapes === "true"}
              onClick={() => setFilter("escapes_tests", "true")}
            />
          </div>

          <label className="flex items-center gap-2 rounded-lg border border-border bg-surface-2 px-3">
            <Search size={14} className="text-muted" aria-hidden />
            <input
              value={q}
              onChange={(event) => setFilter("q", event.target.value)}
              placeholder="Search case ids, notes, gold symbols…"
              className="w-full bg-transparent py-2 text-[13px] outline-none placeholder:text-muted"
            />
          </label>
        </div>
      </Card>

      <Card
        title={loading ? "Loading…" : `${data?.total ?? 0} cases`}
        action={
          (project || category || label || escapes || q) && (
            <button
              type="button"
              onClick={() => setParams(new URLSearchParams(), { replace: true })}
              className="text-[12px] text-accent hover:underline"
            >
              Clear filters
            </button>
          )
        }
      >
        {loading ? (
          <div className="space-y-2">
            {Array.from({ length: 8 }).map((_, i) => (
              <Skeleton key={i} className="h-9 rounded-md" />
            ))}
          </div>
        ) : (
          <DataTable
            rows={data?.items ?? []}
            columns={columns}
            rowKey={(row) => row.id}
            onRowClick={(row) => navigate(`/cases/${row.id}`)}
            initialSort={{ key: "id", direction: "asc" }}
            empty={<EmptyState title="No cases match these filters" hint="Clear a filter, or widen the search." />}
          />
        )}
        <Caption>Click any row to see the diff, the rule, and every detector's reasoning.</Caption>
      </Card>
    </div>
  );
}

import { ChevronDown, ChevronUp } from "lucide-react";
import { type ReactNode, useMemo, useState } from "react";
import { cn } from "../../lib/format";

export interface Column<T> {
  key: string;
  header: string;
  align?: "left" | "right";
  width?: string;
  sortValue?: (row: T) => string | number;
  render: (row: T) => ReactNode;
}

/** Sortable, keyboard navigable, sticky header. Rows activate on Enter or Space. */
export function DataTable<T>({
  rows,
  columns,
  rowKey,
  onRowClick,
  empty,
  initialSort,
}: {
  rows: T[];
  columns: Column<T>[];
  rowKey: (row: T) => string;
  onRowClick?: (row: T) => void;
  empty?: ReactNode;
  initialSort?: { key: string; direction: "asc" | "desc" };
}) {
  const [sort, setSort] = useState(initialSort ?? null);

  const sorted = useMemo(() => {
    if (!sort) return rows;
    const column = columns.find((c) => c.key === sort.key);
    if (!column?.sortValue) return rows;

    const factor = sort.direction === "asc" ? 1 : -1;
    return [...rows].sort((a, b) => {
      const left = column.sortValue!(a);
      const right = column.sortValue!(b);
      if (left === right) return 0;
      return left > right ? factor : -factor;
    });
  }, [rows, sort, columns]);

  const toggle = (key: string) =>
    setSort((current) =>
      current?.key === key
        ? { key, direction: current.direction === "asc" ? "desc" : "asc" }
        : { key, direction: "asc" },
    );

  if (!rows.length && empty) return <>{empty}</>;

  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-[13px]">
        <thead className="sticky top-0 z-10 bg-surface">
          <tr>
            {columns.map((column) => (
              <th
                key={column.key}
                scope="col"
                style={{ width: column.width }}
                className={cn(
                  "border-b border-border px-3 py-2 text-[11px] font-medium uppercase tracking-[0.05em] text-muted",
                  column.align === "right" ? "text-right" : "text-left",
                )}
              >
                {column.sortValue ? (
                  <button
                    type="button"
                    onClick={() => toggle(column.key)}
                    className="inline-flex items-center gap-1 hover:text-text"
                  >
                    {column.header}
                    {sort?.key === column.key &&
                      (sort.direction === "asc" ? <ChevronUp size={12} /> : <ChevronDown size={12} />)}
                  </button>
                ) : (
                  column.header
                )}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sorted.map((row) => (
            <tr
              key={rowKey(row)}
              tabIndex={onRowClick ? 0 : undefined}
              onClick={onRowClick ? () => onRowClick(row) : undefined}
              onKeyDown={
                onRowClick
                  ? (event) => {
                      if (event.key === "Enter" || event.key === " ") {
                        event.preventDefault();
                        onRowClick(row);
                      }
                    }
                  : undefined
              }
              className={cn(
                "border-b border-border/70 transition-colors",
                onRowClick && "cursor-pointer hover:bg-surface-2 focus:bg-surface-2",
              )}
            >
              {columns.map((column) => (
                <td
                  key={column.key}
                  className={cn("px-3 py-2 align-middle", column.align === "right" && "text-right")}
                >
                  {column.render(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

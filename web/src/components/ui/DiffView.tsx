import { useMemo } from "react";
import { CodeBlock } from "./CodeBlock";
import { cn } from "../../lib/format";

/**
 * Side by side on desktop, stacked on narrow screens. Only the window around the
 * change is shown, because a 130-line file with one changed line reads as noise.
 */
export function DiffView({
  before,
  after,
  changedLines,
  context = 8,
  scrollTo = null,
  className,
}: {
  before: string;
  after: string;
  changedLines: number[];
  context?: number;
  scrollTo?: number | null;
  className?: string;
}) {
  const window = useMemo(() => {
    const total = after.split("\n").length;
    if (!changedLines.length) return { start: 1, end: Math.min(total, 40) };
    const start = Math.max(1, Math.min(...changedLines) - context);
    const end = Math.min(total, Math.max(...changedLines) + context);
    return { start, end };
  }, [after, changedLines, context]);

  const slice = (text: string) =>
    text.split("\n").slice(window.start - 1, window.end).join("\n");

  if (!before && !after) {
    return (
      <p className="rounded-lg border border-dashed border-border px-4 py-6 text-center text-[13px] text-muted">
        This case applies no patch — it is the project exactly as written.
      </p>
    );
  }

  return (
    <div className={cn("grid gap-3 lg:grid-cols-2", className)}>
      <div>
        <p className="mb-1.5 text-[11px] font-medium uppercase tracking-[0.06em] text-muted">
          Before
        </p>
        <CodeBlock code={slice(before)} startLine={window.start} highlight={changedLines} tone="removed" />
      </div>
      <div>
        <p className="mb-1.5 text-[11px] font-medium uppercase tracking-[0.06em] text-muted">
          After <span className="text-drift">· patched</span>
        </p>
        <CodeBlock
          code={slice(after)}
          startLine={window.start}
          highlight={changedLines}
          tone="added"
          scrollTo={scrollTo}
        />
      </div>
    </div>
  );
}

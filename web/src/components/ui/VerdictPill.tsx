import { AlertTriangle, CheckCircle2, HelpCircle, MinusCircle } from "lucide-react";
import type { VerdictValue } from "../../lib/types";
import { cn } from "../../lib/format";

const STYLES: Record<VerdictValue, { className: string; Icon: typeof CheckCircle2 }> = {
  COMPLIANT: { className: "bg-[rgba(52,211,153,.14)] text-compliant", Icon: CheckCircle2 },
  DRIFT: { className: "bg-[rgba(251,113,133,.14)] text-drift", Icon: AlertTriangle },
  UNCERTAIN: { className: "bg-[rgba(251,191,36,.14)] text-uncertain", Icon: HelpCircle },
};

/** Never colour alone: the icon and the word carry the verdict too. */
export function VerdictPill({
  verdict,
  size = "md",
}: {
  verdict?: VerdictValue | null;
  size?: "sm" | "md";
}) {
  if (!verdict) {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-surface-2 px-2 py-0.5 text-[11px] text-muted">
        <MinusCircle size={12} aria-hidden /> not run
      </span>
    );
  }

  const { className, Icon } = STYLES[verdict];
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full font-semibold",
        className,
        size === "sm" ? "px-2 py-0.5 text-[11px]" : "px-2.5 py-1 text-xs",
      )}
    >
      <Icon size={size === "sm" ? 12 : 14} aria-hidden />
      {verdict}
    </span>
  );
}

export function ConfidenceBar({ value, label = true }: { value: number; label?: boolean }) {
  const width = Math.max(0, Math.min(1, value)) * 100;
  return (
    <div className="flex items-center gap-2">
      <div
        className="h-1.5 w-full min-w-[54px] overflow-hidden rounded-full bg-surface-2"
        role="meter"
        aria-valuenow={Number(value.toFixed(2))}
        aria-valuemin={0}
        aria-valuemax={1}
        aria-label="confidence"
      >
        <div className="h-full rounded-full bg-accent transition-[width] duration-500" style={{ width: `${width}%` }} />
      </div>
      {label && <span className="tabular font-mono text-[11px] text-muted">{value.toFixed(2)}</span>}
    </div>
  );
}

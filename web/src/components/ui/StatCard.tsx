import { useEffect, useRef, useState } from "react";
import { cn } from "../../lib/format";

/** Counts up to the value once, and not at all when the viewer asked for less motion. */
function useCountUp(target: number, duration = 700): number {
  const [value, setValue] = useState(target);
  const frame = useRef<number>();

  useEffect(() => {
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduced) {
      setValue(target);
      return;
    }

    const started = performance.now();
    const step = (now: number) => {
      const progress = Math.min((now - started) / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 3);
      setValue(target * eased);
      if (progress < 1) frame.current = requestAnimationFrame(step);
    };

    frame.current = requestAnimationFrame(step);
    return () => {
      if (frame.current) cancelAnimationFrame(frame.current);
    };
  }, [target, duration]);

  return value;
}

export function StatCard({
  label,
  value,
  format = (v) => Math.round(v).toString(),
  hint,
  hero = false,
}: {
  label: string;
  value: number;
  format?: (value: number) => string;
  hint?: string;
  hero?: boolean;
}) {
  const animated = useCountUp(value);

  return (
    <div
      className={cn(
        "relative flex-1 overflow-hidden rounded-xl border border-border bg-surface p-4",
        hero && "before:absolute before:-right-10 before:-top-16 before:h-32 before:w-32 before:rounded-full before:bg-accent/15 before:blur-3xl",
      )}
    >
      <p className="text-[11px] font-medium uppercase tracking-[0.07em] text-muted">{label}</p>
      <p className={cn("tabular mt-1 font-mono font-semibold", hero ? "text-3xl" : "text-2xl")}>
        {format(animated)}
      </p>
      {hint && <p className="mt-1 text-[12px] leading-snug text-muted">{hint}</p>}
    </div>
  );
}

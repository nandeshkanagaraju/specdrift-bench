import { type ReactNode, useId, useState } from "react";
import { cn } from "../../lib/format";

export function Card({
  children,
  className,
  title,
  action,
}: {
  children: ReactNode;
  className?: string;
  title?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <section className={cn("hairline rounded-xl bg-surface", className)}>
      {(title || action) && (
        <header className="flex items-center justify-between gap-3 border-b border-border px-4 py-3">
          <h2 className="text-sm font-semibold tracking-tight">{title}</h2>
          {action}
        </header>
      )}
      <div className="p-4">{children}</div>
    </section>
  );
}

export function Caption({ children }: { children: ReactNode }) {
  return <p className="mt-2 text-[13px] leading-relaxed text-muted">{children}</p>;
}

export function Badge({
  children,
  tone = "neutral",
  title,
}: {
  children: ReactNode;
  tone?: "neutral" | "accent" | "drift" | "compliant" | "uncertain";
  title?: string;
}) {
  const tones = {
    neutral: "border-border bg-surface-2 text-muted",
    accent: "border-transparent bg-[var(--accent-soft)] text-accent",
    drift: "border-transparent bg-[rgba(251,113,133,.14)] text-drift",
    compliant: "border-transparent bg-[rgba(52,211,153,.14)] text-compliant",
    uncertain: "border-transparent bg-[rgba(251,191,36,.14)] text-uncertain",
  } as const;

  return (
    <span
      title={title}
      className={cn(
        "inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-medium",
        tones[tone],
      )}
    >
      {children}
    </span>
  );
}

export function FilterChip({
  label,
  active,
  onClick,
  count,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
  count?: number;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={cn(
        "rounded-full border px-3 py-1 text-xs transition-colors",
        active
          ? "border-accent bg-[var(--accent-soft)] text-accent"
          : "border-border bg-surface text-muted hover:text-text",
      )}
    >
      {label}
      {count !== undefined && <span className="ml-1.5 tabular opacity-70">{count}</span>}
    </button>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("skeleton", className)} aria-hidden />;
}

export function EmptyState({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-1 rounded-xl border border-dashed border-border px-6 py-12 text-center">
      <p className="text-sm font-medium">{title}</p>
      {hint && <p className="max-w-sm text-[13px] text-muted">{hint}</p>}
    </div>
  );
}

export function ErrorState({ message }: { message: string }) {
  return (
    <div className="rounded-xl border border-drift/40 bg-[rgba(251,113,133,.08)] px-4 py-3 text-[13px] text-drift">
      {message}
      <span className="mt-1 block text-muted">
        Is the API running? Start it with <code className="font-mono">specdrift serve</code>.
      </span>
    </div>
  );
}

export function Tabs<T extends string>({
  value,
  options,
  onChange,
}: {
  value: T;
  options: { value: T; label: string }[];
  onChange: (value: T) => void;
}) {
  return (
    <div role="tablist" className="inline-flex rounded-lg border border-border bg-surface-2 p-0.5">
      {options.map((option) => (
        <button
          key={option.value}
          role="tab"
          aria-selected={option.value === value}
          onClick={() => onChange(option.value)}
          className={cn(
            "rounded-md px-3 py-1 text-xs transition-colors",
            option.value === value ? "bg-surface text-text shadow-sm" : "text-muted hover:text-text",
          )}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}

export function Tooltip({ label, children }: { label: string; children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const id = useId();

  return (
    <span
      className="relative inline-flex"
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
      onFocus={() => setOpen(true)}
      onBlur={() => setOpen(false)}
    >
      <span aria-describedby={open ? id : undefined}>{children}</span>
      {open && (
        <span
          id={id}
          role="tooltip"
          className="pointer-events-none absolute bottom-full left-1/2 z-30 mb-1.5 -translate-x-1/2 whitespace-nowrap rounded-md border border-border bg-surface-2 px-2 py-1 text-[11px] text-text shadow-lg"
        >
          {label}
        </span>
      )}
    </span>
  );
}

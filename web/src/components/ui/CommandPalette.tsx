import { Command, CornerDownLeft, Search } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../../lib/api";
import type { CaseRow } from "../../lib/types";
import { cn } from "../../lib/format";

interface Entry {
  id: string;
  label: string;
  hint: string;
  to: string;
}

const PAGES: Entry[] = [
  { id: "page-overview", label: "Overview", hint: "page", to: "/" },
  { id: "page-explorer", label: "Benchmark Explorer", hint: "page", to: "/explorer" },
  { id: "page-compare", label: "Detector Comparison", hint: "page", to: "/compare" },
  { id: "page-live", label: "Live Check", hint: "page", to: "/live" },
];

/** Subsequence match, so "lD201" still finds library-D2-01. */
function fuzzy(needle: string, haystack: string): boolean {
  if (!needle) return true;
  let index = 0;
  const lower = haystack.toLowerCase();
  for (const character of needle.toLowerCase()) {
    index = lower.indexOf(character, index);
    if (index === -1) return false;
    index += 1;
  }
  return true;
}

export function CommandPalette() {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [cursor, setCursor] = useState(0);
  const [cases, setCases] = useState<CaseRow[]>([]);
  const input = useRef<HTMLInputElement>(null);
  const navigate = useNavigate();

  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setOpen((value) => !value);
      } else if (event.key === "Escape") {
        setOpen(false);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  useEffect(() => {
    if (!open) return;
    setQuery("");
    setCursor(0);
    input.current?.focus();
    if (!cases.length) {
      api.cases({ page_size: "1000" }).then((list) => setCases(list.items)).catch(() => {});
    }
  }, [open, cases.length]);

  const entries = useMemo(() => {
    const caseEntries: Entry[] = cases.map((row) => ({
      id: row.id,
      label: row.id,
      hint: `${row.category} · ${row.category_name}`,
      to: `/cases/${row.id}`,
    }));
    return [...PAGES, ...caseEntries].filter((entry) => fuzzy(query, `${entry.label} ${entry.hint}`)).slice(0, 40);
  }, [cases, query]);

  if (!open) return null;

  const go = (entry: Entry) => {
    setOpen(false);
    navigate(entry.to);
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center bg-black/50 px-4 pt-[12vh] backdrop-blur-sm"
      onClick={() => setOpen(false)}
      role="presentation"
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Command palette"
        onClick={(event) => event.stopPropagation()}
        className="w-full max-w-xl overflow-hidden rounded-xl border border-border bg-surface shadow-2xl animate-rise"
      >
        <div className="flex items-center gap-2 border-b border-border px-3">
          <Search size={15} className="text-muted" aria-hidden />
          <input
            ref={input}
            value={query}
            placeholder="Jump to a case id or a page…"
            onChange={(event) => {
              setQuery(event.target.value);
              setCursor(0);
            }}
            onKeyDown={(event) => {
              if (event.key === "ArrowDown") {
                event.preventDefault();
                setCursor((c) => Math.min(c + 1, entries.length - 1));
              } else if (event.key === "ArrowUp") {
                event.preventDefault();
                setCursor((c) => Math.max(c - 1, 0));
              } else if (event.key === "Enter" && entries[cursor]) {
                go(entries[cursor]);
              }
            }}
            className="w-full bg-transparent py-3 text-sm outline-none placeholder:text-muted"
          />
          <kbd className="hidden items-center gap-1 rounded border border-border px-1.5 py-0.5 font-mono text-[10px] text-muted sm:flex">
            esc
          </kbd>
        </div>

        <ul className="max-h-[52vh] overflow-y-auto py-1">
          {entries.length === 0 && (
            <li className="px-4 py-6 text-center text-[13px] text-muted">Nothing matches “{query}”.</li>
          )}
          {entries.map((entry, index) => (
            <li key={entry.id}>
              <button
                type="button"
                onMouseEnter={() => setCursor(index)}
                onClick={() => go(entry)}
                className={cn(
                  "flex w-full items-center justify-between gap-3 px-4 py-2 text-left text-[13px]",
                  index === cursor ? "bg-surface-2" : "hover:bg-surface-2/60",
                )}
              >
                <span className="font-mono">{entry.label}</span>
                <span className="flex items-center gap-2 text-[11px] text-muted">
                  {entry.hint}
                  {index === cursor && <CornerDownLeft size={12} aria-hidden />}
                </span>
              </button>
            </li>
          ))}
        </ul>

        <footer className="flex items-center gap-2 border-t border-border px-4 py-2 text-[11px] text-muted">
          <Command size={11} aria-hidden /> K toggles this palette
        </footer>
      </div>
    </div>
  );
}

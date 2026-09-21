import { motion } from "framer-motion";
import { Activity, LayoutDashboard, Moon, Play, Rows3, Sun } from "lucide-react";
import { type ReactNode } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { CommandPalette } from "./ui/CommandPalette";
import { useTheme } from "../lib/theme";
import { cn } from "../lib/format";

const NAV = [
  { to: "/", label: "Overview", Icon: LayoutDashboard, end: true },
  { to: "/explorer", label: "Explorer", Icon: Rows3, end: false },
  { to: "/compare", label: "Compare", Icon: Activity, end: false },
  { to: "/live", label: "Live Check", Icon: Play, end: false },
];

export function AppShell({ children }: { children: ReactNode }) {
  const { theme, toggle } = useTheme();
  const location = useLocation();

  return (
    <div className="flex min-h-full">
      <CommandPalette />

      <aside className="sticky top-0 hidden h-screen w-[208px] shrink-0 flex-col border-r border-border bg-surface px-3 py-4 md:flex">
        <div className="px-2 pb-5">
          <p className="font-mono text-[15px] font-semibold tracking-tight">
            Spec<span className="text-accent">Drift</span>
          </p>
          <p className="mt-0.5 text-[11px] text-muted">drift detection benchmark</p>
        </div>

        <nav className="flex flex-col gap-0.5">
          {NAV.map(({ to, label, Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-[13px] transition-colors",
                  isActive
                    ? "bg-[var(--accent-soft)] text-accent"
                    : "text-muted hover:bg-surface-2 hover:text-text",
                )
              }
            >
              <Icon size={15} aria-hidden />
              {label}
            </NavLink>
          ))}
        </nav>

        <div className="mt-auto px-2 pt-4">
          <button
            type="button"
            onClick={toggle}
            className="flex w-full items-center gap-2 rounded-lg border border-border px-2.5 py-2 text-[12px] text-muted transition-colors hover:text-text"
          >
            {theme === "dark" ? <Moon size={14} aria-hidden /> : <Sun size={14} aria-hidden />}
            {theme === "dark" ? "Dark" : "Light"} theme
          </button>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-20 flex items-center justify-between gap-3 border-b border-border bg-bg/85 px-4 py-2.5 backdrop-blur md:px-6">
          <nav className="flex gap-1 md:hidden">
            {NAV.map(({ to, label, end }) => (
              <NavLink
                key={to}
                to={to}
                end={end}
                className={({ isActive }) =>
                  cn(
                    "rounded-md px-2 py-1 text-[12px]",
                    isActive ? "bg-[var(--accent-soft)] text-accent" : "text-muted",
                  )
                }
              >
                {label}
              </NavLink>
            ))}
          </nav>
          <p className="hidden text-[12px] text-muted md:block">
            Does the code still do what the spec says?
          </p>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() =>
                window.dispatchEvent(new KeyboardEvent("keydown", { key: "k", metaKey: true }))
              }
              className="hidden items-center gap-1.5 rounded-lg border border-border px-2.5 py-1 text-[12px] text-muted hover:text-text sm:flex"
            >
              Search
              <kbd className="font-mono text-[10px]">⌘K</kbd>
            </button>
            <button
              type="button"
              onClick={toggle}
              aria-label="Toggle theme"
              className="rounded-lg border border-border p-1.5 text-muted hover:text-text md:hidden"
            >
              {theme === "dark" ? <Moon size={14} /> : <Sun size={14} />}
            </button>
          </div>
        </header>

        <motion.main
          key={location.pathname}
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.2, ease: "easeOut" }}
          className="mx-auto w-full max-w-content flex-1 px-4 py-6 md:px-6"
        >
          {children}
        </motion.main>
      </div>
    </div>
  );
}

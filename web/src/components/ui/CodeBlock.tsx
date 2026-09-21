import { type ThemedToken } from "shiki/core";
import { useEffect, useRef, useState } from "react";
import { THEMES, tokenizePython } from "../../lib/highlight";
import { useTheme } from "../../lib/theme";
import { cn } from "../../lib/format";

export interface CodeBlockProps {
  code: string;
  startLine?: number;
  /** 1-based line numbers to tint. */
  highlight?: number[];
  tone?: "added" | "removed" | "neutral";
  /** Scroll this 1-based line into view when it changes. */
  scrollTo?: number | null;
  maxHeight?: string;
  className?: string;
}

export function CodeBlock({
  code,
  startLine = 1,
  highlight = [],
  tone = "neutral",
  scrollTo = null,
  maxHeight = "460px",
  className,
}: CodeBlockProps) {
  const { theme } = useTheme();
  const [lines, setLines] = useState<ThemedToken[][] | null>(null);
  const container = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let live = true;
    tokenizePython(code, theme === "light" ? THEMES.light : THEMES.dark)
      .then((tokens) => live && setLines(tokens))
      .catch(() => live && setLines(null));
    return () => {
      live = false;
    };
  }, [code, theme]);

  useEffect(() => {
    if (!scrollTo || !container.current) return;
    const target = container.current.querySelector(`[data-line="${scrollTo}"]`);
    target?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [scrollTo, lines]);

  const marked = new Set(highlight);
  const toneClass =
    tone === "added"
      ? "bg-[rgba(52,211,153,.13)] border-l-2 border-compliant"
      : tone === "removed"
        ? "bg-[rgba(251,113,133,.13)] border-l-2 border-drift"
        : "bg-[var(--accent-soft)] border-l-2 border-accent";

  const raw = code.split("\n");

  return (
    <div
      ref={container}
      style={{ maxHeight }}
      className={cn(
        "overflow-auto rounded-lg border border-border bg-surface-2 font-mono text-[12px] leading-[1.65]",
        className,
      )}
    >
      <pre className="min-w-max py-2">
        {raw.map((fallback, index) => {
          const lineNo = startLine + index;
          const tokens = lines?.[index];
          return (
            <div
              key={lineNo}
              data-line={lineNo}
              className={cn(
                "flex px-0 pl-0",
                marked.has(lineNo) ? toneClass : "border-l-2 border-transparent",
              )}
            >
              <span className="tabular sticky left-0 select-none bg-surface-2 px-3 text-right text-muted/60">
                {lineNo}
              </span>
              <code className="whitespace-pre pr-4">
                {tokens
                  ? tokens.map((token, i) => (
                      <span key={i} style={{ color: token.color }}>
                        {token.content}
                      </span>
                    ))
                  : fallback}
              </code>
            </div>
          );
        })}
      </pre>
    </div>
  );
}

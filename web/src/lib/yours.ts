import type { CheckSummary, UploadRecord, Verdict, VerdictValue } from "./types";

const RULE_RE = /^\s*[-*]\s+\*\*(R\d+)\*\*\s+(.+?)\s*$/;

export interface PreviewRule {
  id: string;
  text: string;
  line: number;
}

/** The same rule shape the server parser accepts, counted while the spec is still a draft. */
export function previewRules(spec: string): { rules: PreviewRule[]; duplicates: string[] } {
  const rules: PreviewRule[] = [];
  const seen = new Map<string, number>();
  const duplicates: string[] = [];

  spec.split("\n").forEach((line, index) => {
    const match = RULE_RE.exec(line);
    if (!match) return;
    const id = match[1];
    if (seen.has(id)) {
      if (!duplicates.includes(id)) duplicates.push(id);
      return;
    }
    seen.set(id, index + 1);
    rules.push({ id, text: match[2], line: index + 1 });
  });

  return { rules, duplicates };
}

export interface Flip {
  ruleId: string;
  from: VerdictValue;
  to: VerdictValue;
}

/** Rules whose answer changed between two checks of the same specification. */
export function flippedRules(previous: Verdict[], next: Verdict[]): Flip[] {
  const before = new Map(previous.map((verdict) => [verdict.rule_id, verdict.verdict]));
  return next.flatMap((verdict) => {
    const from = before.get(verdict.rule_id);
    if (!from || from === verdict.verdict) return [];
    return [{ ruleId: verdict.rule_id, from, to: verdict.verdict }];
  });
}

export function citedExcerpt(
  files: { path: string; source: string }[],
  verdict: Verdict,
): { path: string; code: string; start: number } | null {
  const fromChunk = verdict.retrieved_chunks[0]?.split("::")[0] ?? "";
  const wanted = verdict.evidence.file || fromChunk;
  if (!wanted) return null;

  const file = files.find(
    (item) => item.path === wanted || item.path.endsWith(`/${wanted}`) || wanted.endsWith(item.path),
  );
  if (!file) return null;

  const lines = file.source.split("\n");
  const start = verdict.evidence.start_line > 0 ? verdict.evidence.start_line : 1;
  const end =
    verdict.evidence.end_line >= start ? verdict.evidence.end_line : Math.min(lines.length, start + 24);
  return {
    path: file.path,
    code: lines.slice(start - 1, end).join("\n"),
    start,
  };
}

export function reportMarkdown(
  upload: UploadRecord,
  verdicts: Verdict[],
  summary: CheckSummary | null,
  flips: Flip[],
): string {
  const lines: string[] = [
    `# SpecDrift report — ${upload.name}`,
    "",
    summary
      ? `Status: **${summary.status}** · ${summary.counts.DRIFT} drift, ${summary.counts.COMPLIANT} compliant, ${summary.counts.UNCERTAIN} uncertain · model \`${summary.model}\`.`
      : "The check did not finish.",
    "",
  ];

  if (flips.length) {
    lines.push("## What changed since the previous check", "");
    for (const flip of flips) {
      lines.push(`- **${flip.ruleId}** ${flip.from} → ${flip.to}`);
    }
    lines.push("");
  }

  lines.push("## Rules", "");
  const byId = new Map(verdicts.map((verdict) => [verdict.rule_id, verdict]));
  for (const rule of upload.rules) {
    const verdict = byId.get(rule.id);
    lines.push(`### ${rule.id} · ${verdict?.verdict ?? "not checked"}`, "", rule.text, "");
    if (!verdict) continue;
    if (verdict.violated_clause) lines.push(`Quoted clause: ${verdict.violated_clause}`, "");
    const example = verdict.counterexample;
    if (example.input || example.expected || example.actual) {
      lines.push(
        `Counterexample: input \`${example.input}\`, expected \`${example.expected}\`, actual \`${example.actual}\`.`,
        "",
      );
    }
    const excerpt = citedExcerpt(upload.files, verdict);
    if (excerpt) {
      lines.push(`\`${excerpt.path}\` from line ${excerpt.start}:`, "", "```python", excerpt.code, "```", "");
    }
    if (verdict.downgraded) {
      lines.push("This drift claim was downgraded because it lacked a quoted clause and a counterexample.", "");
    }
  }

  return lines.join("\n");
}

export function downloadText(filename: string, text: string): void {
  const blob = new Blob([text], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

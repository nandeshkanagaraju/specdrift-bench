import { createHighlighterCore, type HighlighterCore, type ThemedToken } from "shiki/core";
import { createOnigurumaEngine } from "shiki/engine/oniguruma";
import python from "shiki/langs/python.mjs";
import githubDark from "shiki/themes/github-dark-default.mjs";
import githubLight from "shiki/themes/github-light.mjs";

/**
 * One highlighter for the whole app, created on first use.
 *
 * Built from shiki's core with exactly one grammar and two themes: the convenience
 * entry point ships every language it knows, which is 6 MB of Wolfram and Emacs Lisp
 * we would never load a line of.
 */
let pending: Promise<HighlighterCore> | null = null;

export const THEMES = { dark: "github-dark-default", light: "github-light" } as const;

export function getHighlighter(): Promise<HighlighterCore> {
  if (!pending) {
    pending = createHighlighterCore({
      themes: [githubDark, githubLight],
      langs: [python],
      engine: createOnigurumaEngine(() => import("shiki/wasm")),
    });
  }
  return pending;
}

export async function tokenizePython(code: string, theme: string): Promise<ThemedToken[][]> {
  const highlighter = await getHighlighter();
  return highlighter.codeToTokens(code, { lang: "python", theme }).tokens;
}

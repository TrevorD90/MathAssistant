// Renders tutor/learner text with $...$ math via KaTeX (bundled, trust=false).
// Plain text is rendered as React text nodes (escaped); only KaTeX output is
// injected as HTML, and KaTeX escapes its input.

import katex from "katex";
import { useMemo } from "react";

export interface Segment {
  math: boolean;
  text: string;
  display?: boolean;
}

// Split on $$...$$, $...$, \(...\), \[...\]. Unclosed delimiters stay as text.
// Inline $...$ follows the Pandoc rule so money isn't mistaken for math: the
// opening $ must be followed by a non-space, the closing $ must follow a
// non-space and must not be followed by a digit, and \$ is a literal dollar.
// "$3x+5$" is math; "Sam has $5 and buys a $2 toy" stays text.
export function splitMath(input: string): Segment[] {
  const re = /\$\$([\s\S]+?)\$\$|(?<!\\)\$(?=\S)([^$]*?\S)\$(?!\d)|\\\(([\s\S]+?)\\\)|\\\[([\s\S]+?)\\\]/g;
  const out: Segment[] = [];
  let last = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(input)) !== null) {
    if (m.index > last) out.push({ math: false, text: input.slice(last, m.index) });
    const body = m[1] ?? m[2] ?? m[3] ?? m[4] ?? "";
    out.push({ math: true, text: body, display: m[1] !== undefined || m[4] !== undefined });
    last = re.lastIndex;
  }
  if (last < input.length) out.push({ math: false, text: input.slice(last) });
  return out;
}

export function renderLatex(latex: string, displayMode = false): string {
  return katex.renderToString(latex, {
    throwOnError: false,
    displayMode,
    trust: false,
    strict: "ignore",
    output: "htmlAndMathml",
    maxExpand: 200,
  });
}

export function MathText({ text }: { text: string }) {
  const parts = useMemo(() => splitMath(text), [text]);
  return (
    <span className="math-text">
      {parts.map((p, i) =>
        p.math ? (
          <span key={i} dangerouslySetInnerHTML={{ __html: renderLatex(p.text, p.display) }} />
        ) : (
          <span key={i}>{p.text}</span>
        ),
      )}
    </span>
  );
}

export function Latex({ latex, display = false }: { latex: string; display?: boolean }) {
  const html = useMemo(() => renderLatex(latex, display), [latex, display]);
  return <span className="latex" dangerouslySetInnerHTML={{ __html: html }} />;
}

import { describe, expect, it } from "vitest";
import { splitMath, renderLatex } from "./components/MathText";
import { isRenderable } from "./components/DisplayBox";
import { LAYOUTS } from "./components/keyboard/layouts";

describe("splitMath", () => {
  it("splits inline and display math", () => {
    const parts = splitMath("Let $u=x^2$. Then $$\\sin u$$ ok");
    expect(parts.map((p) => [p.math, p.text])).toEqual([
      [false, "Let "], [true, "u=x^2"], [false, ". Then "], [true, "\\sin u"], [false, " ok"],
    ]);
    expect(parts[3].display).toBe(true);
  });
  it("leaves unclosed dollars as text", () => {
    expect(splitMath("costs $5 today")).toEqual([{ math: false, text: "costs $5 today" }]);
  });
  it("treats money as text, not math (word problems)", () => {
    for (const s of ["Sam has $5 and buys a $2 toy.", "It costs $4.50 or $6.", "between $2 and $3", "a $ 5 bill $"]) {
      expect(splitMath(s).every((p) => !p.math)).toBe(true);
    }
  });
  it("still finds real inline math", () => {
    expect(splitMath("Solve $3x+5=20$ now").filter((p) => p.math).map((p) => p.text)).toEqual(["3x+5=20"]);
    expect(splitMath("Let $x$ be $2$.").filter((p) => p.math).map((p) => p.text)).toEqual(["x", "2"]);
    expect(splitMath("You have $5, so $5-2$ is left").filter((p) => p.math).map((p) => p.text)).toEqual(["5-2"]);
  });
});

describe("renderLatex", () => {
  it("never throws on bad input and does not execute html", () => {
    const html = renderLatex("\\frac{1}{");
    expect(typeof html).toBe("string");
    // trust=false: \href is refused (shown as escaped error text), never emitted as a link.
    const out = renderLatex("\\href{javascript:alert(1)}{x}");
    expect(out).not.toMatch(/href\s*=\s*["']?javascript:/i);
    expect(out).not.toContain("<a ");
  });
});

describe("display payload", () => {
  it("renders only known, non-empty latex payloads", () => {
    expect(isRenderable(null)).toBe(false);
    expect(isRenderable({ type: "latex", title: "", items: [] })).toBe(false);
    expect(isRenderable({ type: "graph", title: "", items: [{ latex: "x", caption: "" }] } as never)).toBe(false);
    expect(isRenderable({ type: "latex", title: "", items: [{ latex: "3\\times4", caption: "" }] })).toBe(true);
  });
});

describe("keyboard layouts (spec §5)", () => {
  const flat = (i: number) => JSON.stringify(LAYOUTS[i]);
  it("has the five tabs in order", () => {
    expect(LAYOUTS.map((l) => l.label)).toEqual(["Basic", "Algebra", "Functions", "Calculus", "Advanced"]);
  });
  it("covers the minimum keys", () => {
    for (const k of ["[0]", "[9]", "\\\\times", "\\\\div", "\\\\frac", "[.]", "\\\\%", "[=]", "[(]"]) expect(flat(0)).toContain(k);
    for (const k of ["\\\\sqrt", "\\\\pm", "\\\\le", "\\\\ge", "\\\\ne", "\\\\left|", "#@_{#?}", "#@^{#?}"]) expect(flat(1)).toContain(k);
    for (const k of ["\\\\sin", "\\\\sec", "\\\\arcsin", "\\\\log_{#?}", "\\\\ln", "e^{#?}", "\\\\pi", "f(#?)", "g(#?)"]) expect(flat(2)).toContain(k);
    for (const k of ["\\\\frac{d}{dx}", "\\\\partial", "\\\\int", "\\\\lim", "\\\\sum", "\\\\prod", "\\\\infty", "f'", "f''", "\\\\Delta"]) expect(flat(3)).toContain(k);
    for (const k of ["#@^{#?^{#?}}", "pmatrix", "!", "\\\\binom", "\\\\theta", "\\\\phi", "\\\\lambda", "\\\\in", "\\\\cup", "\\\\cap", "\\\\to"]) expect(flat(4)).toContain(k);
  });
});

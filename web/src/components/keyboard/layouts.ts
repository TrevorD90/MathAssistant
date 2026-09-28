// Custom MathLive virtual keyboard (spec §5): Basic, Algebra, Functions,
// Calculus, Advanced. `#@` = current selection, `#?` = empty placeholder.
// Physical-keyboard input works alongside (MathLive handles it natively).

import type { VirtualKeyboardLayout } from "mathlive";

type Key = string | Record<string, unknown>;

// Navigation/editing row shared by every tab.
const NAV: Key[] = ["[left]", "[right]", "[backspace]", { label: "⌫ all", command: ["deleteAll"], class: "small action" }];

export const BASIC: VirtualKeyboardLayout = {
  id: "ma-basic",
  label: "Basic",
  tooltip: "Numbers and arithmetic",
  rows: [
    ["[7]", "[8]", "[9]", { latex: "\\div", insert: "\\div" }, { latex: "\\frac{#@}{#?}", label: "a/b" }, "[(]", "[)]"],
    ["[4]", "[5]", "[6]", { latex: "\\times", insert: "\\times" }, { latex: "\\%", insert: "\\%" }, "[=]", { latex: "-", label: "(−)", insert: "-", tooltip: "negative" }],
    ["[1]", "[2]", "[3]", "[-]", "[.]", "[,]", "[separator]"],
    ["[0]", "[separator]", "[separator]", "[+]", ...NAV],
  ] as never,
};

export const ALGEBRA: VirtualKeyboardLayout = {
  id: "ma-algebra",
  label: "Algebra",
  tooltip: "Variables, powers, roots, inequalities",
  rows: [
    ["x", "y", "z", "a", "b", "n", { latex: "#@^{#?}", label: "xⁿ" }, { latex: "#@_{#?}", label: "xₙ" }],
    [{ latex: "\\sqrt{#0}", label: "√" }, { latex: "\\sqrt[#?]{#0}", label: "ⁿ√" }, { latex: "\\left|#0\\right|", label: "|x|" }, "\\pm", "(", ")", "[", "]"],
    ["<", ">", "\\le", "\\ge", "\\ne", "=", "+", "-"],
    ["\\times", "\\div", { latex: "\\frac{#@}{#?}", label: "a/b" }, ...NAV],
  ] as never,
};

export const FUNCTIONS: VirtualKeyboardLayout = {
  id: "ma-functions",
  label: "Functions",
  tooltip: "Trig, logs, constants",
  rows: [
    ["\\sin", "\\cos", "\\tan", "\\sec", "\\csc", "\\cot", "\\pi", "e"],
    ["\\arcsin", "\\arccos", "\\arctan", "\\log", { latex: "\\log_{#?}", label: "logₙ" }, "\\ln", { latex: "e^{#?}", label: "eˣ" }, "\\theta"],
    [{ latex: "f(#?)", label: "f(x)" }, { latex: "g(#?)", label: "g(x)" }, "x", "(", ")", { latex: "#@^{#?}", label: "xⁿ" }, { latex: "\\frac{#@}{#?}", label: "a/b" }, "="],
    ["[separator]", ...NAV],
  ] as never,
};

export const CALCULUS: VirtualKeyboardLayout = {
  id: "ma-calculus",
  label: "Calculus",
  tooltip: "Derivatives, integrals, limits, sums",
  rows: [
    [{ latex: "\\frac{d}{dx}", label: "d/dx" }, { latex: "\\frac{d^{#?}}{dx^{#?}}", label: "dⁿ/dxⁿ" }, { latex: "\\frac{\\partial}{\\partial x}", label: "∂/∂x" }, "f'", "f''", "\\Delta", "\\infty"],
    [{ latex: "\\int #? \\,dx", label: "∫" }, { latex: "\\int_{#?}^{#?} #? \\,dx", label: "∫ₐᵇ" }, { latex: "\\lim_{x\\to #?}", label: "lim" }, { latex: "\\sum_{#?}^{#?}", label: "Σ" }, { latex: "\\prod_{#?}^{#?}", label: "Π" }, "dx", "\\to"],
    ["x", "(", ")", { latex: "#@^{#?}", label: "xⁿ" }, { latex: "\\frac{#@}{#?}", label: "a/b" }, "\\sin", "\\cos"],
    ["[separator]", ...NAV],
  ] as never,
};

export const ADVANCED: VirtualKeyboardLayout = {
  id: "ma-advanced",
  label: "Advanced",
  tooltip: "Nested exponents, matrices, combinatorics, sets, Greek",
  rows: [
    // Nested exponents: press xⁿ again inside an exponent, or use x^(y^z) directly.
    [{ latex: "#@^{#?^{#?}}", label: "x^y^z" }, { latex: "#@^{#?}", label: "xⁿ" }, "!", { latex: "\\binom{#?}{#?}", label: "ⁿCᵣ" }, { latex: "\\begin{pmatrix}#? & #?\\\\ #? & #?\\end{pmatrix}", label: "[2×2]" }, { latex: "\\begin{pmatrix}#?\\\\ #?\\end{pmatrix}", label: "vec" }],
    ["\\theta", "\\phi", "\\alpha", "\\beta", "\\lambda", "\\mu", "\\sigma"],
    ["\\in", "\\cup", "\\cap", "\\to", "(", ")", ","],
    ["[separator]", ...NAV],
  ] as never,
};

export const LAYOUTS = [BASIC, ALGEBRA, FUNCTIONS, CALCULUS, ADVANCED];

"""LaTeX -> SymPy conversion.

Two parsers, chosen by content:

* **Translator** (default): converts a restricted LaTeX subset into a SymPy
  expression string, then runs `parse_expr` with implicit multiplication.
  Used for anything without calculus operators — i.e. almost every learner
  answer. It reads `2\\sin(x^2)x` as `2*sin(x**2)*x`, which is what a learner
  means.
* **SymPy's `parse_latex(backend="lark")`**: used when the input contains
  calculus / big operators (\\int, \\lim, \\sum, d/dx, ...). It is
  argument-greedy (`\\sin(x^2)x` -> `sin(x**3)`), which is why it is NOT the
  default for answers.

Both paths map `e` -> Euler's number and `\\pi` -> pi.

Safety: `parse_expr` uses `eval` internally. The translator output is checked
against a character whitelist and a name whitelist before it is evaluated, so
only arithmetic, known functions, and single-letter symbols can get through.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import sympy as sp
from sympy.parsing.sympy_parser import (
    convert_xor,
    implicit_multiplication_application,
    parse_expr,
    standard_transformations,
)


class LatexParseError(ValueError):
    """Raised when LaTeX can't be converted to SymPy."""


# Markers that route input to SymPy's own LaTeX parser.
_CALCULUS_MARKERS = (
    r"\int", r"\iint", r"\oint", r"\lim", r"\sum", r"\prod",
    r"\frac{d", r"\dfrac{d", r"\frac{\mathrm{d}", r"\partial", r"\binom",
)

# LaTeX command -> SymPy function name (translator path).
_FUNCTIONS = {
    "sin": "sin", "cos": "cos", "tan": "tan",
    "sec": "sec", "csc": "csc", "cot": "cot",
    "arcsin": "asin", "arccos": "acos", "arctan": "atan",
    "sinh": "sinh", "cosh": "cosh", "tanh": "tanh",
    "ln": "log", "log": "log", "exp": "exp",
}

_GREEK = {
    "alpha", "beta", "gamma", "delta", "epsilon", "theta", "lambda", "mu",
    "sigma", "phi", "varphi", "rho", "omega", "tau", "Delta",
}

# Names the translated string may contain. Anything else is rejected.
_ALLOWED_NAMES = (
    set(_FUNCTIONS.values())
    | {"sqrt", "root", "Abs", "factorial", "pi", "E", "oo", "I"}
    | (_GREEK - {"lambda"})
    | {"lamda"}
)

_ALLOWED_CHARS = re.compile(r"^[0-9A-Za-z_+\-*/().,= ]*$")

_TRANSFORMS = standard_transformations + (implicit_multiplication_application, convert_xor)


@dataclass(frozen=True)
class Parsed:
    """Result of parsing one LaTeX string.

    `value` is the evaluated SymPy object (Expr, Eq, or a tuple of these for
    comma-separated lists). `raw` is the same input parsed with
    `evaluate=False` when available — used to judge *form* (e.g. whether a
    learner typed `5\\times5` instead of `25`).
    """

    value: object
    raw: object | None
    latex: str


# ---------------------------------------------------------------- normalizing

def normalize(latex: str) -> str:
    """Strip presentation-only LaTeX that doesn't change meaning."""
    s = latex.strip()
    s = s.strip("$")
    if s.startswith(r"\(") and s.endswith(r"\)"):
        s = s[2:-2]
    if s.startswith(r"\[") and s.endswith(r"\]"):
        s = s[2:-2]
    # MathLive emits \placeholder{} for empty slots; treat as parse failure later.
    s = re.sub(r"\\(left|right|bigl|bigr|Bigl|Bigr|big|Big|displaystyle|textstyle)\b", "", s)
    s = re.sub(r"\\[,;:! ]", " ", s)
    s = s.replace(r"\mathrm{d}", "d").replace(r"\,", " ")
    s = re.sub(r"\\operatorname\{(\w+)\}", r"\\\1", s)
    s = re.sub(r"\\mathrm\{(\w+)\}", r"\1", s)
    s = re.sub(r"\\text\{\s*\}", "", s)
    s = s.replace(r"\lbrace", "{").replace(r"\rbrace", "}")
    s = s.replace(r"\lvert", "|").replace(r"\rvert", "|")
    s = s.replace("−", "-").replace("×", r"\times").replace("÷", r"\div")
    return s.strip()


def _uses_calculus(s: str) -> bool:
    return any(m in s for m in _CALCULUS_MARKERS)


# ------------------------------------------------------------- translator

def _read_group(s: str, i: int) -> tuple[str, int]:
    """Read a {...} group (or a single char/command) starting at s[i].

    Returns (inner_text, index_after_group).
    """
    while i < len(s) and s[i] == " ":
        i += 1
    if i >= len(s):
        raise LatexParseError("unexpected end of input")
    if s[i] == "{":
        depth = 0
        for j in range(i, len(s)):
            if s[j] == "{":
                depth += 1
            elif s[j] == "}":
                depth -= 1
                if depth == 0:
                    return s[i + 1 : j], j + 1
        raise LatexParseError("unbalanced braces")
    if s[i] == "\\":
        m = re.match(r"\\[A-Za-z]+", s[i:])
        if m:
            return m.group(0), i + len(m.group(0))
    return s[i], i + 1


def _translate(s: str) -> str:
    """Translate restricted LaTeX into a SymPy-parsable string."""
    out: list[str] = []
    i = 0
    abs_open = False  # toggles on each bare '|'
    while i < len(s):
        c = s[i]
        if c == "\\":
            m = re.match(r"\\([A-Za-z]+|.)", s[i:])
            cmd = m.group(1)
            i += len(m.group(0))
            if cmd in ("frac", "dfrac", "tfrac"):
                num, i = _read_group(s, i)
                den, i = _read_group(s, i)
                out.append(f"(({_translate(num)})/({_translate(den)}))")
            elif cmd == "sqrt":
                if i < len(s) and s[i] == "[":
                    j = s.index("]", i)
                    n = s[i + 1 : j]
                    i = j + 1
                    arg, i = _read_group(s, i)
                    out.append(f"root(({_translate(arg)}),({_translate(n)}))")
                else:
                    arg, i = _read_group(s, i)
                    out.append(f"sqrt({_translate(arg)})")
            elif cmd in ("cdot", "times", "ast"):
                out.append("*")
            elif cmd == "div":
                out.append("/")
            elif cmd == "pi":
                out.append(" pi ")
            elif cmd == "infty":
                out.append(" oo ")
            elif cmd == "%":
                out.append("/100")
            elif cmd in ("exponentialE",):
                out.append(" E ")
            elif cmd in _FUNCTIONS:
                # \log_{b} x -> log(x, b) is handled by emitting a marker the
                # post-pass can't express simply, so we translate log_b as
                # log(...)/log(b) around the next group/atom.
                if cmd == "log" and i < len(s) and s[i] == "_":
                    base, i = _read_group(s, i + 1)
                    arg, i = _read_function_arg(s, i)
                    out.append(f"(log({_translate(arg)})/log({_translate(base)}))")
                else:
                    # \sin^{2}x style power on the function
                    power = None
                    if i < len(s) and s[i] == "^":
                        power, i = _read_group(s, i + 1)
                    arg, i = _read_function_arg(s, i)
                    call = f"{_FUNCTIONS[cmd]}({_translate(arg)})"
                    out.append(f"({call})**({_translate(power)})" if power else call)
            elif cmd in _GREEK:
                # "lambda" is a Python keyword; SymPy spells the symbol "lamda".
                out.append(f" {'lamda' if cmd == 'lambda' else cmd} ")
            elif cmd in ("{", "}"):
                out.append("(" if cmd == "{" else ")")
            elif cmd == "placeholder":
                raise LatexParseError("empty placeholder")
            else:
                raise LatexParseError(f"unsupported command \\{cmd}")
        elif c == "^":
            grp, i = _read_group(s, i + 1)
            out.append(f"**({_translate(grp)})")
        elif c == "{":
            grp, i = _read_group(s, i)
            out.append(f"({_translate(grp)})")
        elif c == "|":
            out.append(")" if abs_open else "Abs(")
            abs_open = not abs_open
            i += 1
        elif c == "!":
            # factorial applies to the previous atom: wrap it.
            prev = out.pop() if out else ""
            out.append(f"factorial({prev})")
            i += 1
        elif c == "[":
            out.append("(")
            i += 1
        elif c == "]":
            out.append(")")
            i += 1
        elif c.isalpha():
            # Learner letters are always single-letter symbols. Spacing them
            # out means the only multi-letter names in the output are ones
            # this translator emitted itself (checked by _check_safe).
            out.append(f" {c} ")
            i += 1
        else:
            out.append(c)
            i += 1
    if abs_open:
        raise LatexParseError("unbalanced |")
    return "".join(out)


def _read_function_arg(s: str, i: int) -> tuple[str, int]:
    """Argument of \\sin etc.: a (...) group, a {...} group, or one atom."""
    while i < len(s) and s[i] == " ":
        i += 1
    if i < len(s) and s[i] == "(":
        depth = 0
        for j in range(i, len(s)):
            if s[j] == "(":
                depth += 1
            elif s[j] == ")":
                depth -= 1
                if depth == 0:
                    return s[i + 1 : j], j + 1
        raise LatexParseError("unbalanced parentheses")
    if i < len(s) and s[i] == "{":
        return _read_group(s, i)
    # bare atom: digits, or a letter (optionally with ^power), e.g. \sin x
    m = re.match(r"(\d+(?:\.\d+)?|[A-Za-z](?:\^\{[^}]*\}|\^\w)?|\\[A-Za-z]+)", s[i:])
    if not m:
        raise LatexParseError("missing function argument")
    return m.group(0), i + len(m.group(0))


def _local_dict() -> dict:
    d: dict = {name: sp.Symbol(name) for name in _GREEK if name != "lambda"}
    d["lamda"] = sp.Symbol("lambda")
    d.update({"e": sp.E, "E": sp.E, "pi": sp.pi, "oo": sp.oo, "root": sp.root})
    return d


def _check_safe(expr_str: str) -> None:
    if not _ALLOWED_CHARS.match(expr_str):
        raise LatexParseError("unsupported characters")
    for name in re.findall(r"[A-Za-z_][A-Za-z_0-9]*", expr_str):
        # Single letters become symbols; multi-letter names must be ones the
        # translator emits (functions, constants, greek letters).
        if len(name) > 1 and name not in _ALLOWED_NAMES:
            raise LatexParseError(f"unsupported name {name}")
    if "__" in expr_str or re.search(r"\.\s*[A-Za-z_]", expr_str):
        raise LatexParseError("unsupported token")


def _parse_translated(expr_str: str, evaluate: bool) -> object:
    _check_safe(expr_str)
    if "=" in expr_str:
        parts = expr_str.split("=")
        if len(parts) != 2 or not parts[0].strip() or not parts[1].strip():
            raise LatexParseError("malformed equation")
        lhs = _parse_translated(parts[0], evaluate)
        rhs = _parse_translated(parts[1], evaluate)
        return sp.Eq(lhs, rhs, evaluate=False)
    try:
        return parse_expr(
            expr_str,
            local_dict=_local_dict(),
            transformations=_TRANSFORMS,
            evaluate=evaluate,
        )
    except Exception as exc:  # SymPy raises many types (SyntaxError, TokenError, TypeError...)
        raise LatexParseError(f"could not parse: {exc}") from exc


# ------------------------------------------------------------- public API

def _fix_constants(expr: object) -> object:
    """Map a free symbol `e` to Euler's number (SymPy's LaTeX parser leaves it a symbol)."""
    if isinstance(expr, sp.Basic):
        e_sym = sp.Symbol("e")
        if e_sym in expr.free_symbols:
            expr = expr.subs(e_sym, sp.E)
    return expr


def _parse_calculus(s: str) -> Parsed:
    from sympy.parsing.latex import parse_latex  # imported lazily; loads the Lark grammar

    try:
        value = parse_latex(s, backend="lark")
    except Exception as exc:
        raise LatexParseError(f"could not parse: {exc}") from exc
    value = _fix_constants(value)
    return Parsed(value=value, raw=value, latex=s)


def parse(latex: str) -> Parsed:
    """Parse one LaTeX math string. Raises LatexParseError."""
    s = normalize(latex)
    if not s:
        raise LatexParseError("empty input")
    if r"\placeholder" in s:
        raise LatexParseError("empty placeholder")
    if _uses_calculus(s):
        return _parse_calculus(s)

    # Comma-separated list, e.g. "x=2, x=3" or "2, 3" (solution sets).
    # Only split on top-level commas and only if every piece parses.
    pieces = _split_top_level(s, ",")
    if len(pieces) > 1:
        parsed = [parse(p) for p in pieces]
        return Parsed(
            value=tuple(p.value for p in parsed),
            raw=tuple(p.raw for p in parsed),
            latex=s,
        )

    translated = _translate(s)
    value = _parse_translated(translated, evaluate=True)
    try:
        raw = _parse_translated(translated, evaluate=False)
    except LatexParseError:
        raw = None
    return Parsed(value=value, raw=raw, latex=s)


def _split_top_level(s: str, sep: str) -> list[str]:
    parts, depth, cur = [], 0, []
    for ch in s:
        if ch in "({[":
            depth += 1
        elif ch in ")}]":
            depth -= 1
        if ch == sep and depth == 0:
            parts.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    parts.append("".join(cur))
    return [p.strip() for p in parts if p.strip()]


def try_parse(latex: str) -> Parsed | None:
    """Parse, returning None instead of raising."""
    try:
        return parse(latex)
    except (LatexParseError, RecursionError, ValueError, TypeError):
        return None


# Public alias: split on a separator outside brackets (used for "a = b = c" chains).
split_top_level = _split_top_level

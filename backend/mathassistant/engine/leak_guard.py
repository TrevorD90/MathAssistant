"""Answer-leak guardrail (spec §7.3, N1).

Protects against the AI *accidentally* revealing the final answer, or the
current step's result, before the learner has produced it. Runs on every piece
of tutor text and every display payload before anything is shown.

How a leak is detected, per target value:

* **Numbers** — literal numbers in the text (`25`, `0.875`, `7/8`,
  `\\frac{7}{8}`) and, for small integers, number words ("twenty-five").
  If the target number also appears in the problem itself (e.g. `2x+3=7`,
  answer 2), a bare "2" is unavoidable in normal talk, so only *assertion*
  patterns count: `x = 2`, `is 2`, `equals 2`.
* **Expressions** — math segments in the text (inside `$...$`, `\\(...\\)`,
  or plain-text runs like `2x cos(x^2)`) are parsed and compared to the target
  with SymPy equivalence. Segments that still contain an unevaluated operator
  (d/dx, ∫, lim) are the problem restated, not a leak, and are skipped.
* **Unparseable targets** (word problems where SymPy had no answer) fall back
  to a normalized substring match on the model's own stated answer.

Values the learner has already produced ("revealed") are never flagged.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

import sympy as sp

from .answer_check import _is_reduced_plain_number, equivalent, normalize_value, numbers_equal
from .latex_parse import normalize, try_parse

log = logging.getLogger(__name__)


@dataclass
class Target:
    """A value that must not be shown yet."""

    label: str                    # "final" or "step"
    value: object | None          # SymPy Expr (None -> text-only target)
    latex: str                    # canonical LaTeX (also used for text fallback)
    variable: str | None = None   # for "x = 2" style assertions


@dataclass
class LeakHit:
    label: str
    reason: str
    snippet: str


@dataclass
class GuardContext:
    targets: list[Target]
    problem_latex: str
    revealed_latex: list[str] = field(default_factory=list)  # things the learner already said


# ------------------------------------------------------------ number words

_ONES = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine",
         "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen",
         "seventeen", "eighteen", "nineteen"]
_TENS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]


def number_words(n: int) -> list[str]:
    """English spellings of 0 <= n < 1000 (with hyphen and space variants)."""
    if n < 0 or n >= 1000:
        return []
    if n < 20:
        return [_ONES[n]]
    if n < 100:
        t, o = divmod(n, 10)
        if o == 0:
            return [_TENS[t]]
        return [f"{_TENS[t]}-{_ONES[o]}", f"{_TENS[t]} {_ONES[o]}"]
    h, rest = divmod(n, 100)
    head = f"{_ONES[h]} hundred"
    if rest == 0:
        return [head]
    return [f"{head} and {w}" for w in number_words(rest)] + [f"{head} {w}" for w in number_words(rest)]


# ------------------------------------------------------------ extraction

_NUM_RE = re.compile(r"(?<![\w.])-?\d+(?:\.\d+)?(?:\s*/\s*\d+)?(?![\w.]*\d)")
_FRAC_RE = re.compile(r"\\[dt]?frac\{\s*(-?\d+)\s*\}\{\s*(\d+)\s*\}")
_LATEX_SEG_RE = re.compile(r"\$\$(.+?)\$\$|\$(.+?)\$|\\\((.+?)\\\)|\\\[(.+?)\\\]", re.S)

# Plain-text math runs: digits, single letters, operators, brackets, function names.
_FUNC_WORDS = ("arcsin", "arccos", "arctan", "sin", "cos", "tan", "sec", "csc", "cot",
               "ln", "log", "sqrt", "exp", "pi")
_MATH_CHARS_RE = re.compile(r"[0-9A-Za-z()+\-*/^=.·×÷²³ ]+")
_ALPHA_RUN_RE = re.compile(r"[A-Za-z]+")


def _plain_runs(text: str) -> list[str]:
    """Maximal plain-text math runs. English words (2+ letters, not a function
    name) act as separators, so "Multiply cos(x^2) by 2x" yields "cos(x^2)" and "2x"."""
    runs: list[str] = []
    for m in _MATH_CHARS_RE.finditer(text):
        chunk = _ALPHA_RUN_RE.sub(
            lambda w: w.group(0) if len(w.group(0)) == 1 or w.group(0) in _FUNC_WORDS else "|",
            m.group(0),
        )
        for piece in chunk.split("|"):
            piece = piece.strip().rstrip(".").strip()
            if piece:
                runs.append(piece)
    return runs


def _plain_to_latex(run: str) -> str:
    s = run.replace("·", "*").replace("×", "*").replace("÷", "/")
    s = s.replace("²", "^2").replace("³", "^3")
    for fw in _FUNC_WORDS:
        s = re.sub(rf"\b{fw}\b", rf"\\{fw}", s)
    return s.replace("*", r"\cdot ")


def extract_numbers(text: str) -> list[tuple[sp.Rational | sp.Float, str]]:
    """All literal numbers (ints, decimals, a/b, \\frac{a}{b}) with their source snippet."""
    found: list[tuple[object, str]] = []
    for m in _FRAC_RE.finditer(text):
        found.append((sp.Rational(int(m.group(1)), int(m.group(2))), m.group(0)))
    stripped = _FRAC_RE.sub(" ", text)
    for m in _NUM_RE.finditer(stripped):
        tok = m.group(0).replace(" ", "")
        try:
            if "/" in tok:
                a, b = tok.split("/")
                if int(b) == 0:
                    continue
                val = sp.Rational(int(a), int(b))
            elif "." in tok:
                val = sp.Float(tok)
            else:
                val = sp.Integer(int(tok))
        except (ValueError, ZeroDivisionError):
            continue
        found.append((val, tok))
    return found


def extract_segments(text: str) -> list[str]:
    """Candidate math segments to parse (LaTeX-delimited and plain-text runs)."""
    segs: list[str] = []
    for m in _LATEX_SEG_RE.finditer(text):
        seg = next(g for g in m.groups() if g is not None)
        segs.append(seg)
    no_latex = _LATEX_SEG_RE.sub(" ", text)
    for run in _plain_runs(no_latex):
        if re.search(r"[a-zA-Z]", run) and re.search(r"[\d(^]", run):
            segs.append(_plain_to_latex(run))
    return segs


def _sides(seg: str) -> list[str]:
    """Split a segment on '=' (and common relation words) so each side is checked."""
    parts = re.split(r"=|\\approx|\\equiv", seg)
    return [p for p in (x.strip() for x in parts) if p]


def _is_operator_form(obj: object) -> bool:
    return isinstance(obj, sp.Basic) and obj.has(sp.Derivative, sp.Integral, sp.Limit, sp.Sum)


# ------------------------------------------------------------ scanning

def _problem_numbers(problem_latex: str) -> list[object]:
    return [v for v, _ in extract_numbers(normalize(problem_latex))]


def _revealed_values(revealed: list[str]) -> list[object]:
    """Values the learner has produced themselves.

    A number only counts once the learner has written it as a number:
    typing `152 - 3(2)` does not reveal 146 (the tutor still mustn't finish
    that arithmetic for them), but typing `146` does.
    """
    vals: list[object] = []
    for r in revealed:
        p = try_parse(r)
        if p is None:
            continue
        v, raw = p.value, p.raw
        items = v if isinstance(v, tuple) else (v,)
        raws = raw if isinstance(raw, tuple) else (raw,) * len(items)
        for it, rw in zip(items, raws):
            sides = [(it.lhs, getattr(rw, "lhs", None)), (it.rhs, getattr(rw, "rhs", None))]                 if isinstance(it, sp.Equality) else [(it, rw)]
            for val, val_raw in sides:
                if isinstance(val, sp.Basic) and not val.free_symbols and not _is_reduced_plain_number(val_raw):
                    continue
                vals.append(val)
    return vals


def _was_revealed(value: object, revealed_vals: list[object]) -> bool:
    return any(equivalent(value, r) for r in revealed_vals if isinstance(r, sp.Basic))


def _assertion_patterns(num_text: list[str], variable: str | None) -> list[re.Pattern]:
    alts = "|".join(re.escape(t) for t in num_text)
    subj = rf"(?:\b{re.escape(variable)}\s*|)" if variable else ""
    # Lookahead: the number must end there ("2." at a sentence end is fine; "2.5",
    # "2/3", and "2x" are different values).
    end = r"(?![\dA-Za-z]|\.\d|/\d)"
    return [
        re.compile(rf"{subj}=\s*\$?\s*(?:{alts}){end}"),
        re.compile(rf"\b(?:is|equals|makes|gives|get|becomes)\s+\$?\s*(?:{alts}){end}", re.I),
    ]


def _number_text_forms(value: sp.Expr) -> list[str]:
    forms: list[str] = []
    if isinstance(value, sp.Integer):
        forms.append(str(int(value)))
    elif isinstance(value, sp.Rational):
        forms += [f"{value.p}/{value.q}", rf"\frac{{{value.p}}}{{{value.q}}}"]
    try:
        f = float(value)
        if f == int(f):
            forms.append(str(int(f)))
        forms.append(f"{f:g}")
    except (TypeError, ValueError):
        pass
    return list(dict.fromkeys(forms))


def _scan_number_target(text: str, t: Target, problem_nums: list[object]) -> LeakHit | None:
    value = t.value
    in_problem = any(numbers_equal(value, pn) for pn in problem_nums)
    if not in_problem:
        for num, snippet in extract_numbers(text):
            if numbers_equal(num, value):
                return LeakHit(t.label, "number", snippet)
        if isinstance(value, sp.Integer) and abs(int(value)) < 1000:
            low = text.lower()
            for w in number_words(abs(int(value))):
                if re.search(rf"(?<![a-z-]){re.escape(w)}(?![a-z-])", low):
                    # "one"/"two" etc. are too common as plain words; only flag
                    # them in an assertion ("the answer is two").
                    if int(value) < 11 and not re.search(
                        rf"\b(?:is|equals|makes|gives|get|=)\s+{re.escape(w)}\b", low
                    ):
                        continue
                    return LeakHit(t.label, "number-word", w)
        return None
    # Target number also appears in the problem: only assertions count.
    for pat in _assertion_patterns(_number_text_forms(value), t.variable):
        m = pat.search(text)
        if m:
            return LeakHit(t.label, "assertion", m.group(0))
    return None


def _scan_expression_target(text: str, t: Target, revealed_vals: list[object]) -> LeakHit | None:
    for seg in extract_segments(text):
        for side in _sides(seg):
            p = try_parse(side)
            if p is None or _is_operator_form(p.value) or isinstance(p.value, tuple):
                continue
            v = p.value
            if not isinstance(v, sp.Basic) or isinstance(v, sp.Equality):
                continue
            if not v.free_symbols:
                continue  # numbers are handled by the number scan
            if equivalent(v, t.value) and not _was_revealed(v, revealed_vals):
                return LeakHit(t.label, "expression", side)
    # Cheap textual backstop on the canonical LaTeX.
    canon = re.sub(r"\s+", "", t.latex)
    if len(canon) >= 3 and canon in re.sub(r"\s+", "", text):
        return LeakHit(t.label, "latex-text", t.latex)
    return None


def _squash(s: str) -> str:
    """Lowercase, unwrap \\text{...}, drop spaces/$/braces/backslashes/punctuation."""
    s = re.sub(r"\\(?:text|mathrm|textbf|mathbf)\{([^}]*)\}", r"\1", s)
    return re.sub(r"[\s$\\{}.,;:!?]", "", s.lower())


def _scan_text_target(text: str, t: Target) -> LeakHit | None:
    needle = _squash(t.latex)
    hay = _squash(text)
    if len(needle) >= 2 and needle in hay:
        return LeakHit(t.label, "text", t.latex)
    return None


def scan(text: str, ctx: GuardContext) -> LeakHit | None:
    """Return the first leak found in `text`, or None if it is safe to show."""
    if not text:
        return None
    problem_nums = _problem_numbers(ctx.problem_latex)
    revealed_vals = _revealed_values(ctx.revealed_latex)
    for t in ctx.targets:
        values = t.value if isinstance(t.value, (list, tuple)) else [t.value]
        for v in values:
            sub = Target(t.label, v, t.latex if len(values) == 1 else sp.latex(v) if v is not None else t.latex,
                         t.variable)
            if v is None:
                hit = _scan_text_target(text, sub)
            elif _was_revealed(v, revealed_vals):
                continue
            elif isinstance(v, sp.Basic) and not v.free_symbols:
                hit = _scan_number_target(text, sub, problem_nums)
            else:
                hit = _scan_expression_target(text, sub, revealed_vals)
            if hit:
                log.info("leak guard hit: label=%s reason=%s", hit.label, hit.reason)
                return hit
    return None


def scan_all(texts: list[str], ctx: GuardContext) -> LeakHit | None:
    for s in texts:
        hit = scan(s, ctx)
        if hit:
            return hit
    return None


# ------------------------------------------------------------ targets

def target_from_latex(label: str, latex: str | None, variable: str | None = None) -> Target | None:
    """Build a target from a LaTeX string (step result or model-stated answer)."""
    if not latex or not latex.strip():
        return None
    p = try_parse(latex)
    if p is None:
        return Target(label, None, latex, variable)
    v = p.value
    if isinstance(v, tuple):
        vals = []
        for item in v:
            if isinstance(item, sp.Equality) and isinstance(item.lhs, sp.Symbol):
                variable = variable or item.lhs.name
                vals.append(item.rhs)
            elif isinstance(item, sp.Basic):
                vals.append(item)
        return Target(label, vals or None, latex, variable)
    if isinstance(v, sp.Equality):
        if isinstance(v.lhs, sp.Symbol):
            return Target(label, v.rhs, latex, variable or v.lhs.name)
        nv = normalize_value(v)  # identities like "12^2 = 144" stand for 144
        if not isinstance(nv, sp.Equality):
            return Target(label, nv, latex, variable)
        return Target(label, None, latex, variable)
    if _is_operator_form(v):
        return Target(label, None, latex, variable)
    return Target(label, v, latex, variable)

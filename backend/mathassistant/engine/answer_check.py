"""Check learner answers with SymPy (spec §7.4, N8).

The model never decides whether math is correct when SymPy can. Verdicts:

* CORRECT        — equivalent to the expected value (and in an acceptable form)
* NOT_SIMPLIFIED — equivalent, but the learner restated the problem instead of
                   finishing it (e.g. typed `5\\times5` for 25, or `14/16`)
* INCORRECT      — parsed, not equivalent
* UNCHECKABLE    — no math to check (words), or the expected value isn't
                   parseable; the AI judges it conceptually inside the turn call
"""

from __future__ import annotations

import logging
import random
from enum import Enum

import sympy as sp

from .latex_parse import Parsed, try_parse
from .solver import Solution

log = logging.getLogger(__name__)

# Relative tolerance for "these are the same number" when both are exact-ish.
_EXACT_TOL = 1e-9


class Verdict(str, Enum):
    CORRECT = "correct"
    NOT_SIMPLIFIED = "not_simplified"
    INCORRECT = "incorrect"
    UNCHECKABLE = "uncheckable"


# ------------------------------------------------------------ equivalence

def _decimal_places(p: Parsed | None) -> int | None:
    """Number of decimal places the learner typed, if their answer is a decimal."""
    if p is None:
        return None
    text = p.latex.strip()
    if "." in text and text.replace(".", "", 1).lstrip("-").isdigit():
        return len(text.split(".", 1)[1])
    return None


def numbers_equal(a: sp.Expr, b: sp.Expr, decimals: int | None = None) -> bool:
    """Numeric comparison. `decimals` = places the learner typed (rounding tolerance)."""
    try:
        av, bv = complex(sp.N(a, 30)), complex(sp.N(b, 30))
    except (TypeError, ValueError):
        return False
    diff = abs(av - bv)
    if diff <= _EXACT_TOL * max(1.0, abs(bv)):
        return True
    # Rounded decimals: 0.33 for 1/3 passes; one decimal place is too coarse.
    if decimals is not None and decimals >= 2:
        return diff <= 0.5 * 10 ** (-decimals) + 1e-12
    return False


def expressions_equal(a: sp.Expr, b: sp.Expr) -> bool:
    """Symbolic equivalence: simplify(a-b)==0, then .equals(), then random probes."""
    try:
        if sp.simplify(a - b) == 0:
            return True
    except Exception:
        pass
    try:
        eq = a.equals(b)
        if eq is not None:
            return bool(eq)
    except Exception:
        pass
    # Numeric probing at random points as a last resort (both must agree everywhere probed).
    syms = sorted((a.free_symbols | b.free_symbols), key=lambda s: s.name)
    if not syms:
        return numbers_equal(a, b)
    rng = random.Random(1234)  # deterministic
    for _ in range(6):
        subs = {s: sp.Rational(rng.randint(3, 97), rng.randint(7, 41)) for s in syms}
        try:
            if not numbers_equal(a.subs(subs), b.subs(subs)):
                return False
        except Exception:
            return False
    return True


def equivalent(learner: object, expected: object, decimals: int | None = None) -> bool:
    if not isinstance(learner, sp.Basic) or not isinstance(expected, sp.Basic):
        return False
    if isinstance(learner, sp.Equality) or isinstance(expected, sp.Equality):
        return False
    if not learner.free_symbols and not expected.free_symbols:
        return numbers_equal(learner, expected, decimals)
    return expressions_equal(learner, expected)


# ------------------------------------------------------------ form checks

def _is_reduced_plain_number(raw: object) -> bool:
    """True if `raw` (parsed with evaluate=False) is a bare number or reduced fraction."""
    if raw is None:
        return True  # can't judge form; don't penalize
    if isinstance(raw, sp.Number):
        return True
    if isinstance(raw, sp.Mul):
        args = list(raw.args)
        # strip a leading -1 (negative numbers)
        args = [a for a in args if a != -1]
        if len(args) == 1:
            return _is_reduced_plain_number(args[0])
        if len(args) == 2:
            nums = [a for a in args if isinstance(a, sp.Integer)]
            dens = [a for a in args if isinstance(a, sp.Pow) and a.exp == -1 and isinstance(a.base, sp.Integer)]
            if len(nums) == 1 and len(dens) == 1:
                return sp.gcd(nums[0], dens[0].base) == 1
    if isinstance(raw, sp.Pow) and raw.exp == -1 and isinstance(raw.base, sp.Integer):
        return True  # 1/n
    return False


def _restates_problem(raw: object, problem_expr: object) -> bool:
    """Learner typed the problem back (or left an unevaluated operator in)."""
    if raw is None:
        return False
    if isinstance(raw, sp.Basic) and raw.has(sp.Derivative, sp.Integral, sp.Limit):
        return True
    if problem_expr is not None and isinstance(raw, sp.Basic) and isinstance(problem_expr, sp.Basic):
        try:
            return sp.srepr(raw) == sp.srepr(problem_expr)
        except Exception:
            return False
    return False


# ------------------------------------------------------------ public API

def _strip_var_eq(value: object, var: str | None) -> object:
    """`x = 2` -> 2 when the lhs is the solved variable (or any lone symbol)."""
    if isinstance(value, sp.Equality):
        if isinstance(value.lhs, sp.Symbol) and (var is None or value.lhs.name == var):
            return value.rhs
        if isinstance(value.rhs, sp.Symbol) and (var is None or value.rhs.name == var):
            return value.lhs
    return value


def normalize_value(value: object) -> object:
    """The value an equation-shaped result stands for.

    Plans (and learners) often write results as equations: `u = x^2`,
    `12^2 = 144`, `8 + 144 - 3x = 152 - 3x`. The value to compare is the
    right-hand side when the left side is a lone symbol or the equation is an
    identity. A genuine equation (`2x = 4`) is returned unchanged.
    """
    if isinstance(value, sp.Equality):
        if isinstance(value.lhs, sp.Symbol):
            return value.rhs
        try:
            if sp.simplify(value.lhs - value.rhs) == 0:
                return value.rhs
        except Exception:
            pass
    return value


def check_final(learner_latex: str, solution: Solution) -> Verdict:
    """Check a learner's final answer against the SymPy-computed solution."""
    if solution.kind == "none":
        return Verdict.UNCHECKABLE
    p = try_parse(learner_latex)
    if p is None:
        return Verdict.UNCHECKABLE
    decimals = _decimal_places(p)

    if solution.kind == "solutions":
        given = p.value if isinstance(p.value, tuple) else (p.value,)
        given = [_strip_var_eq(g, solution.variable) for g in given]
        expected = list(solution.value)
        if len(given) != len(expected):
            # Allow a single correct value only if the solution set has one element.
            return Verdict.INCORRECT
        remaining = list(expected)
        for g in given:
            match = next((e for e in remaining if equivalent(g, e, decimals)), None)
            if match is None:
                return Verdict.INCORRECT
            remaining.remove(match)
        return Verdict.CORRECT

    # "152 - 6 = 146" (a true identity) counts as stating 146.
    value = normalize_value(_strip_var_eq(p.value, None))
    raw = normalize_value(_strip_var_eq(p.raw, None))
    if isinstance(value, tuple):
        return Verdict.INCORRECT

    if solution.kind == "antiderivative":
        var = sp.Symbol(solution.variable or "x")
        # Drop a "+ C" constant of integration if the learner wrote one.
        if isinstance(value, sp.Basic):
            consts = [s for s in value.free_symbols if s.name in ("C", "c", "K") and s != var]
            value = value.subs({c: 0 for c in consts})
        if not isinstance(value, sp.Basic) or _restates_problem(raw, solution.problem_expr):
            return Verdict.NOT_SIMPLIFIED if isinstance(value, sp.Basic) else Verdict.INCORRECT
        try:
            ok = sp.simplify(sp.diff(value - solution.value, var)) == 0
        except Exception:
            ok = False
        return Verdict.CORRECT if ok else Verdict.INCORRECT

    if not equivalent(value, solution.value, decimals):
        return Verdict.INCORRECT
    if solution.kind == "number":
        if solution.value.is_Rational and not _is_reduced_plain_number(raw):
            return Verdict.NOT_SIMPLIFIED
    if _restates_problem(raw, solution.problem_expr):
        return Verdict.NOT_SIMPLIFIED
    return Verdict.CORRECT


def check_step(learner_latex: str, expected_latex: str | None) -> Verdict:
    """Check a learner's answer to one step against that step's planned result.

    Step results come from the model's plan; if they don't parse, or the
    learner wrote words, the step is judged conceptually by the AI.
    """
    if not expected_latex:
        return Verdict.UNCHECKABLE
    exp = try_parse(expected_latex)
    got = try_parse(learner_latex)
    if exp is None or got is None:
        return Verdict.UNCHECKABLE
    exp_v = normalize_value(exp.value)
    got_v = normalize_value(got.value)
    if isinstance(exp_v, tuple) or isinstance(got_v, tuple):
        exp_t = exp_v if isinstance(exp_v, tuple) else (exp_v,)
        got_t = got_v if isinstance(got_v, tuple) else (got_v,)
        exp_t = [normalize_value(e) for e in exp_t]
        got_t = [normalize_value(g) for g in got_t]
        if len(exp_t) != len(got_t):
            return Verdict.INCORRECT
        remaining = list(exp_t)
        for g in got_t:
            m = next((e for e in remaining if equivalent(g, e)), None)
            if m is None:
                return Verdict.INCORRECT
            remaining.remove(m)
        return Verdict.CORRECT
    if isinstance(exp_v, sp.Equality) or isinstance(got_v, sp.Equality):
        # Genuine equation-valued step (e.g. "2x = 4"): compare both sides
        # moved to one side, up to a constant factor.
        if isinstance(exp_v, sp.Equality) and isinstance(got_v, sp.Equality):
            a = exp_v.lhs - exp_v.rhs
            b = got_v.lhs - got_v.rhs
            try:
                ratio = sp.simplify(a / b)
                return Verdict.CORRECT if ratio.is_number and ratio != 0 else Verdict.INCORRECT
            except Exception:
                return Verdict.INCORRECT
        return Verdict.INCORRECT
    if not equivalent(got_v, exp_v, _decimal_places(got)):
        return Verdict.INCORRECT
    # If the plan's result is a plain number (e.g. "144", or "12^2 = 144"), the
    # learner must finish the arithmetic. If the plan's result is itself an
    # unevaluated expression (e.g. "152 - 3(2)"), any equivalent form counts.
    exp_raw = normalize_value(exp.raw)
    got_raw = normalize_value(_strip_var_eq(got.raw, None))
    if (isinstance(exp_v, sp.Rational) and _is_reduced_plain_number(exp_raw)
            and not _is_reduced_plain_number(got_raw)):
        return Verdict.NOT_SIMPLIFIED
    return Verdict.CORRECT

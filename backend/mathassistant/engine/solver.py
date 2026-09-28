"""Compute the final answer of a problem with SymPy (spec §7.1 step 1, N8).

The answer is computed once at intake and stored with the problem. If SymPy
can't handle the problem (word problems, proofs, unsupported notation) the
result is `Solution(kind="none")` and the leak guard falls back to the model's
own stated answer (§7.1).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import sympy as sp

from .latex_parse import try_parse

log = logging.getLogger(__name__)

# Answer kinds:
#   number         — a numeric value (5×5, 3/4+1/8, definite integral, limit)
#   expression     — a symbolic expression (derivative, simplify)
#   antiderivative — indefinite integral; equal up to a constant
#   solutions      — solution set of an equation, for `variable`
#   none           — SymPy couldn't solve; rely on the model's plan
KINDS = ("number", "expression", "antiderivative", "solutions", "none")


@dataclass
class Solution:
    kind: str
    # SymPy objects (not persisted directly — see to_record()).
    value: object = None                 # Expr, or list[Expr] for "solutions"
    variable: str | None = None          # for "solutions" / "antiderivative"
    problem_expr: object = None          # parsed problem (for "not simplified" checks)
    notes: list[str] = field(default_factory=list)

    def to_record(self) -> dict:
        """Serializable form (stored in SQLite as JSON)."""
        if self.kind == "none":
            return {"kind": "none"}
        if self.kind == "solutions":
            values = [sp.srepr(v) for v in self.value]
        else:
            values = [sp.srepr(self.value)]
        return {"kind": self.kind, "srepr": values, "variable": self.variable,
                "latex": self.latex()}

    def latex(self) -> str:
        if self.kind == "none":
            return ""
        if self.kind == "solutions":
            var = self.variable or "x"
            return ", ".join(f"{var} = {sp.latex(v)}" for v in self.value)
        if self.kind == "antiderivative":
            return f"{sp.latex(self.value)} + C"
        return sp.latex(self.value)

    @staticmethod
    def from_record(rec: dict | None) -> "Solution":
        if not rec or rec.get("kind") in (None, "none"):
            return Solution(kind="none")
        vals = [_from_srepr(s) for s in rec.get("srepr", [])]
        kind = rec["kind"]
        value = vals if kind == "solutions" else (vals[0] if vals else None)
        return Solution(kind=kind, value=value, variable=rec.get("variable"))


def _from_srepr(s: str) -> object:
    # srepr strings are written by this module into the local DB, never taken
    # from user input. sympify parses them in SymPy's namespace.
    return sp.sympify(s)


def _finalize(expr: sp.Expr) -> sp.Expr:
    """Simplify to a canonical form for display/comparison."""
    try:
        return sp.simplify(expr)
    except Exception:  # simplify can fail on exotic input; keep raw value
        return expr


def solve_latex(latex: str) -> Solution:
    parsed = try_parse(latex)
    if parsed is None:
        return Solution(kind="none", notes=["unparseable"])
    return solve_expr(parsed.value, problem_expr=parsed.raw)


def solve_expr(value: object, problem_expr: object = None) -> Solution:
    try:
        return _solve(value, problem_expr)
    except Exception as exc:  # never let the CAS crash intake
        log.info("solver fell back to none: %s", type(exc).__name__)
        return Solution(kind="none", notes=[f"error: {type(exc).__name__}"])


def _solve(value: object, problem_expr: object) -> Solution:
    if isinstance(value, tuple):
        return Solution(kind="none", notes=["multiple expressions"])

    # Equation -> solve for its single free symbol.
    if isinstance(value, sp.Equality):
        syms = sorted(value.free_symbols, key=lambda s: s.name)
        if len(syms) != 1:
            return Solution(kind="none", notes=["equation needs exactly one unknown"])
        var = syms[0]
        sols = sp.solve(sp.Eq(value.lhs, value.rhs), var)
        if not sols:
            return Solution(kind="none", notes=["no solution found"])
        sols = [_finalize(s) for s in sols]
        return Solution(kind="solutions", value=sols, variable=var.name, problem_expr=problem_expr)

    if not isinstance(value, sp.Basic):
        return Solution(kind="none", notes=["not a SymPy object"])

    # Indefinite integral -> antiderivative (compare up to a constant).
    if isinstance(value, sp.Integral) and any(len(lim) == 1 for lim in value.limits):
        var = value.limits[0][0]
        result = value.doit()
        if result.has(sp.Integral):
            return Solution(kind="none", notes=["integral not elementary"])
        return Solution(kind="antiderivative", value=_finalize(result), variable=var.name,
                        problem_expr=problem_expr)

    result = value.doit() if hasattr(value, "doit") else value
    if result.has(sp.Integral, sp.Derivative, sp.Limit):
        return Solution(kind="none", notes=["could not evaluate"])
    result = _finalize(result)
    if result.free_symbols:
        return Solution(kind="expression", value=result, problem_expr=problem_expr)
    return Solution(kind="number", value=result, problem_expr=problem_expr)

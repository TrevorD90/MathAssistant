"""Intake: SymPy solve + ONE AI call for level and step plan (spec §7.1, N3, N6).

Plan validation (all code, no extra AI calls):
* level clamped to 1-5; 1-8 steps; strings length-capped.
* If SymPy solved the problem, SymPy's answer wins (N8): the plan's final
  answer and last-step result are overwritten if they disagree.
* Every learner-visible plan string (titles, questions, hints, problem title)
  is run through the leak guard. A leaking string is replaced with a generic
  safe version rather than spending another AI call.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import sympy as sp

from ..providers.base import LLMProvider, StructuredRequest, Usage
from . import prompts
from .answer_check import Verdict, check_step
from .leak_guard import GuardContext, Target, scan, target_from_latex
from .solver import Solution, solve_latex

log = logging.getLogger(__name__)

MAX_STEPS = 8
_CAPS = {"title": 80, "goal": 300, "result_latex": 200, "first_question": 400,
         "check_question": 400, "safe_hint": 400}


class PlanError(Exception):
    """The model's plan was unusable (malformed twice is not retried: cost)."""


@dataclass
class IntakeResult:
    level: int
    title: str
    plan: dict            # {"final_answer_latex": str, "steps": [...]}
    solution: Solution
    usage: Usage
    ai_calls: int
    replaced_strings: int  # plan strings replaced by the leak guard


def final_target(solution: Solution, plan: dict) -> Target | None:
    """The final-answer leak target: SymPy's answer, else the model's stated answer."""
    if solution.kind != "none":
        return Target("final", solution.value, solution.latex(), solution.variable)
    return target_from_latex("final", plan.get("final_answer_latex"))


def step_target(step: dict) -> Target | None:
    return target_from_latex("step", step.get("result_latex"))


def _clean_step(raw: dict, i: int) -> dict:
    step = {}
    for k, cap in _CAPS.items():
        v = raw.get(k, "")
        step[k] = (v if isinstance(v, str) else str(v)).strip()[:cap]
    if not step["title"]:
        step["title"] = f"Step {i + 1}"
    return step


def _generic(field_name: str, i: int, level: int) -> str:
    """Generic, answer-free fallbacks for leaking plan strings."""
    simple = level <= 2
    return {
        "title": f"Step {i + 1}",
        "first_question": ("What should we do first here?" if simple
                           else "What's the first thing you'd do for this step?"),
        "check_question": ("How do you know that's right?" if simple
                           else "Why does that step work?"),
        "safe_hint": ("Take it one small piece at a time. What do you notice?" if simple
                      else "Look again at what this step asks for. Which rule or idea applies?"),
        "goal": "Work out this step.",
    }[field_name]


def run_intake(provider: LLMProvider, problem_latex: str, problem_kind: str = "math") -> IntakeResult:
    """`problem_kind` is "math" (LaTeX) or "words" (a word problem in plain text)."""
    if problem_kind == "words":
        solution = Solution(kind="none")   # solved below from the model's math formulation
        verified = None
    else:
        solution = solve_latex(problem_latex)
        verified = solution.latex() if solution.kind != "none" else None

    req = StructuredRequest(
        system_blocks=[prompts.INTAKE_SYSTEM],
        messages=[{"role": "user",
                   "content": prompts.intake_user_message(problem_latex, verified, problem_kind)}],
        schema=prompts.INTAKE_SCHEMA,
        max_tokens=prompts.INTAKE_MAX_TOKENS,
        purpose="intake",
    )
    result = provider.structured(req)
    data = result.data
    if not data or not isinstance(data.get("steps"), list) or not data["steps"]:
        raise PlanError("malformed plan")

    try:
        level = int(data.get("level", 3))
    except (TypeError, ValueError):
        level = 3
    level = min(5, max(1, level))
    steps = [_clean_step(s, i) for i, s in enumerate(data["steps"][:MAX_STEPS]) if isinstance(s, dict)]
    if not steps:
        raise PlanError("no usable steps")

    formulation = str(data.get("math_formulation_latex", "") or "").strip()[:300]
    plan = {"final_answer_latex": str(data.get("final_answer_latex", "")).strip()[:200], "steps": steps,
            "math_formulation_latex": formulation}

    # Word problems: the model translates words -> math; SymPy does the math (N8).
    if problem_kind == "words" and formulation:
        solution = solve_latex(formulation)
        if solution.kind != "none":
            verified = solution.latex()
            log.info("intake: word problem solved by SymPy from the model's formulation (kind=%s)", solution.kind)

    # N8: SymPy's answer wins over the model's.
    if solution.kind != "none":
        if plan["final_answer_latex"] and check_step(plan["final_answer_latex"], verified) != Verdict.CORRECT:
            log.info("intake: model final answer disagreed with SymPy; using SymPy")
        plan["final_answer_latex"] = verified
        last = steps[-1]
        if check_step(last["result_latex"], _last_step_expected(solution)) != Verdict.CORRECT:
            last["result_latex"] = _last_step_expected(solution)

    # Leak-guard every learner-visible string.
    replaced = 0
    ft = final_target(solution, plan)
    for i, step in enumerate(steps):
        targets = [t for t in (ft, step_target(step)) if t]
        ctx = GuardContext(targets=targets, problem_latex=problem_latex)
        for field_name in ("title", "first_question", "check_question", "safe_hint", "goal"):
            # The check question comes after the learner produced this step's
            # result, so it only needs to avoid the final answer (and later steps).
            if field_name == "check_question":
                later = [step_target(s) for s in steps[i + 1:]]
                fctx = GuardContext(targets=[t for t in [ft if i < len(steps) - 1 else None, *later] if t],
                                    problem_latex=problem_latex,
                                    revealed_latex=[step["result_latex"]] if step["result_latex"] else [])
            else:
                fctx = ctx
            if step[field_name] and scan(step[field_name], fctx):
                step[field_name] = _generic(field_name, i, level)
                replaced += 1
        if not step["first_question"]:
            step["first_question"] = _generic("first_question", i, level)
        if not step["safe_hint"]:
            step["safe_hint"] = _generic("safe_hint", i, level)
        if not step["check_question"]:
            step["check_question"] = _generic("check_question", i, level)

    title = str(data.get("title", "")).strip()[:60]
    all_targets = [t for t in [ft, *(step_target(s) for s in steps)] if t]
    if not title or scan(title, GuardContext(targets=all_targets, problem_latex=problem_latex)):
        title = _fallback_title(problem_latex)
        replaced += 1

    return IntakeResult(level=level, title=title, plan=plan, solution=solution,
                        usage=result.usage, ai_calls=1, replaced_strings=replaced)


def _last_step_expected(solution: Solution) -> str:
    """LaTeX the learner's last-step answer is compared against."""
    if solution.kind == "antiderivative":
        return sp.latex(solution.value)
    if solution.kind == "solutions":
        return ", ".join(sp.latex(v) for v in solution.value)
    return solution.latex()


def _fallback_title(problem_latex: str) -> str:
    base = problem_latex if len(problem_latex) <= 40 else problem_latex[:37] + "..."
    return f"Problem: {base}"

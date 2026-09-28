"""Decide what a learner's answer matches (spec §7.2-§7.4, N8).

Learners don't always follow the plan's step order. An answer is checked
against, in priority order:

  1. the final answer            -> jump to the end (then the check question)
  2. the current step's result   -> normal advance
  3. a later step's result       -> jump ahead to that step
  4. "equivalent but unfinished" for any of the above
  5. otherwise: the current step's verdict (usually INCORRECT)

A correct answer is never reported as incorrect just because it belongs to
a different step than the one the plan expected.

Candidates come from the learner's input:
  * math input (or math-looking text): the whole thing, plus each side of an
    equation chain like `152-3(2) = 152-6 = 146` (last side first);
  * words with embedded math ("152 - 6 is 146", "it's 146"): the numbers and
    math segments found in the text. These can confirm a correct answer but
    never count as a wrong attempt.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .answer_check import Verdict, check_final, check_step
from .latex_parse import normalize, split_top_level, try_parse
from .leak_guard import extract_numbers, extract_segments
from .solver import Solution

_FUNC_WORDS = {"sin", "cos", "tan", "sec", "csc", "cot", "ln", "log", "sqrt", "pi", "exp"}


def looks_like_math(text: str) -> bool:
    """Plain text that is really a math answer ("25", "2x+2", "x = 3")."""
    t = text.strip()
    if not t or len(t) > 120:
        return False
    for word in re.findall(r"[A-Za-z]{2,}", t):
        if word.lower() not in _FUNC_WORDS:
            return False
    if not re.search(r"[\dA-Za-z]", t):
        return False
    return try_parse(t) is not None


@dataclass
class Candidates:
    items: list[str] = field(default_factory=list)
    from_words: bool = False     # extracted from prose: may confirm, never penalize

    @property
    def primary(self) -> str:
        return self.items[0] if self.items else ""


_UNIT_RE = re.compile(r"\\(?:text|textrm|mathrm|operatorname)\{[^}]*\}")


def strip_units(latex: str) -> str:
    """Drop unit words and currency marks: `36\\text{ apples}` -> `36`, `\\$4.50` -> `4.50`."""
    s = _UNIT_RE.sub(" ", latex)
    s = s.replace("\\$", " ").replace("$", " ")
    return s.strip()


def candidates(text: str, latex: str) -> Candidates:
    if latex:
        bare = strip_units(latex)
        latex = bare if bare and bare != latex and try_parse(latex) is None else latex
    primary = latex or (text if looks_like_math(text) else "")
    if primary:
        items = [primary]
        sides = split_top_level(normalize(primary), "=")
        if len(sides) > 2:  # a chain a = b = c: every side is something the learner wrote
            items += list(reversed(sides))
        return Candidates(items=_dedupe(items))
    if not text:
        return Candidates()
    found: list[str] = []
    for seg in extract_segments(text):
        found += list(reversed(split_top_level(seg, "="))) if "=" in seg else [seg]
    found += [snippet for _, snippet in extract_numbers(text)]
    # Later mentions are usually the conclusion ("152 - 6 is 146"): check them first.
    return Candidates(items=_dedupe(list(reversed(found))), from_words=True)


def _dedupe(items: list[str]) -> list[str]:
    seen, out = set(), []
    for it in items:
        k = it.strip()
        if k and k not in seen:
            seen.add(k)
            out.append(k)
    return out


@dataclass
class Match:
    verdict: Verdict
    target: str                  # "final" | "current" | "later" | "none"
    step_index: int | None = None
    math: str = ""
    from_words: bool = False


def _final_verdict(c: str, solution: Solution, plan: dict) -> Verdict:
    if solution.kind != "none":
        return check_final(c, solution)
    return check_step(c, plan.get("final_answer_latex"))


def route(cands: Candidates, step_index: int, steps: list[dict], solution: Solution, plan: dict) -> Match:
    """Classify the learner's answer. Pure function (no state changes)."""
    if not cands.items:
        return Match(Verdict.UNCHECKABLE, "none")
    fw = cands.from_words
    finals = [(c, _final_verdict(c, solution, plan)) for c in cands.items]
    for c, v in finals:
        if v == Verdict.CORRECT:
            return Match(Verdict.CORRECT, "final", len(steps) - 1, c, fw)

    current = steps[step_index].get("result_latex") if step_index < len(steps) else None
    currents = [(c, check_step(c, current)) for c in cands.items]
    for c, v in currents:
        if v == Verdict.CORRECT:
            return Match(Verdict.CORRECT, "current", step_index, c, fw)

    for j in range(step_index + 1, len(steps)):
        for c in cands.items:
            if check_step(c, steps[j].get("result_latex")) == Verdict.CORRECT:
                return Match(Verdict.CORRECT, "later", j, c, fw)

    for c, v in finals + currents:
        if v == Verdict.NOT_SIMPLIFIED:
            return Match(Verdict.NOT_SIMPLIFIED, "current", step_index, c, fw)

    # Nothing matched. The verdict for the learner's main input decides.
    primary_v = currents[0][1] if currents else Verdict.UNCHECKABLE
    if step_index == len(steps) - 1 and solution.kind != "none":
        primary_v = finals[0][1]
    if primary_v == Verdict.UNCHECKABLE and len(cands.items) > 1:
        # e.g. an unparseable chain: judge its last side
        primary_v = check_step(cands.items[1], current)
    return Match(primary_v, "none", step_index, cands.primary, fw)

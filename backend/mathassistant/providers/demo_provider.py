"""Offline demo provider (development only).

Enabled with DEV_MODE=true + MATHASSISTANT_DEMO=1, never in bundled builds.
Returns canned, generic tutoring responses so the UI can be exercised without
an API key or network. Not a tutor: it doesn't read the learner's message.
"""

from __future__ import annotations

import re

from ..engine.solver import solve_latex
from .base import Capabilities, LLMProvider, StructuredRequest, StructuredResult, Usage


class DemoProvider(LLMProvider):
    name = "demo"

    def __init__(self):
        super().__init__("demo", Capabilities(vision=True, structured_output=True, streaming=False))
        self._turn = 0

    def probe(self) -> Capabilities:
        return self.capabilities

    def structured(self, req: StructuredRequest) -> StructuredResult:
        usage = Usage(input_tokens=0, output_tokens=0)
        if req.purpose == "intake":
            content = req.messages[0]["content"]
            problem = re.search(r"PROBLEM \([^)]*\): (.*)", content).group(1).strip()
            words = "word problem" in content
            sol = solve_latex(problem) if not words else solve_latex("")
            return StructuredResult(data={
                "level": 3,
                "title": "Demo problem",
                "final_answer_latex": sol.latex() if sol.kind != "none" else "",
                "math_formulation_latex": "",   # the demo doesn't translate word problems
                "steps": [
                    {"title": "Understand the problem", "goal": "Say what the problem asks for.",
                     "result_latex": "", "first_question": "In your own words, what is this problem asking?",
                     "check_question": "Why does knowing that help you start?",
                     "safe_hint": "Read the problem one piece at a time."},
                    {"title": "Find the answer", "goal": "Work it out.",
                     "result_latex": sol.latex() if sol.kind in ("number", "expression") else "",
                     "first_question": "What do you get when you work it out?",
                     "check_question": "How could you check your answer?",
                     "safe_hint": "Try a smaller, similar problem first."},
                ],
            }, usage=usage)
        if req.purpose == "vision":
            return StructuredResult(data={"readable": True, "note": "demo", "problems": [
                {"label": "1", "kind": "math", "latex": r"5\times 5", "text": "", "instruction": ""},
                {"label": "2", "kind": "words", "latex": "",
                 "text": "Sam has 3 bags with 12 apples in each bag. How many apples does Sam have?",
                 "instruction": ""},
            ]}, usage=usage)
        self._turn += 1
        note = req.messages[0]["content"]
        passed = "PHASE: CHECK" in note
        correct = "yes" if "step is conceptual" in note else "n/a"
        allowed = "Display: ALLOWED" in note
        return StructuredResult(data={
            "intent": "on-step",
            "reply": "(Demo) Good thinking. What would you try next?" if not passed
            else "(Demo) That explanation works. What do you get when you work it out?",
            "question": "What would you try next?" if not passed else "What do you get when you work it out?",
            "learner_correct": correct,
            "check_passed": passed,
            "display_title": "A similar example" if allowed else "",
            "display_items": [{"latex": r"3\times 4 = 12", "caption": "3 groups of 4"}] if allowed else [],
            "display_keep": False,
        }, usage=usage)

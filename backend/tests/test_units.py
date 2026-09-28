"""Unit tests: LaTeX parsing, SymPy equivalence, leak guard, off-topic pre-check."""

from __future__ import annotations

import pytest
import sympy as sp

from mathassistant.engine import display, intent
from mathassistant.engine.answer_check import Verdict, check_final, check_step
from mathassistant.engine.latex_parse import LatexParseError, parse, try_parse
from mathassistant.engine.leak_guard import GuardContext, Target, number_words, scan, target_from_latex
from mathassistant.engine.solver import Solution, solve_latex

x = sp.Symbol("x")


# ------------------------------------------------------------------ parsing

@pytest.mark.parametrize("latex, expected", [
    (r"5\times5", 25),
    (r"\frac{3}{4}+\frac{1}{8}", sp.Rational(7, 8)),
    (r"2\sin(x^2)x", 2 * x * sp.sin(x**2)),              # SymPy's own parser gets this wrong
    (r"2x\cos\left(x^{2}\right)", 2 * x * sp.cos(x**2)),
    (r"\cos(x^{2})\cdot2x", 2 * x * sp.cos(x**2)),
    (r"\sqrt[3]{27}", 3),
    (r"\log_{2}8", 3),
    (r"\ln(e^2)", 2),
    (r"x^{y^{z}}", x ** (sp.Symbol("y") ** sp.Symbol("z"))),   # nested exponents
    (r"\left|-3\right|", 3),
    (r"50\%", sp.Rational(1, 2)),
])
def test_parse_values(latex, expected):
    assert sp.simplify(parse(latex).value - expected) == 0


def test_parse_calculus_routes_to_sympy_parser():
    assert isinstance(parse(r"\frac{d}{dx}\sin(x^2)").value, sp.Derivative)
    assert isinstance(parse(r"\int x^2\,dx").value, sp.Integral)


@pytest.mark.parametrize("bad", ["", r"\placeholder{}", r"\frac{1}{", r"\foo{x}", "__import__"])
def test_parse_rejects(bad):
    with pytest.raises(LatexParseError):
        parse(bad)


def test_translator_cannot_call_python_names():
    # Letters are always single-letter symbols; "open" becomes o*p*e*n, never a call.
    p = try_parse("open(1)")
    assert p is None or not callable(p.value)


# ------------------------------------------------------------------ solver + equivalence

@pytest.mark.parametrize("problem, kind", [
    (r"5\times5", "number"),
    (r"\frac{d}{dx}\sin(x^2)", "expression"),
    ("2x+3=7", "solutions"),
    (r"\int x^2\,dx", "antiderivative"),
    (r"\int_{0}^{1} x^2\,dx", "number"),
    (r"\lim_{x\to0}\frac{\sin x}{x}", "number"),
    (r"\text{A train leaves}", "none"),
])
def test_solver_kinds(problem, kind):
    assert solve_latex(problem).kind == kind


def test_solution_round_trips_through_record():
    s = solve_latex(r"\frac{d}{dx}\sin(x^2)")
    s2 = Solution.from_record(s.to_record())
    assert sp.simplify(s2.value - s.value) == 0


@pytest.mark.parametrize("answer, problem, verdict", [
    ("25", r"5\times5", Verdict.CORRECT),
    (r"5\times5", r"5\times5", Verdict.NOT_SIMPLIFIED),
    ("24", r"5\times5", Verdict.INCORRECT),
    (r"2x\cos(x^2)", r"\frac{d}{dx}\sin(x^2)", Verdict.CORRECT),
    (r"\cos(x^2)\cdot 2x", r"\frac{d}{dx}\sin(x^2)", Verdict.CORRECT),
    (r"\frac{d}{dx}\sin(x^2)", r"\frac{d}{dx}\sin(x^2)", Verdict.NOT_SIMPLIFIED),
    (r"\cos(x^2)", r"\frac{d}{dx}\sin(x^2)", Verdict.INCORRECT),
    ("x=2", "2x+3=7", Verdict.CORRECT),
    ("2", "2x+3=7", Verdict.CORRECT),
    ("3", "2x+3=7", Verdict.INCORRECT),
    ("x=3, x=2", "x^2-5x+6=0", Verdict.CORRECT),
    ("2", "x^2-5x+6=0", Verdict.INCORRECT),
    (r"\frac{x^3}{3}+C", r"\int x^2\,dx", Verdict.CORRECT),
    (r"\frac{x^3}{3}+7", r"\int x^2\,dx", Verdict.CORRECT),
    (r"x^3", r"\int x^2\,dx", Verdict.INCORRECT),
    ("0.875", r"\frac{3}{4}+\frac{1}{8}", Verdict.CORRECT),
    (r"\frac{14}{16}", r"\frac{3}{4}+\frac{1}{8}", Verdict.NOT_SIMPLIFIED),
    ("0.33", r"\frac{1}{3}+0", Verdict.CORRECT),          # rounded decimal within tolerance
    ("0.3", r"\frac{1}{3}+0", Verdict.INCORRECT),         # one decimal place is too coarse
    ("banana", r"5\times5", Verdict.INCORRECT),           # letters parse as symbols -> not equal
])
def test_check_final(answer, problem, verdict):
    assert check_final(answer, solve_latex(problem)) == verdict


def test_check_step_equivalence_2x_plus_2():
    assert check_step("2(x+1)", "2x+2") == Verdict.CORRECT
    assert check_step("2x+1", "2x+2") == Verdict.INCORRECT


def test_check_step_equation_scaled():
    assert check_step("4x=8", "2x=4") == Verdict.CORRECT
    assert check_step("2x=5", "2x=4") == Verdict.INCORRECT


def test_check_step_uncheckable_when_words_or_no_result():
    # Words never count as a correct math answer (the engine only sends math-looking text here).
    assert check_step("because groups", "25") != Verdict.CORRECT
    assert check_step("25", "") == Verdict.UNCHECKABLE


# ------------------------------------------------------------------ leak guard

def _final(problem):
    s = solve_latex(problem)
    return Target("final", s.value, s.latex(), s.variable)


@pytest.mark.parametrize("text, leaks", [
    ("How many apples are in 5 groups of 5?", False),
    ("The answer is 25.", True),
    ("That makes twenty-five.", True),
    ("That makes twenty five.", True),
    (r"What is $5\times5$?", False),
    ("Count by fives: 5, 10, 15, 20...", False),
])
def test_guard_numbers(text, leaks):
    ctx = GuardContext([_final(r"5\times5")], r"5\times5")
    assert (scan(text, ctx) is not None) == leaks


@pytest.mark.parametrize("text, leaks", [
    (r"Let $u=x^2$. What's the derivative of $\sin u$?", False),
    (r"So you get $2x\cos(x^2)$.", True),
    (r"It's $\cos\left(x^{2}\right)\cdot 2x$.", True),
    ("Multiply cos(x^2) by 2x", False),        # two pieces, not the expression
    ("Multiply: cos(x^2) * 2x", True),
    ("cos(x²)·2x", True),
    (r"Find $\frac{d}{dx}\sin(x^2)$ with the chain rule.", False),
])
def test_guard_expressions(text, leaks):
    ctx = GuardContext([_final(r"\frac{d}{dx}\sin(x^2)")], r"\frac{d}{dx}\sin(x^2)")
    assert (scan(text, ctx) is not None) == leaks


@pytest.mark.parametrize("text, leaks", [
    ("Subtract 3 from both sides.", False),
    ("Divide both sides by 2.", False),
    ("So x = 2.", True),
    ("x equals 2", True),
    ("The answer is 2", True),
    ("What is 2x equal to?", False),
])
def test_guard_answer_number_that_appears_in_problem(text, leaks):
    ctx = GuardContext([_final("2x+3=7")], "2x+3=7")
    assert (scan(text, ctx) is not None) == leaks


def test_guard_allows_revealed_values():
    ctx = GuardContext([_final(r"5\times5")], r"5\times5", revealed_latex=["25"])
    assert scan("Yes, 25 is right.", ctx) is None


def test_guard_step_result_target():
    t = target_from_latex("step", r"\cos(u)")
    ctx = GuardContext([t], r"\frac{d}{dx}\sin(x^2)")
    assert scan(r"The outer derivative is $\cos(u)$.", ctx) is not None
    assert scan(r"What's the derivative of $\sin(u)$?", ctx) is None


def test_guard_text_fallback_for_unsolvable_problems():
    t = target_from_latex("final", r"\text{the train arrives at noon}")
    ctx = GuardContext([t], r"\text{A train leaves}")
    assert scan("The train arrives at noon, obviously.", ctx) is not None


def test_number_words():
    assert "twenty-five" in number_words(25)
    assert "one hundred and five" in number_words(105)


# ------------------------------------------------------------------ off-topic pre-check

@pytest.mark.parametrize("msg, off", [
    ("what's your favorite movie", True),
    ("do you like minecraft?", True),
    ("tell me a joke", True),
    ("I don't get it", False),                  # uncertain -> AI
    ("because there are 5 groups", False),
    ("just tell me the answer", False),
    ("why do we multiply?", False),
    ("x", False),
    ("25", False),
    ("my dog has 4 legs so is it 4?", False),   # has math content -> AI decides
    ("is the inner function the thing inside", False),
])
def test_precheck(msg, off):
    assert intent.is_obviously_off_topic(msg, intent.problem_vocabulary("Identify inner function")) == off


def test_redirect_repeats_current_question():
    msg = intent.redirect_message(2, "What do you get when you distribute the 3?")
    assert msg == "That's not about this problem. Back to step 2: What do you get when you distribute the 3?"


# ------------------------------------------------------------------ display schema

def test_display_validation():
    ok = display.validate_payload({"type": "latex", "items": [{"latex": "3+4", "caption": "c"}]})
    assert ok and ok["items"][0]["latex"] == "3+4"
    assert display.validate_payload({"type": "graph", "items": []}) is None
    assert display.validate_payload({"type": "steps", "items": []}) is None       # local-only type
    assert display.validate_payload({"type": "latex", "items": []}) is None
    assert display.validate_payload("garbage") is None
    assert display.validate_payload({"type": "latex", "items": [{"latex": "x" * 999}]}) is None


def test_display_gating_rules():
    assert display.display_allowed(step_just_started=True, wrong_attempts=0, asked_for_example=False)
    assert not display.display_allowed(step_just_started=False, wrong_attempts=1, asked_for_example=False)
    assert display.display_allowed(step_just_started=False, wrong_attempts=2, asked_for_example=False)
    assert display.display_allowed(step_just_started=False, wrong_attempts=0, asked_for_example=True)

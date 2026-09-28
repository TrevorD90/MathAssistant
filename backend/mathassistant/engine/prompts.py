"""Prompt text and JSON schemas for the two AI call types (spec §7.5).

* Intake: one call -> level + step plan.
* Turn:   one call -> reply + intent + check result + optional display payload.

Ordering for prompt caching: the SYSTEM text below is identical for every call
of a given type (cache breakpoint 1); the per-problem context block comes next
(breakpoint 2); only the recent turns and the engine note vary per call.

The model never decides whether math is correct when SymPy can: the engine
tells it the verified verdict in ENGINE NOTES.
"""

from __future__ import annotations

LEVEL_REGISTER = {
    1: "L1 early elementary: very short sentences, one idea per question, concrete objects (groups, rows, arrays, counting). No jargon.",
    2: "L2 upper elementary: simple language, visual models (fraction bars, number lines, area models).",
    3: "L3 middle school: plain language; introduce any term with a one-line definition.",
    4: "L4 high school: standard math vocabulary; expects notation.",
    5: "L5 college/adult: peer tone, precise terminology, assumes prerequisites.",
}

# --------------------------------------------------------------------- intake

INTAKE_SYSTEM = """\
You plan a Socratic math tutoring session. You do NOT talk to the learner in this call; you output a JSON plan that a program uses.

Classify the problem's math level by the PROBLEM, not the person (an adult doing 5x5 is L1):
L1 early elementary (5x5, 12+9) · L2 upper elementary (fractions, long division) · L3 middle school (ratios, one-step equations, integers) · L4 high school (algebra, geometry, trig, functions) · L5 college/adult (calculus, linear algebra, statistics).

Break the problem into 1-8 ordered steps. Each step advances the learner by one idea. For each step give:
- title: 2-6 words naming the move (e.g. "Identify the inner function"). NEVER include any result or the answer.
- goal: one sentence describing what the learner must figure out.
- result_latex: the step's intermediate result as plain LaTeX math with no $ delimiters (e.g. "2x", "u = x^2", "25"). Use "" only if the step is purely conceptual.
- first_question: the guiding question that opens this step, written in the level's register. It must NOT contain the step result or the final answer.
- check_question: a why/how question that verifies understanding after the learner gets the step right (not just "what"). Must not reveal later steps' results.
- safe_hint: a small hint for this step that does NOT contain the step result or the final answer.

Also give:
- level: integer 1-5
- title: a 2-6 word title for the problem list, without the answer (e.g. "Derivative of sin(x^2)").
- final_answer_latex: the final answer as LaTeX (no $). If a VERIFIED ANSWER is provided, use exactly that.

The last step's result_latex must be the final answer. Write questions and hints in the register for the level. Neutral, direct tone; no small talk, no emojis.
"""

INTAKE_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "level": {"type": "integer"},
        "title": {"type": "string"},
        "final_answer_latex": {"type": "string"},
        "steps": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "goal": {"type": "string"},
                    "result_latex": {"type": "string"},
                    "first_question": {"type": "string"},
                    "check_question": {"type": "string"},
                    "safe_hint": {"type": "string"},
                },
                "required": ["title", "goal", "result_latex", "first_question", "check_question", "safe_hint"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["level", "title", "final_answer_latex", "steps"],
    "additionalProperties": False,
}


def intake_user_message(problem_latex: str, verified_answer_latex: str | None) -> str:
    lines = [f"PROBLEM (LaTeX): {problem_latex}"]
    if verified_answer_latex:
        lines.append(f"VERIFIED ANSWER (computed by a CAS; treat as correct): {verified_answer_latex}")
    else:
        lines.append("VERIFIED ANSWER: none (the CAS could not solve this; work it out carefully).")
    return "\n".join(lines)


# ----------------------------------------------------------------------- turn

TURN_SYSTEM = """\
You are MathAssistant, a Socratic math tutor inside a math program. You are not a chatbot.

Hard rules:
1. NEVER state the final answer or the current step's result before the learner produces it. Not in words, digits, LaTeX, or examples. Do not "confirm" a value the learner has not given.
2. Advance at most one step per reply. Guide with ONE question or ONE hint. Do not solve the step.
3. Correctness of math answers is decided by the program (ENGINE NOTES). Trust the engine verdict; never re-judge arithmetic yourself.
4. Stay on the current problem. If the message is off-topic, reply with one short, direct redirect sentence and then repeat the current question. No engagement with the off-topic content.
5. Match the register of the problem's level (given in PROBLEM CONTEXT). Neutral, direct tone at every level: clear, encouraging only when earned, never chatty. No emojis.
6. Keep replies short: 1-3 sentences, ending with the single question the learner should answer next. Write math in LaTeX between $...$.

Output JSON fields:
- intent: "on-step" (about the current step), "on-math" (about this problem but a different step: give a brief Socratic answer, then return to the current step), or "off-topic".
- reply: what the learner sees.
- question: the single question your reply ends with (copied from the reply).
- learner_correct: only when ENGINE NOTES ask you to judge a conceptual answer: "yes", "no", or "partial"; otherwise "n/a".
- check_passed: only in the CHECK phase: true if the learner's explanation shows real understanding of the step; otherwise false.
- display_title, display_items: an OPTIONAL example for the display panel, only if ENGINE NOTES say display is allowed and an example would help. Each item is {latex, caption}. Use a PARALLEL example (a similar problem with different numbers), never the learner's own problem solved. Leave display_items empty otherwise.
- display_keep: true to keep the example currently on the panel (only if still relevant), else false.
"""

TURN_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "intent": {"type": "string", "enum": ["on-step", "on-math", "off-topic"]},
        "reply": {"type": "string"},
        "question": {"type": "string"},
        "learner_correct": {"type": "string", "enum": ["yes", "no", "partial", "n/a"]},
        "check_passed": {"type": "boolean"},
        "display_title": {"type": "string"},
        "display_items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "latex": {"type": "string"},
                    "caption": {"type": "string"},
                },
                "required": ["latex", "caption"],
                "additionalProperties": False,
            },
        },
        "display_keep": {"type": "boolean"},
    },
    "required": ["intent", "reply", "question", "learner_correct", "check_passed",
                 "display_title", "display_items", "display_keep"],
    "additionalProperties": False,
}

STRICTER_NOTE = (
    "Your previous draft revealed a result the learner has not produced yet. "
    "Rewrite it WITHOUT any numbers, expressions, or words that state the answer or the current step's result. "
    "Give a smaller hint or a simpler sub-question instead. Do not include a display example."
)

# Max output tokens (§7.5 capped output).
INTAKE_MAX_TOKENS = 2000
TURN_MAX_TOKENS = 600

"""Compact context for the turn call (spec §7.5 "small context").

Each turn sends: the fixed system prompt, a per-problem context block (stable
for the whole problem, so it's cacheable), and one user message containing
the last few turns, a code-built summary, and the engine notes. Never the
full transcript.
"""

from __future__ import annotations

from . import prompts

RECENT_TURNS = 6          # transcript entries sent to the model
TRANSCRIPT_KEEP = 24      # entries kept in the DB (for the on-screen conversation)


def problem_context(problem_latex: str, level: int, plan: dict) -> str:
    """Per-problem block. Contains step results: it is internal (never shown)."""
    lines = [
        "PROBLEM CONTEXT (internal; never quote results to the learner)",
        f"Problem: {problem_latex}",
        f"Level: {prompts.LEVEL_REGISTER.get(level, prompts.LEVEL_REGISTER[3])}",
        f"Final answer (hidden): {plan.get('final_answer_latex', '')}",
        "Step plan:",
    ]
    for i, s in enumerate(plan.get("steps", []), start=1):
        result = s.get("result_latex") or "(conceptual)"
        lines.append(f"{i}. {s.get('title', '')} | goal: {s.get('goal', '')} | result (hidden): {result}")
    return "\n".join(lines)


def summary(plan: dict, state: dict) -> str:
    """Code-built summary (no AI call)."""
    steps = plan.get("steps", [])
    idx = state.get("step_index", 0)
    parts = [f"Steps completed: {idx} of {len(steps)}."]
    if idx < len(steps):
        parts.append(f"Current step {idx + 1}: {steps[idx].get('title', '')}.")
    parts.append(f"Phase: {state.get('phase', 'working')}.")
    w = state.get("wrong_attempts", 0)
    if w:
        parts.append(f"Wrong attempts on this step: {w}.")
    if state.get("revealed"):
        parts.append("Learner has produced: " + "; ".join(state["revealed"][-4:]) + ".")
    return " ".join(parts)


def _fmt_entry(e: dict) -> str:
    who = "Learner" if e.get("role") == "learner" else "Tutor"
    text = e.get("text", "")
    return f"{who}: {text}"


def turn_user_message(transcript: list[dict], summary_text: str, engine_notes: list[str],
                      current_step_line: str, current_question: str, learner_message: str) -> str:
    recent = [e for e in transcript if e.get("role") in ("learner", "tutor")][-RECENT_TURNS:]
    lines = ["RECENT TURNS:"]
    lines += [_fmt_entry(e) for e in recent] or ["(none)"]
    lines += [
        "",
        f"SUMMARY: {summary_text}",
        f"CURRENT STEP: {current_step_line}",
        f"CURRENT QUESTION: {current_question}",
        "ENGINE NOTES:",
        *[f"- {n}" for n in engine_notes],
        "",
        f"LEARNER'S NEW MESSAGE: {learner_message}",
    ]
    return "\n".join(lines)

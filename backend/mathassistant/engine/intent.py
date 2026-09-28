"""Intent labels and the local off-topic pre-check (spec §8, N7).

The pre-check is deliberately **conservative**: it only fires when a message
has no math content, nothing about the problem, AND a positive off-topic cue
(chit-chat, questions about the tutor, common non-math topics). A false
positive would redirect a genuine conceptual answer, which is worse than
spending one AI call on an uncertain message. Everything uncertain goes to the
AI inside the normal turn call, which returns its own intent label.
"""

from __future__ import annotations

import re
from enum import Enum


class Intent(str, Enum):
    ON_STEP = "on-step"
    ON_MATH = "on-math"
    OFF_TOPIC = "off-topic"


# Any of these characters means "there is math here".
_MATH_CHARS = re.compile(r"[0-9=+\-*/^()<>√π∫∑%×÷\\]")

# Words that suggest the learner is talking about math or the problem.
_MATH_WORDS = {
    "add", "adding", "plus", "sum", "subtract", "minus", "difference", "multiply",
    "multiplying", "times", "product", "divide", "dividing", "quotient", "equal",
    "equals", "fraction", "numerator", "denominator", "decimal", "percent",
    "number", "numbers", "digit", "count", "group", "groups", "row", "rows",
    "column", "columns", "array", "total", "half", "double", "twice", "square",
    "root", "power", "exponent", "variable", "equation", "expression", "solve",
    "simplify", "factor", "distribute", "both", "side", "sides", "term", "terms",
    "derivative", "integral", "limit", "chain", "rule", "slope", "graph", "angle",
    "triangle", "function", "inside", "outside", "inner", "outer", "zero", "negative",
    "positive", "answer", "step", "problem", "question", "hint", "help", "stuck",
    "example", "explain", "understand", "confused", "mean", "means", "why", "how",
    "again", "repeat", "show", "sin", "cos", "tan", "log", "ln", "pi",
}

# Positive off-topic cues. The pre-check only fires if one of these matches.
_OFF_TOPIC_CUES = [
    r"\byour favou?rite\b", r"\bfavou?rite\b", r"\bwho are you\b", r"\bare you (a |an )?(real|human|robot|ai|alive)\b",
    r"\bdo you like\b", r"\bwhat do you like\b", r"\bhow old are you\b", r"\bwhat'?s your name\b",
    r"\btell me a (joke|story)\b", r"\bjoke\b", r"\bmovies?\b", r"\bfilms?\b", r"\bsongs?\b",
    r"\bmusic\b", r"\bvideo ?games?\b", r"\bminecraft\b", r"\bfortnite\b", r"\broblox\b",
    r"\bpokemon\b", r"\byoutube\b", r"\btiktok\b", r"\bweather\b", r"\bsports?\b",
    r"\bfootball\b", r"\bsoccer\b", r"\bbasketball\b", r"\bbirthday\b", r"\bpizza\b",
    r"\bdinner\b", r"\blunch\b", r"\bpets?\b", r"\bdogs?\b", r"\bcats?\b", r"\bnetflix\b",
    r"\bwhat'?s up\b", r"\bsup\b", r"\blol\b", r"\bbored\b", r"\bboring\b",
    r"\bwrite (me )?(an? )?(essay|poem|story|email)\b", r"\bhomework for (history|english|science)\b",
]
_OFF_TOPIC_RE = re.compile("|".join(_OFF_TOPIC_CUES), re.I)


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z']+", text.lower())


def has_math_content(text: str, problem_words: set[str] | None = None) -> bool:
    if _MATH_CHARS.search(text):
        return True
    words = _words(text)
    # A lone single letter ("x", "y") is almost always a variable.
    if any(len(w) == 1 and w not in ("a", "i") for w in words):
        return True
    if any(w in _MATH_WORDS for w in words):
        return True
    if problem_words and any(w in problem_words for w in words):
        return True
    return False


def problem_vocabulary(*texts: str) -> set[str]:
    """Content words from the problem's step titles/goals (4+ letters)."""
    vocab: set[str] = set()
    for t in texts:
        vocab.update(w for w in _words(t or "") if len(w) >= 4)
    return vocab


def is_obviously_off_topic(message: str, problem_words: set[str] | None = None) -> bool:
    """True only when the message is clearly unrelated to math/the problem.

    Uncertain messages return False and go to the AI.
    """
    text = (message or "").strip()
    if not text:
        return False
    if has_math_content(text, problem_words):
        return False
    return bool(_OFF_TOPIC_RE.search(text))


def redirect_message(step_number: int, current_question: str) -> str:
    """Canned redirect (no AI call). Neutral and direct, then the current question."""
    q = current_question.strip() or "Let's keep going with the problem."
    return f"That's not about this problem. Back to step {step_number}: {q}"

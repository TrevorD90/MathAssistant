"""The tutoring engine: intake, turn loop, resume (spec §7.2, N2-N5, N7, N11).

AI call budget per learner message:
  * obviously off-topic (local pre-check)        -> 0 calls, canned redirect
  * SymPy-verified correct step answer           -> 0 calls, canned "Right." + planned check question
  * SymPy-verified correct final answer          -> 0 calls, canned confirmation
  * everything else                              -> 1 call (reply + intent + check + display)
  * leak detected in that reply                  -> +1 regenerate, then canned safe hint (§7.3)
Resume -> 0 calls.

Phases per problem:
  working  -> learner is producing the current step's result
  checking -> result verified; learner answers the check-understanding question
  final    -> all steps passed; learner states the final answer
  done     -> completed
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Callable

from ..providers.base import LLMProvider, ProviderError, StructuredRequest, Usage
from ..storage import ProblemRecord, Storage
from . import context_builder, display, intent, prompts
from .answer_check import Verdict, check_final, check_step
from .latex_parse import try_parse
from .leak_guard import GuardContext, scan_all
from .solver import Solution
from .step_planner import PlanError, final_target, run_intake, step_target

log = logging.getLogger(__name__)

MALFORMED_NOTICE_AFTER = 2
MALFORMED_NOTICE = ("The AI model keeps returning responses the app can't use. "
                    "A tested model in Settings may work better.")

_FUNC_WORDS = {"sin", "cos", "tan", "sec", "csc", "cot", "ln", "log", "sqrt", "pi", "exp"}


class TutorError(Exception):
    def __init__(self, message: str, kind: str = "error"):
        super().__init__(message)
        self.kind = kind
        self.user_message = message


@dataclass
class TurnOutcome:
    ai_calls: int = 0
    usage: Usage = None  # type: ignore[assignment]

    def __post_init__(self):
        if self.usage is None:
            self.usage = Usage()


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


def _ack(level: int) -> str:
    return "Yes, that's right." if level <= 2 else "Correct."


class TutorEngine:
    def __init__(self, storage: Storage, provider_factory: Callable[[], LLMProvider]):
        self.storage = storage
        self.provider_factory = provider_factory

    # ================================================================ intake

    def start_problem(self, problem_latex: str) -> dict:
        problem_latex = (problem_latex or "").strip()
        if not problem_latex or r"\placeholder" in problem_latex:
            raise TutorError("Enter a problem first.", "empty")
        if len(problem_latex) > 2000:
            raise TutorError("That problem is too long. Enter one problem at a time.", "too_long")
        provider = self.provider_factory()
        try:
            intake = run_intake(provider, problem_latex)
        except PlanError:
            raise TutorError("The AI couldn't plan this problem. Try rewording it or try again.", "plan") from None
        except ProviderError as err:
            raise TutorError(err.user_message, err.kind) from None
        steps = intake.plan["steps"]
        state = {
            "step_index": 0,
            "phase": "working",
            "wrong_attempts": 0,
            "step_just_started": True,
            "revealed": [],
            "current_question": steps[0]["first_question"],
            "display": None,
            "malformed_count": 0,
        }
        rec = ProblemRecord.new(
            title=intake.title,
            problem_latex=problem_latex,
            level=intake.level,
            plan=intake.plan,
            solution=intake.solution.to_record(),
            state=state,
            transcript=[{"role": "tutor", "text": steps[0]["first_question"], "kind": "question"}],
            tokens_in=intake.usage.input_tokens + intake.usage.cache_read_tokens + intake.usage.cache_write_tokens,
            tokens_out=intake.usage.output_tokens,
            ai_calls=intake.ai_calls,
        )
        rec.summary = context_builder.summary(rec.plan, rec.state)
        self.storage.save_problem(rec)
        return self.view(rec)

    # ================================================================ resume

    def load(self, problem_id: str) -> dict:
        """Restore a saved problem. Zero AI calls."""
        rec = self._get(problem_id)
        return self.view(rec)

    def _get(self, problem_id: str) -> ProblemRecord:
        rec = self.storage.get_problem(problem_id)
        if rec is None:
            raise TutorError("That problem wasn't found.", "not_found")
        return rec

    # ================================================================ turn

    def submit(self, problem_id: str, text: str = "", latex: str = "") -> dict:
        rec = self._get(problem_id)
        if rec.status == "completed":
            return self.view(rec, notice="This problem is already solved.")

        text = (text or "").strip()[:1000]
        latex = (latex or "").strip()[:500]
        if not text and not latex:
            raise TutorError("Type an answer or a question first.", "empty")

        st = rec.state
        steps = rec.plan["steps"]
        idx = st["step_index"]
        step = steps[min(idx, len(steps) - 1)]
        solution = Solution.from_record(rec.solution)
        learner_shown = f"${latex}$" if latex else text
        history_before = list(rec.transcript)
        rec.transcript.append({"role": "learner", "text": learner_shown, "latex": latex or None})

        # ---- 1. Local off-topic pre-check (no AI call) -------------------
        if not latex:
            vocab = intent.problem_vocabulary(*(s.get("title", "") + " " + s.get("goal", "") for s in steps))
            if intent.is_obviously_off_topic(text, vocab):
                reply = intent.redirect_message(idx + 1, st["current_question"])
                return self._finish(rec, reply, kind="redirect", outcome=TurnOutcome())

        math = latex or (text if looks_like_math(text) else "")
        is_last = idx == len(steps) - 1
        phase = st["phase"]
        notes: list[str] = []
        advance_if_passed = False

        # ---- 2. Code checks (SymPy) --------------------------------------
        if phase == "final":
            v = (check_final(math, solution) if solution.kind != "none"
                 else check_step(math, rec.plan.get("final_answer_latex"))) if math else Verdict.UNCHECKABLE
            if v == Verdict.CORRECT:
                st["revealed"].append(math)
                return self._complete(rec, f"{_ack(rec.level)} You solved it: ${math}$.")
            notes.append(self._verdict_note(v, st, final=True))
        elif phase == "working":
            if math:
                if is_last and solution.kind != "none":
                    v = check_final(math, solution)
                else:
                    v = check_step(math, step.get("result_latex"))
            else:
                v = Verdict.UNCHECKABLE
            if v == Verdict.CORRECT:
                # Verified by SymPy -> canned acknowledgement + planned check question. 0 AI calls.
                st["revealed"].append(math)
                st["phase"] = "checking"
                st["display"] = None                      # §9.2 wipe on correct step answer
                st["current_question"] = step["check_question"]
                reply = f"{_ack(rec.level)} {step['check_question']}"
                return self._finish(rec, reply, kind="check", outcome=TurnOutcome())
            if v == Verdict.INCORRECT:
                st["wrong_attempts"] += 1
            notes.append(self._verdict_note(v, st, final=False, step=step))
        else:  # checking
            advance_if_passed = True
            if is_last:
                if self._final_already_produced(st, solution, rec.plan):
                    notes.append("PHASE: CHECK (last step). Judge the learner's explanation and set check_passed. "
                                 "If it passes, the whole problem is complete: confirm briefly in one sentence and ask nothing further "
                                 "(set question to \"\"). If it does not pass, ask a smaller why/how question.")
                else:
                    notes.append("PHASE: CHECK (last step). Judge the learner's explanation and set check_passed. "
                                 "If it passes, ask the learner to state the final answer to the original problem. "
                                 "If not, ask a smaller why/how question.")
            else:
                nxt = steps[idx + 1]
                notes.append(
                    "PHASE: CHECK. The learner already produced this step's result. Judge whether their explanation "
                    "shows understanding of: " + (step.get("goal") or step.get("title", "")) + ". Set check_passed. "
                    f"If it passes: confirm briefly, then open step {idx + 2} ({nxt['title']}) with this question: "
                    f"\"{nxt['first_question']}\". If not: ask a smaller why/how question about this step."
                )

        asked_example = display.learner_asked_for_example(text)
        allowed = display.display_allowed(step_just_started=st.get("step_just_started", False),
                                          wrong_attempts=st.get("wrong_attempts", 0),
                                          asked_for_example=asked_example)
        if advance_if_passed and not is_last:
            allowed = True  # a passed check introduces a new step (§9.1)
        notes.append("Display: ALLOWED (only if an example would help)." if allowed
                     else "Display: NOT allowed this turn; leave display_items empty.")

        # ---- 3. One AI call ---------------------------------------------
        provider = self.provider_factory()
        system_blocks = [prompts.TURN_SYSTEM, context_builder.problem_context(rec.problem_latex, rec.level, rec.plan)]
        step_line = f"{idx + 1} of {len(steps)}: {step['title']} | goal: {step.get('goal', '')}"
        user_msg = context_builder.turn_user_message(history_before, context_builder.summary(rec.plan, st), notes,
                                                     step_line, st["current_question"], learner_shown)
        req = StructuredRequest(system_blocks=system_blocks,
                                messages=[{"role": "user", "content": user_msg}],
                                schema=prompts.TURN_SCHEMA, max_tokens=prompts.TURN_MAX_TOKENS, purpose="turn")
        outcome = TurnOutcome()
        data = self._call(provider, req, outcome)

        # ---- 4. Leak guard (regenerate once, then canned safe hint) -------
        guard_ctx = self._guard_context(rec, solution, include_next=advance_if_passed)
        notice = None
        if data is None:
            st["malformed_count"] = st.get("malformed_count", 0) + 1
            if st["malformed_count"] >= MALFORMED_NOTICE_AFTER:
                notice = MALFORMED_NOTICE
            return self._finish(rec, self._safe_reply(rec), kind="hint", outcome=outcome, notice=notice)

        payload = self._payload(data) if allowed else None
        if scan_all(self._texts(data, payload), guard_ctx):
            retry = StructuredRequest(
                system_blocks=system_blocks,
                messages=[{"role": "user", "content": user_msg + "\n\n" + prompts.STRICTER_NOTE}],
                schema=prompts.TURN_SCHEMA, max_tokens=prompts.TURN_MAX_TOKENS, purpose="turn-retry")
            data2 = self._call(provider, retry, outcome)
            payload = None  # no display on a regenerated reply
            if data2 is None or scan_all(self._texts(data2, None), guard_ctx):
                log.info("leak guard: substituting canned safe reply")
                passed = bool(data.get("check_passed")) and phase == "checking" and data.get("intent") != "off-topic"
                if passed:
                    return self._advance(rec, solution, reply_override=True, outcome=outcome)
                return self._finish(rec, self._safe_reply(rec), kind="hint", outcome=outcome)
            data = data2

        # ---- 5. Apply the model's labels to engine state -----------------
        reply = str(data.get("reply", "")).strip()[:1500] or self._safe_reply(rec)
        question = str(data.get("question", "")).strip()[:500]
        label = data.get("intent")
        if label == intent.Intent.OFF_TOPIC.value:
            # No state change on off-topic; the model's reply is a redirect.
            return self._finish(rec, reply, kind="redirect", outcome=outcome)

        if phase == "checking" and data.get("check_passed") is True:
            return self._advance(rec, solution, reply=reply, question=question, payload=payload, outcome=outcome)

        if (phase == "working" and v == Verdict.UNCHECKABLE and not try_parse(step.get("result_latex") or "")
                and data.get("learner_correct") == "yes"):
            # Conceptual step judged by the AI (SymPy can't check words).
            st["revealed"].append(text or latex)
            st["phase"] = "checking"
            st["display"] = None
            st["current_question"] = step["check_question"]

        if question:
            st["current_question"] = question
        if payload:
            st["display"] = payload
        elif not data.get("display_keep"):
            st["display"] = None
        st["step_just_started"] = False
        return self._finish(rec, reply, kind="tutor", outcome=outcome)

    # ================================================================ helpers

    def _call(self, provider: LLMProvider, req: StructuredRequest, outcome: TurnOutcome) -> dict | None:
        try:
            result = provider.structured(req)
        except ProviderError as err:
            raise TutorError(err.user_message, err.kind) from None
        outcome.ai_calls += 1
        outcome.usage = outcome.usage.add(result.usage)
        return result.data if (result.data and not result.malformed) else None

    @staticmethod
    def _payload(data: dict) -> dict | None:
        items = data.get("display_items") or []
        if not items:
            return None
        return display.validate_payload({"type": "latex", "title": data.get("display_title", "") or "",
                                         "items": items})

    @staticmethod
    def _texts(data: dict, payload: dict | None) -> list[str]:
        return [str(data.get("reply", "")), str(data.get("question", ""))] + display.payload_texts(payload)

    def _guard_context(self, rec: ProblemRecord, solution: Solution, include_next: bool) -> GuardContext:
        st = rec.state
        steps = rec.plan["steps"]
        idx = st["step_index"]
        targets = []
        ft = final_target(solution, rec.plan)
        if ft:
            targets.append(ft)
        if st["phase"] == "working" and idx < len(steps):
            t = step_target(steps[idx])
            if t:
                targets.append(t)
        if include_next and idx + 1 < len(steps):
            t = step_target(steps[idx + 1])
            if t:
                targets.append(t)
        return GuardContext(targets=targets, problem_latex=rec.problem_latex, revealed_latex=list(st["revealed"]))

    def _safe_reply(self, rec: ProblemRecord) -> str:
        """Canned, pre-guarded fallback: the step's safe hint + the current question."""
        st = rec.state
        steps = rec.plan["steps"]
        step = steps[min(st["step_index"], len(steps) - 1)]
        q = st["current_question"]
        if st["phase"] == "checking":
            return f"Think about why that works. {q}"
        return f"{step.get('safe_hint', '')} {q}".strip()

    def _final_already_produced(self, st: dict, solution: Solution, plan: dict) -> bool:
        for r in st.get("revealed", []):
            if solution.kind != "none":
                if check_final(r, solution) == Verdict.CORRECT:
                    return True
            elif plan.get("final_answer_latex") and check_step(r, plan["final_answer_latex"]) == Verdict.CORRECT:
                return True
        return False

    @staticmethod
    def _verdict_note(v: Verdict, st: dict, final: bool, step: dict | None = None) -> str:
        what = "final answer" if final else "answer to the current step"
        if v == Verdict.INCORRECT:
            return (f"ENGINE VERDICT: the learner's {what} is INCORRECT (verified by a CAS). "
                    f"Wrong attempts on this step: {st.get('wrong_attempts', 0)}. "
                    "Give a smaller hint or a simpler sub-question. Do not reveal the result.")
        if v == Verdict.NOT_SIMPLIFIED:
            return (f"ENGINE VERDICT: the learner's {what} is equivalent but NOT FINISHED "
                    "(they restated the expression instead of computing/simplifying it). Ask them to finish it.")
        # UNCHECKABLE
        if step is not None and not try_parse(step.get("result_latex") or ""):
            return ("ENGINE: this step is conceptual; the CAS can't check it. Judge the learner's answer and set "
                    "learner_correct. If \"yes\": acknowledge briefly and ask exactly this check question: \""
                    + step.get("check_question", "") + "\". Otherwise give a hint.")
        return ("ENGINE: the learner did not give a checkable math answer (a question, words, or confusion). "
                "Respond to it and guide them toward the current step with one question. learner_correct = \"n/a\".")

    def _advance(self, rec: ProblemRecord, solution: Solution, reply: str = "", question: str = "",
                 payload: dict | None = None, outcome: TurnOutcome | None = None,
                 reply_override: bool = False) -> dict:
        """Check passed -> next step, final phase, or done."""
        st = rec.state
        steps = rec.plan["steps"]
        idx = st["step_index"]
        outcome = outcome or TurnOutcome()
        if idx + 1 < len(steps):
            nxt = steps[idx + 1]
            st.update(step_index=idx + 1, phase="working", wrong_attempts=0, step_just_started=True)
            st["display"] = payload  # wiped on advance; only a new-step example may replace it
            st["current_question"] = question or nxt["first_question"]
            if reply_override or not reply:
                reply = f"{_ack(rec.level)} Step {idx + 2}: {nxt['first_question']}"
                st["current_question"] = nxt["first_question"]
            return self._finish(rec, reply, kind="tutor", outcome=outcome)
        # Last step passed.
        if self._final_already_produced(st, solution, rec.plan):
            done_reply = reply if (reply and not reply_override) else f"{_ack(rec.level)} You solved the problem."
            return self._complete(rec, done_reply, outcome=outcome)
        st.update(phase="final", wrong_attempts=0, step_just_started=False, display=None)
        final_q = "What's the final answer to the original problem?"
        st["current_question"] = question or final_q
        if reply_override or not reply:
            reply = f"{_ack(rec.level)} {final_q}"
            st["current_question"] = final_q
        return self._finish(rec, reply, kind="tutor", outcome=outcome)

    def _complete(self, rec: ProblemRecord, reply: str, outcome: TurnOutcome | None = None) -> dict:
        st = rec.state
        st.update(phase="done", display=None, current_question="")
        st["step_index"] = len(rec.plan["steps"])
        rec.status = "completed"
        return self._finish(rec, reply, kind="done", outcome=outcome or TurnOutcome())

    def _finish(self, rec: ProblemRecord, reply: str, kind: str, outcome: TurnOutcome,
                notice: str | None = None) -> dict:
        rec.transcript.append({"role": "tutor", "text": reply, "kind": kind})
        rec.transcript = rec.transcript[-context_builder.TRANSCRIPT_KEEP:]
        rec.ai_calls += outcome.ai_calls
        u = outcome.usage
        rec.tokens_in += u.input_tokens + u.cache_read_tokens + u.cache_write_tokens
        rec.tokens_out += u.output_tokens
        rec.summary = context_builder.summary(rec.plan, rec.state)
        self.storage.save_problem(rec)  # autosave after every turn (§10)
        view = self.view(rec, notice=notice)
        view["turn_ai_calls"] = outcome.ai_calls
        return view

    # ================================================================ view

    @staticmethod
    def view(rec: ProblemRecord, notice: str | None = None) -> dict:
        """Everything the UI needs. Never includes step results or the answer."""
        st = rec.state
        steps = rec.plan["steps"]
        completed = rec.status == "completed"
        return {
            "id": rec.id,
            "title": rec.title,
            "problem_latex": rec.problem_latex,
            "level": rec.level,
            "status": rec.status,
            "phase": st["phase"],
            "step_index": min(st["step_index"], len(steps)),
            "step_count": len(steps),
            "steps": display.steps_checklist(steps, st["step_index"], completed),
            "current_question": st.get("current_question", ""),
            "display": st.get("display"),
            "transcript": [{"role": e["role"], "text": e["text"], "kind": e.get("kind", "")} for e in rec.transcript],
            "usage": {"tokens_in": rec.tokens_in, "tokens_out": rec.tokens_out, "ai_calls": rec.ai_calls},
            "notice": notice,
            "updated_at": rec.updated_at,
        }

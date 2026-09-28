# MathAssistant — build rules

Source of truth: `docs/MATH_TUTOR_SPEC.md` (v0.2). Phase prompts live in `docs/`. The spec wins over any prompt.

## Non-negotiables (summary — see spec §2)

- **N1** Never display the final answer (text or display box) before the learner produces it.
- **N2** One step per turn, via a question or hint. Never solve for the learner.
- **N3** Every problem gets a step plan before tutoring.
- **N4** A step advances only after a correct answer **and** a passed check-understanding question.
- **N5** Questions target the current step.
- **N6** Register = the problem's math level (L1–L5), not the user's age.
- **N7** Off-topic → one short redirect + current question. Obvious cases: local, zero AI calls.
- **N8** SymPy decides correctness. Never trust model arithmetic.
- **N9** API key lives only in the OS credential store (`keyring`). Never in DB, config, logs.
- **N10** No telemetry. Only outbound traffic: the selected AI provider (+ optional update check, Phase 3).
- **N11** Fewest, smallest AI calls: 1 per turn, 1 at intake, 0 on resume, 0 for obvious off-topic.

## Build rules

- Don't add an AI call beyond spec §7.5 without explicit approval.
- Only MIT-compatible dependencies (MIT/BSD/Apache-2.0). No GPL/AGPL. Check the license before adding.
- Bundle all frontend libraries; no CDN scripts.
- Malformed display payloads → empty box, logged, no crash.
- All user data under `platformdirs`; resolve resources for both dev and PyInstaller (`backend/mathassistant/paths.py`).
- Internal app ID is `mathassistant` (keyring service + data folder). **Never change it** — doing so orphans saved problems and stored keys.
- Public repo: never commit a key, even temporarily. A key that lands in history is leaked and must be revoked.

## Dev commands

```
# one-time
python -m venv .venv && .venv/Scripts/pip install -e "backend[dev]"   # macOS: .venv/bin/pip
cd web && npm install

# run (builds web if stale, starts server on 127.0.0.1, opens browser)
.venv/Scripts/python -m mathassistant

# tests
.venv/Scripts/python -m pytest backend/tests
cd web && npm test
```

## Phase status

| Phase | Status |
|---|---|
| 1 — Core loop (dev mode) | In progress |
| 2 — Image/PDF input | Not started (needs approval) |
| 3 — Packaging | Not started |
| 4 — Richer visuals | Not started |
| 5 — More providers | Not started |

## Decision log

- 2026-09-28 — App name **MathAssistant**; internal ID `mathassistant`.
- 2026-09-28 — Default model `claude-haiku-4-5` (cost). `claude-sonnet-5` selectable. Haiku stays default only if it passes the §14 tutoring acceptance tests with clear math communication; otherwise switch default to Sonnet 5.
- 2026-09-28 — No token streaming in Phase 1: full reply is buffered, leak-guarded, then sent as JSON (spec §7.3 forbids showing unguarded text). Structured JSON from the model is internal only; the learner sees only rendered reply text + validated display payloads.
- 2026-09-28 — Transcript summary is code-generated (no extra AI call).
- 2026-09-28 — LaTeX parsing via SymPy `parse_latex(backend="lark")` (MIT `lark`), not `latex2sympy2` (pins stale deps).
- 2026-09-28 — Prompt caching: Haiku 4.5 minimum cacheable prefix is 4096 tokens; our prompts are shorter, so caching is a no-op on Haiku (still marked; applies on Sonnet 5 at ≥1024).
- 2026-09-28 — Default branch `main`; `.idea/` and `*.iml` git-ignored.

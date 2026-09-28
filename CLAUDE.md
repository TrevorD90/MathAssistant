# MathAssistant — build rules

Source of truth: `docs/MATH_TUTOR_SPEC.md` (v0.2). Phase prompts live in `docs/`. The spec wins over any prompt.

## Non-negotiables (summary — see spec §2)

- **N1** Never display the final answer (text or display box) before the learner produces it.
- **N2** One step per turn, via a question or hint. Never solve for the learner.
- **N3** Every problem gets a step plan before tutoring.
- **N4** (amended 2026-09-28) A correct answer advances immediately. Only after a mistake on that step does a why/how check question have to be passed first.
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

# build the downloadable app for this OS (see docs/DEVELOPING.md)
.venv/Scripts/python packaging/build.py

# tests
.venv/Scripts/python -m pytest backend/tests          # offline suite (live tests deselected)
.venv/Scripts/python -m pytest backend/tests/live -m live -s   # real API, costs a little
cd web && npm test

# offline UI demo (no key, no AI)
DEV_MODE=true MATHASSISTANT_DEMO=1 .venv/Scripts/python -m mathassistant
```

## Phase status

| Phase | Status |
|---|---|
| 1 — Core loop (dev mode) | Built 2026-09-28; awaiting live acceptance run with a real key |
| 2 — Image/PDF input | Built 2026-09-28 (camera, upload, paste, PDF, crop, vision, confirm); live camera + real-vision check pending |
| 3 — Packaging | Done — v0.3.0 released 2026-09-28 |
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
- 2026-09-28 — SymPy-verified correct step answers get a canned "Correct." + the plan's pre-written check question (0 AI calls). Correct final answers complete with 0 AI calls. AI is called only when judgment is needed.
- 2026-09-28 — Own LaTeX translator for answers; SymPy's Lark parser only for calculus notation (it misreads `\sin(x^2)x` as `sin(x^3)`).
- 2026-09-28 — Leaking plan strings at intake are replaced with generic safe text (no extra AI call).
- 2026-09-28 — Both Anthropic models start `tested=False` until the live suite passes (UI shows the untested warning meanwhile).
- 2026-09-28 — Dev-only offline DemoProvider (`DEV_MODE=true MATHASSISTANT_DEMO=1`), never active in bundled builds.
- 2026-09-28 — Off-topic pre-check is conservative: needs no math content AND a positive off-topic cue; uncertain messages go to the AI.
- 2026-09-28 — N4 amended by the user: correct answers are accepted immediately; a check question is asked only after a wrong attempt on that step. Correct final answer = solved.
- 2026-09-28 — Phase 3 approved and built. Mac: separate Apple Silicon (macos-15) and Intel (macos-15-intel) builds, not universal2 (§15 #4). Update check ON by default, toggle in Settings (§15 #5). Windows ships as a zipped onedir folder (no installer; faster start than onefile, fewer AV false positives). Control window via tkinter (stdlib). pystray rejected (LGPL). UPX off.
- 2026-09-28 — Haiku 4.5 marked tested after the user's live acceptance run; Sonnet 5 still untested.
- 2026-09-28 — Worksheets: vision lists all problems (≤20/image); learner picks one; the rest go to "Up next" (queued_problems table, migration v3, no AI cost until started). PDF "Read all pages" ≤10 pages.
- 2026-09-28 — Phase 2 approved and built. Fixed default port 51789 (user choice) so camera permission persists; fallback to a free port.
- 2026-09-28 — Vision extraction is transcription only (never solves); result must be confirmed by the learner before the intake call. Images never stored/logged.
- 2026-09-28 — Crop UI built in-house (no library). pdf.js 6.3 bundled; CSP gains 'wasm-unsafe-eval' + worker-src for it.
- 2026-09-28 — Word problems added: plain-text entry; intake returns `math_formulation_latex`; SymPy solves it and wins over the model. Migration v2 adds `problem_kind`.
- 2026-09-28 — Answers are routed against final answer → current step → later steps (learners may work ahead). Numbers pulled from prose can confirm but never count as wrong.

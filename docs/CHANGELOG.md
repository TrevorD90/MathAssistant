# Changelog

## Unreleased

### Added — 2026-09-28: worksheets with several problems
- The vision call now lists **every problem** in the image (up to 20, reading order, printed labels, never solved). One problem → straight to confirm; several → a **picker** to choose which to start with.
- The rest can be saved to **Up next** (checkbox, on by default): stored as text only, **no AI cost** until started. My problems shows Up next; starting one pre-fills the entry screen to confirm, and it leaves the list once started.
- **Read all pages** for multi-page PDFs (up to 10 pages, one vision call per page), merged with page labels ("p2 #3"). All page reads count toward the usage of the problem started from them.
- Cropping is optional: read the whole page to choose from all problems.
- Migration v3: `queued_problems` table. Delete all problems also clears Up next.

### Phase 2 — Image/PDF input — 2026-09-28
- **Camera** (webcam via `getUserMedia`), **photo/screenshot upload**, **clipboard paste** (Ctrl+V on the entry screen), and **PDF** (pdf.js, pick a page). All four go through the same **crop** step, then **one vision call** (`POST /api/extract`) that transcribes the problem (math → LaTeX, word problem → text, never solved). The result loads into the normal entry fields to **confirm or edit**; tutoring starts only on Start.
- Images are cropped and downscaled in the browser (≤1568 px side, ≤1.15 MP; PNG, JPEG for large photos), validated server-side (type, signature, 5 MB), sent to the provider once, and **never stored or logged** (tested).
- The vision call's tokens are added to the problem's usage meter when it starts (counted once).
- **Capability gating:** Test key now probes image support and structured output in one tiny call; image inputs are disabled with an explanation for models that can't read images.
- **Fixed port 51789** (falls back to a free port if taken) so the browser remembers camera permission.
- Security headers: `Permissions-Policy: camera=(self)` (no microphone/location); CSP allows same-origin workers and `'wasm-unsafe-eval'` for pdf.js's bundled decoders (no JS `eval`). `.mjs`/`.wasm` served with correct MIME types on Windows.
- UI robustness: MathLive fields receive their initial value as content and defer focus (a freshly mounted field could crash the app); an error boundary replaces a blank screen with a Reload prompt; the cropper finishes a selection on pointer release.
- pdf.js 6.3 (Apache-2.0) with its WASM decoders (BSD/Apache/MIT), fonts and CMaps bundled under `/pdfjs/`; loaded only when a PDF is opened.

### Added — 2026-09-28
- `$` handling: inline math uses the Pandoc rule (opening `$` followed by a non-space; closing `$` after a non-space and not before a digit), so money in word problems ("$5 and a $2 toy") renders as text. The word-problem box no longer suggests `$` for math.
- Word problems: a "Word problem" option on the entry screen (plain text, `$…$` math allowed). The intake call also returns `math_formulation_latex` (e.g. `3	imes 12`); SymPy computes the answer from it and overrides the model's answer and last step result (N8). Still one AI call at intake. Problems SymPy can't formulate (proofs, explanations) fall back to the model's stated answer, as §7.1 allows.
- Answers with units or currency are accepted: "36 apples", `36	ext{ apples}`, `\$4.50`.
- Off-topic pre-check treats words from the problem text as on-topic ("dogs" in a dog word problem).
- Schema migration v2: `problems.problem_kind` ('math' | 'words'); existing problems become 'math'.

### Changed — 2026-09-28
- N4 amended: a correct answer is accepted and the tutor moves on immediately (a correct final answer solves the problem). A why/how check question is asked only if the learner got that step wrong first. Conceptual (AI-judged) steps follow the same rule; AI-judged wrong answers now count as attempts.

### Fixes — 2026-09-28 (first live session, `lim x→2 (8−3x+12²)`)
- Correct answers were graded INCORRECT when they belonged to a later step or were the final answer (the tutor said "your arithmetic doesn't match" to 146). New `engine/answer_router.py` checks final answer → current step → later steps; the learner can jump ahead (0 AI calls) and is never told a correct value is wrong.
- Equation-shaped step results (`12^2 = 144`, `8 + 144 - 3x = 152 - 3x`) now accept the plain value (`144`). Unevaluated planned results (`152 - 3(2)`) accept any equivalent form.
- Answer chains (`152-3(2) = 152 - 6 = 146`) and answers in words ("152 - 6 is 146", "it's 146") are read. Numbers pulled from prose can confirm an answer but never count as a wrong attempt.
- Leak guard: anything the learner typed may be echoed back (typing `146` unlocks 146; typing `152 - 3(2)` does not). This stopped the repeated canned "Calculate 12 times 12" hint.
- Display box: captions/titles render `$…$` math instead of showing raw dollar signs.

### Phase 1 — Core loop (dev mode) — 2026-09-28

**Repo**
- MIT license, `.gitignore` (env, databases, build output, IDE), `.env.example`, `CLAUDE.md`, `docs/ARCHITECTURE.md`.

**Local server (§3.1)**
- FastAPI + Uvicorn on 127.0.0.1, free port bound directly (no race), per-launch session token (URL fragment → sessionStorage → `X-Session-Token`), Host-header allowlist, cross-origin rejection, CSP + security headers, Quit endpoint. `python -m mathassistant` builds the web app when stale and opens the browser.

**Tutoring engine (§6–§8)**
- LaTeX → SymPy: safe translator for answers (implicit multiplication, `\sin(x^2)x` read correctly) + SymPy's Lark parser for calculus.
- SymPy solver: numbers, expressions, antiderivatives (+C), equation solution sets; `none` fallback to the model's stated answer.
- Answer checking by SymPy: equivalence, decimal rounding tolerance (≥2 places), "not simplified" detection (`5\times5` for 25, `14/16`, restated problem).
- Intake: one AI call for level + step plan (title, goal, result, first question, check question, safe hint per step). SymPy's answer overrides the model's. Plan strings are leak-guarded at intake.
- Turn loop: working → checking → final → done. Correct step answers and final answers verified by SymPy cost 0 AI calls.
- Leak guard: numbers, number words, assertions ("x = 2") when the answer appears in the problem, SymPy-equivalent expressions in LaTeX and plain text, text fallback. One regenerate, then a canned safe hint.
- Off-topic: conservative local pre-check (0 AI calls) + model intent label.
- Display box: `latex` payloads (schema-validated, gated per §9.1, wiped per §9.2) + local `steps` checklist.

**Providers & key (§11)**
- `LLMProvider` interface with capability flags; Anthropic adapter (structured output via `output_config.format`, prompt-cache breakpoints, error mapping to key-free messages, capability probe with prompt-JSON fallback).
- Key in the OS credential store via `keyring`; plaintext backends refused; secrets scrubbed from every log record.
- Default model `claude-haiku-4-5`; `claude-sonnet-5` selectable; custom model IDs behind the untested warning.

**Storage (§10)**
- SQLite under platformdirs, `PRAGMA user_version` migrations (refuses newer schemas), autosave every turn, resume with 0 AI calls, delete single/all.

**Frontend**
- React 18 + TS + Vite + Zustand. MathLive field with five custom keyboard tabs (Basic, Algebra, Functions, Calculus, Advanced; nested exponents). KaTeX conversation rendering. Display box, My problems, Settings (onboarding, provider/model, key show/hide, Test/Remove key, untested warning, usage meter, delete all), Quit.

**Tests**
- Backend: 129 passing (all §14 items that don't need a live model, plus unit tests for parsing, equivalence, guard, pre-check, display schema). Live acceptance suite in `backend/tests/live` (`-m live`, needs a key).
- Frontend: 6 passing (math splitting/rendering safety, payload validation, keyboard coverage).

**Dev-only**
- Offline demo provider (`DEV_MODE=true MATHASSISTANT_DEMO=1`) for UI work without a key.

# Changelog

## Unreleased

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

# Build Prompt — Math Tutor, Phase 1 (Core Loop, dev mode)

You are building Phase 1 of a math-only Socratic tutor that runs locally on the user's computer. The full spec is `docs/MATH_TUTOR_SPEC.md` (v0.2). Project root: `C:\Users\seren\IdeaProjects\MathAssistant`. Read it completely before doing anything. The spec wins over this prompt if they conflict.

## Step 0 — mandatory, before any code

1. Restate, in your own words:
   - The non-negotiables N1–N11.
   - The architecture: local Python server on 127.0.0.1 serving the React frontend, opened in the user's browser (spec §3, §3.1).
   - Phase 1 scope and what is explicitly **out** of scope: image/PDF input, packaging/installers, graphs, diagrams, providers other than Anthropic, voice, personalities, profiles.
   - Your stack and any deviation from spec §3.
   - Your file/module plan, including the repo layout (spec §3.2).
   - Confirmation that this is a **new standalone repo** with no dependency on Whiskers/`DesktopCompanion`.
2. List any open decisions from spec §15 that block Phase 1, with your recommended default for each.
3. **Stop and wait for explicit confirmation.** Do not write code until the user approves.

## Phase 1 scope

0. **Repo setup** per spec §3.2: `CLAUDE.md`, `docs/ARCHITECTURE.md` and `docs/CHANGELOG.md` (the spec and this prompt are already in `docs/`), `.gitignore` (covers `.env`, local databases, build output), `.env.example`, `LICENSE` (MIT, `Copyright (c) 2026 Trevor Davis`), backend and web scaffolds. The repo is **public**: remind the user to enable secret scanning and push protection before the first push, and never commit a key.
1. **Local server** (spec §3.1): FastAPI + Uvicorn bound to 127.0.0.1 on a free port; per-launch session token required on every API request; `Host` header check; serves the built frontend; a dev command that starts everything and opens the browser.
2. **Frontend** (React 18 + TS + Vite + Zustand)
   - MathLive `<math-field>` with the custom keyboard: Basic, Algebra, Functions, Calculus, Advanced tabs (spec §5). Nested exponents must work.
   - Conversation pane (KaTeX-rendered math).
   - Display box: `latex` and `steps` only, gated and wiped per spec §9.1–9.2.
   - **My problems** screen (In progress / Completed, delete, delete all).
   - Settings → AI provider: onboarding, key entry, Test key, Remove key, untested-model warning, usage meter.
   - A **Quit** control that stops the local server.
3. **Backend**
   - LaTeX → SymPy parse and solve.
   - Intake: one AI call for level (§6) + step plan (§7.1).
   - Turn loop (§7.2) with SymPy answer checking (§7.4).
   - Answer-leak guardrail on all text and display payloads (§7.3).
   - Intent label inside the single turn response, plus the local off-topic pre-check (§8).
   - Cost controls (§7.5): one AI call per turn, compact context, prompt caching, capped output.
   - Provider adapter interface with capability flags, and the Anthropic adapter (§11.2).
   - Key storage with `keyring`, redaction, error scrubbing (§11.1).
   - SQLite storage in the `platformdirs` app-data folder, versioned migrations, autosave, resume with no AI call (§10).
4. **Tests:** every item in spec §14, plus unit tests for the guardrail, SymPy equivalence, and the off-topic pre-check.

## Rules for this build

- The final answer and step results are never displayed until the learner has produced them.
- Tone is neutral and direct at every level. No personalities, no small talk.
- Don't use the AI to decide whether math is correct when SymPy can.
- Don't add an AI call where code can do the job. Any AI call beyond spec §7.5 needs explicit approval.
- The API key lives only in the OS credential store. Never in the database, config files, `.env` (except the dev key under `DEV_MODE=true`), or logs.
- No telemetry, analytics, or outbound calls other than the selected AI provider.
- Bundle all frontend libraries at build time; no CDN scripts.
- Only add dependencies with MIT-compatible licenses (spec §3.2). No GPL/AGPL libraries.
- Malformed display payloads → empty box, logged, no crash.
- Keep modules small and named for their job (e.g. `step_planner.py`, `leak_guard.py`, `answer_check.py`, `intent.py`, `storage.py`, `key_store.py`).
- Write code that will package cleanly with PyInstaller in Phase 3: resolve file paths for both dev and bundled modes, and put all user data under `platformdirs`, never next to the executable.

## End of session

- Run all tests; report pass/fail.
- Update `docs/CHANGELOG.md` with what was built.
- List anything deferred or any spec ambiguity you hit.
- Do not start Phase 2 without explicit approval.

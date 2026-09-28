# Architecture (Phase 1)

MathAssistant is a local web app. `python -m mathassistant` starts a FastAPI server on `127.0.0.1:<free port>` and opens the browser at `/#token=<per-launch token>`. The React frontend is built to static files and served by the same server. Nothing is hosted.

```
browser (React + MathLive + KaTeX)
   │  JSON over HTTP, X-Session-Token header
   ▼
FastAPI (security middleware → routes → Services)
   ├── TutorEngine (engine/turn_loop.py)
   │     ├── step_planner   — SymPy solve + 1 AI intake call → level + step plan
   │     ├── answer_check   — SymPy equivalence (never the model)
   │     ├── intent         — local off-topic pre-check (0 AI calls)
   │     ├── leak_guard     — scans every reply / display payload
   │     ├── display        — payload schema, gating, checklist
   │     └── context_builder/prompts — compact, cache-ordered AI context
   ├── providers/ (LLMProvider interface → AnthropicProvider; FakeProvider for tests; DemoProvider dev-only)
   ├── key_store (keyring → Windows Credential Manager / macOS Keychain)
   └── storage (SQLite under platformdirs, versioned migrations)
```

## Backend modules (`backend/mathassistant/`)

| Module | Job |
|---|---|
| `__main__.py` | Dev command: builds `web/` if stale, then `server.run()` |
| `server.py` | Binds a socket on 127.0.0.1 (port 0 → free port, handed straight to Uvicorn), makes the session token, opens the browser, Quit hook |
| `security.py` | Host-header allowlist, session-token check on `/api/*`, cross-origin `Origin` rejection, CSP and other security headers |
| `app.py` | FastAPI factory; mounts API + built SPA; no OpenAPI/docs routes |
| `services.py` | Settings (provider/model/verified flag/capabilities), provider construction, Test key / Remove key, status |
| `api/routes.py` | HTTP endpoints (see below) |
| `paths.py` | Dev vs PyInstaller resource paths; platformdirs data/log dirs. `APP_ID = "mathassistant"` (never change) |
| `config.py` | `DEV_MODE`, dev-only `.env` key, fixed port, no-browser flag |
| `log_redact.py` | Record factory + handler filter that scrub registered secrets and key-shaped strings; rotating log file |
| `key_store.py` | keyring wrapper; refuses fail/plaintext backends |
| `storage.py`, `migrations.py` | SQLite (`PRAGMA user_version` migrations), problems + non-secret settings |
| `engine/latex_parse.py` | LaTeX → SymPy. Own translator for answers (safe whitelist, implicit multiplication); SymPy's Lark parser for calculus notation |
| `engine/solver.py` | Computes the answer: number / expression / antiderivative / solutions / none |
| `engine/answer_check.py` | Verdicts: correct / not simplified / incorrect / uncheckable |
| `engine/leak_guard.py` | Number, number-word, assertion, expression-equivalence and text scans |
| `engine/intent.py` | Conservative off-topic pre-check + canned redirect |
| `engine/display.py` | `latex` payload schema, §9.1 gating, `steps` checklist |
| `engine/step_planner.py` | Intake call, plan validation, SymPy-wins override, guards plan strings |
| `engine/turn_loop.py` | The state machine (working → checking → final → done) |
| `engine/prompts.py` | System prompts, JSON schemas, token caps |
| `engine/context_builder.py` | Per-problem context block, code-built summary, last 6 turns |

## A turn

1. **Off-topic pre-check** (text only). Obvious → canned redirect + current question. **0 AI calls.**
2. **SymPy check** of the learner's math against the current step result (last step: against the SymPy answer).
   - Correct → canned "Correct." + the plan's check question. **0 AI calls.** Display wiped.
   - Correct final answer → problem completed. **0 AI calls.**
3. Otherwise **one AI call** with ENGINE NOTES (verdict, attempts, phase, whether a display payload is allowed). Returns `{intent, reply, question, learner_correct, check_passed, display_*}`.
4. **Leak guard** on reply, question and display payload. Hit → regenerate once with a stricter note; a second hit → the step's pre-guarded safe hint (or a canned step advance if the check had passed).
5. Engine applies labels: off-topic → no state change; `check_passed` → advance (display wiped); conceptual `learner_correct` → checking.
6. Autosave; transcript trimmed to 24 entries.

## AI calls (N11)

| Event | Calls |
|---|---|
| Start a problem | 1 (intake: level + plan) |
| Normal tutoring turn | 1 |
| Leak detected | +1 (one regenerate), then canned |
| SymPy-verified correct step / final answer | 0 |
| Obvious off-topic | 0 |
| Resume / list / delete | 0 |

Prompt order for caching: fixed system prompt → per-problem context (both `cache_control`) → one user message with recent turns + notes. Caching is a no-op on Haiku 4.5 (4096-token minimum prefix); it applies on Sonnet 5 (1024).

## API (all require `X-Session-Token`)

| Method | Path | |
|---|---|---|
| GET | `/api/status` | key/model/tested status |
| GET | `/api/providers` | provider/model catalog |
| POST | `/api/settings/model` | choose provider + model (resets "verified") |
| POST | `/api/key/test` | probe key (+ store it on success) |
| DELETE | `/api/key` | remove key |
| GET/POST/DELETE | `/api/problems` | list / start / delete all |
| GET/DELETE | `/api/problems/{id}` | resume (0 AI calls) / delete |
| POST | `/api/problems/{id}/turn` | `{text}` or `{latex}` |
| POST | `/api/quit` | stop the server |

## Frontend (`web/src/`)

- `api/client.ts` reads `#token=` into `sessionStorage` and strips it from the URL; every request sends it.
- `store/app.ts`: Zustand store (screen, status, current problem view, busy/error).
- `components/MathInput.tsx`: `<math-field>` with the five custom keyboard tabs (`keyboard/layouts.ts`). Fonts are copied into the build; no sounds, no CDN.
- `components/MathText.tsx`: KaTeX rendering of `$…$` segments (`trust: false`), plain text as React text.
- `components/DisplayBox.tsx`, `TutorScreen.tsx`, `ProblemsScreen.tsx`, `Settings.tsx`.

## Data locations

- Database: `platformdirs.user_data_dir("mathassistant")/mathassistant.sqlite3` (Windows: `%LOCALAPPDATA%\mathassistant`).
- Logs: `platformdirs.user_log_dir("mathassistant")` (rotating, redacted).
- Key: OS credential store, service `mathassistant`, user `anthropic-api-key`.

## Dev-only switches

- `DEV_MODE=true` + `ANTHROPIC_DEV_API_KEY` in `.env`: dev key fallback.
- `DEV_MODE=true` + `MATHASSISTANT_DEMO=1`: offline canned provider for UI work (no AI, no network).
- `MATHASSISTANT_PORT`, `MATHASSISTANT_NO_BROWSER`, `MATHASSISTANT_DATA_DIR`, `MATHASSISTANT_KEYRING_SERVICE` (tests).

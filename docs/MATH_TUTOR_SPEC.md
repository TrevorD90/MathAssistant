# Math Tutor — Design Spec (v0.2)

> Working name TBD. A math-only Socratic tutor for all ages that runs **entirely on the user's own computer** (Windows or Mac).
> Current audience: the author's kids and a friend. Not a commercial product for now.
> This document is the source of truth for build sessions. Non-negotiables come first and apply to every phase.
>
> **v0.2 replaces v0.1.** Removed: hosting, voice, personalities, profiles, server-side key handling. The app is now a local download.

---

## 1. Purpose

A focused math tool that helps a learner solve a problem **themselves**. The learner submits a problem (typed, photo, screenshot, or PDF). The tutor breaks it into steps, guides with questions, and checks understanding. It never hands over the answer.

It is a **math program, not a chatbot.** Anything that isn't about the current problem or math is redirected.

People use this because they want help learning math, not answers. The design keeps the tutor from giving answers away; it does not try to stop a determined user from finding them.

---

## 2. Non-negotiables (encode in prompt + code, never infer)

| # | Rule | Enforcement |
|---|------|-------------|
| N1 | **Never give the final answer**: not in text, not in the display box. | System prompt · answer-leak guardrail (§7.3) · display-box validator |
| N2 | **Guide, don't solve.** Each turn advances the learner by at most one step, via a question or a hint. | System prompt · step-engine state (§7.2) |
| N3 | **Break every problem into steps** before tutoring begins. | Step plan per problem (§7.1) |
| N4 | **Verify understanding with questions** when a learner struggled: after a mistake on a step, a correct answer is followed by one why/how check before moving on. A correct answer with no mistakes is accepted immediately (amended 2026-09-28). | Step engine requires a passed check to advance only after a wrong attempt |
| N5 | **Questions must be relevant** to the current step of the current problem. | System prompt · step plan supplies the check target |
| N6 | **Register matches the math level** of the problem, not the user's age (§6). | Level set per problem at intake |
| N7 | **Stay on task.** Off-topic messages get a short, direct redirect. No engagement. | Intent label per turn + local pre-check (§8) |
| N8 | **Math correctness is computed, not guessed.** Answers and learner responses are checked with SymPy, not the model's arithmetic. | SymPy verification (§7.4) |
| N9 | **The user's API key stays on their computer.** It is stored in the OS credential store and sent only to the provider they chose. Never logged. | §11 |
| N10 | **Local only.** No telemetry, analytics, or accounts. The only outbound traffic is to the user's AI provider, plus the optional update check (§12.4). | Code review · tests |
| N11 | **Keep AI cost low.** Default to fewer, smaller AI calls; use code wherever code can do the job. | §7.5 · call-count tests |

---

## 3. Architecture & stack (confirm in Step 0)

**Shape:** a local web app. The user double-clicks the app; it starts a small Python server on their own machine and opens their default browser to it. Nothing is hosted anywhere.

- **Backend:** Python, FastAPI + Uvicorn (HTTP + SSE for streaming tutor replies). Also serves the built frontend as static files.
- **Frontend:** React 18 + TypeScript + Vite + Zustand, built to static files at release time.
- **Math input:** [MathLive](https://cortexjs.io/mathlive/) `<math-field>` with a custom virtual keyboard (§5). Emits LaTeX.
- **Math rendering:** KaTeX.
- **PDF handling:** pdf.js in the browser (render page, select page, crop to the problem).
- **CAS:** SymPy, with its LaTeX parser (or `latex2sympy2`) for solving and answer checking.
- **Database:** SQLite, one file in the user's app-data folder (§10).
- **Key storage:** Python `keyring` → Windows Credential Manager / macOS Keychain.
- **App-data location:** `platformdirs` (`user_data_dir`) so data survives app updates.
- **AI:** bring your own key; provider adapter layer, Anthropic first (§11).
- **Packaging:** PyInstaller, one build per OS, built by GitHub Actions (§12).

### 3.1 Local server rules

- Bind to **127.0.0.1 only**, never `0.0.0.0`; other devices on the network can't reach it.
- Pick a free port at launch.
- **Per-launch session token:** generated at startup, included in the URL the launcher opens, stored by the frontend, and required on every API request. Also validate the `Host` header. This stops other websites open in the same browser from calling the local API (which has access to the user's key).
- Closing the app window/tray icon (or a **Quit** button in the UI) stops the server.
- Camera access works without HTTPS because browsers treat `localhost`/`127.0.0.1` as a secure context.

### 3.2 Repo layout (proposed)

```
<repo>/
  CLAUDE.md              # build rules, phase status, decision log
  README.md              # includes first-run steps for Windows and Mac (§12.3)
  docs/
    MATH_TUTOR_SPEC.md   # this document
    PHASE1_BUILD_PROMPT.md
    ARCHITECTURE.md
    CHANGELOG.md
  backend/               # Python: server, tutoring engine, SymPy, guardrail, storage
    tests/
  web/                   # React + TS + Vite frontend
  packaging/             # PyInstaller specs, icons
  .github/workflows/     # Windows + Mac release builds
  .env.example           # dev-only settings; names only, never values
```

- `.env` is git-ignored. A dev API key in `.env` is used only when `DEV_MODE=true`.
- **Public repo (decided).** Before the first push:
  - turn on GitHub **secret scanning** and **push protection**;
  - confirm `.gitignore` covers `.env`, local databases, and build output;
  - never commit a key, even temporarily. A key that ever lands in history is treated as leaked and must be revoked, not just deleted.
- **License (decided): MIT.** `LICENSE` at the root, `Copyright (c) 2026 Trevor Davis`.
  - Dependencies must be MIT-compatible (MIT, BSD, Apache-2.0, etc.). Current picks are: MathLive, KaTeX, FastAPI, keyring, platformdirs (MIT); SymPy (BSD); pdf.js (Apache-2.0). PyInstaller's GPL has a bootloader exception that allows bundled apps under any license.
  - Avoid GPL/AGPL libraries (e.g. PyMuPDF is AGPL). Any new dependency's license is checked before adding it.

---

## 4. Problem input

Four input paths, all ending in the **same confirmation step**:

1. **Type it:** MathLive field + math keyboard, or a **word problem** in plain text (added 2026-09-28; the intake call also translates it to math so SymPy computes the answer).
2. **Take a picture:** webcam via the browser (`getUserMedia`), or upload a photo file (e.g. taken on a phone and moved to the computer).
3. **Screenshot:** paste from clipboard or upload an image file.
4. **PDF:** rendered with pdf.js; learner picks the page.

For 2–4, the learner **crops to the one problem** before extraction, or reads the whole page: the AI then lists every problem on it and the learner picks one to start with; the rest can be saved to an **Up next** list (no AI cost until started). A multi-page PDF can be read page by page (one vision call per page, up to 10). (Amended 2026-09-28.)

**Confirmation step (required for 2–4):** the AI (vision) extracts the problem as LaTeX → loaded into the MathLive field → learner confirms or edits before tutoring starts. Extraction runs **once per problem**.

Only the confirmed LaTeX is saved. Images and PDFs are not stored.

---

## 5. Math keyboard

MathLive virtual keyboard with custom layouts, switchable by tabs:

| Tab | Keys (minimum) |
|-----|----------------|
| **Basic** | 0–9, + − × ÷, =, ( ), fraction, decimal, %, negative |
| **Algebra** | x, y, z, a, b, n; xⁿ, subscript, √, ⁿ√, \|x\|, ≤ ≥ ≠ <, ± |
| **Functions** | sin cos tan, sec csc cot, arcsin arccos arctan, log, logₙ, ln, eˣ, π, f(x), g(x) |
| **Calculus** | d/dx, dⁿ/dxⁿ, ∂/∂x, ∫, ∫ₐᵇ, lim (x→a), Σ, Π, ∞, f′, f″, Δ |
| **Advanced** | nested exponents (x^{y^{z}}), matrix/vector, !, ⁿCᵣ, θ φ α β λ μ σ, ∈ ∪ ∩, → |

- Nested exponents must work.
- Physical keyboard input works alongside the virtual one.
- The same field is used for **learner answers**, not just the initial problem.

---

## 6. Level calibration

At intake, the problem's math level is classified. The level sets the **register** for every question and explanation on that problem.

| Level | Examples | Register |
|-------|----------|----------|
| L1 Early elementary | 5×5, 12+9 | Short sentences, concrete objects (groups, arrays), one idea per question |
| L2 Upper elementary | fractions, long division | Simple language, visual models |
| L3 Middle school | ratios, one-step equations, integers | Plain language; terms introduced with definitions |
| L4 High school | algebra, geometry, trig, functions | Standard math vocabulary; expects notation |
| L5 College / adult | calculus, linear algebra, stats | Adult peer tone, precise terminology, assumes prerequisites |

- Calibrate on the **problem**. An adult doing 5×5 gets L1-style questions.
- **Fully automatic (decided).** No manual override in Settings.
- Tone at every level is **neutral and direct**: clear, encouraging where earned, never chatty.

---

## 7. Tutoring engine

### 7.1 Step plan
On confirm:
1. Parse the LaTeX into SymPy and compute the answer.
2. One AI call produces the level (§6) **and** the step plan: ordered steps, each with a goal, its intermediate result, and a check-question target.
3. Store the plan with the problem (§10). The UI shows only step titles as they unlock. The answer and step results are never displayed until the learner produces them.

If SymPy can't parse or solve it (word problems, proofs), the plan still generates; the leak guardrail then falls back to matching the model's own stated answer.

### 7.2 Turn loop
For the current step:
1. Tutor asks a guiding question relevant to this step's goal.
2. Learner responds (MathLive field or text).
3. Check the response: SymPy if it's math, the AI (inside the normal turn call) if it's conceptual.
4. Correct with no mistakes on this step → advance immediately. Correct after a mistake → a **check-understanding question** (why/how, not just what) → pass → advance.
5. Incorrect → a smaller hint or simpler sub-question. Never the step's result.
6. After the final step, the learner states the final answer; the tutor confirms it.

### 7.3 Answer-leak guardrail
This protects against the AI **accidentally** giving answers away. It is not about secrecy.

Before any tutor text or display payload is shown:
- Scan for the final answer (numeric, simplified expression, and SymPy-equivalent forms).
- Scan for the **current step's** result before the learner has produced it.
- On a hit: regenerate **once** with a stricter instruction; if it still leaks, show a canned safe hint for that step (no further AI calls).

### 7.4 Answer checking
- Math answers → SymPy equivalence (`simplify(a - b) == 0` / `equals()`), so `2(x+1)` and `2x+2` both pass.
- Numeric answers → tolerance check for decimals.
- Never trust the model's arithmetic.

### 7.5 Cost controls
Users pay for their own AI usage, so every choice defaults to fewer, smaller calls.

- **One AI call per learner turn:** tutor reply, intent label (§8), and any display payload (§9) come back in a single structured response.
- **One AI call at intake:** level + step plan together. Plus one vision call for image/PDF input.
- **No AI where code can do it:** answer checking (SymPy), the `steps` checklist and math rendering (local), obvious off-topic messages (local pre-check, canned redirect).
- **Small context:** each call sends the system prompt, the problem, a compact step-plan summary, the current step, and only the last few turns. Never the full transcript.
- **Prompt caching** where the provider supports it (Anthropic does): stable content first, marked cacheable.
- **Capped output:** tight max-token limits on replies and display payloads.
- **Images:** cropped (§4) and downscaled before vision extraction.
- **Usage meter:** approximate tokens used on the current problem, shown in Settings.

---

## 8. Staying on task

Each learner message gets an intent:
- **on-step:** answers or asks about the current step → normal loop.
- **on-math:** related to this problem but a different step → brief Socratic answer, then back to the current step.
- **off-topic:** anything else → one short, direct redirect, then the current question repeated.

A **local pre-check** catches obvious off-topic messages (no math content, nothing about the problem) and responds with a canned redirect and **no AI call**. Anything uncertain goes to the AI inside the normal turn call.

Example redirect: *"That's not about this problem. Pay attention. Step 2: what do you get when you distribute the 3?"*

---

## 9. Display box

A panel beside the conversation showing **examples of what the tutor is talking about.**

**Content types** (typed JSON, validated by a schema before rendering):
- `latex`: expressions or **parallel examples** (a similar problem with different numbers, never the learner's own problem solved).
- `steps`: the step checklist, rendered locally from engine state.
- `graph`: function plots (Phase 4).
- `diagram`: SVG (multiplication arrays, number lines, geometry figures) (Phase 4).

Every payload passes the leak guardrail (§7.3). Unknown or malformed payloads leave the box empty rather than crashing.

### 9.1 When the tutor shows something
Only when it helps:
- introducing a new step or concept,
- after the learner's **second** wrong attempt on the same step, or
- when the learner asks to see an example.

The payload rides in the same AI response. It never costs a separate call.

### 9.2 Wiping
Tutor-generated content is **wiped** when the step advances, the learner gets the step right, the tutor moves to a different sub-question, or a new problem starts. Empty is the normal state. The `steps` checklist stays for the whole problem.

---

## 10. Saved problems (local)

Problems save automatically so a learner can stop and resume.

- **Storage:** SQLite file in the app-data folder (`platformdirs`). Created automatically on first launch; nothing for the user to install.
- **Record:** problem LaTeX (as confirmed) · level · step plan + answer · current step · attempt counts · compact transcript (last few turns + short summary) · status (`in progress` / `completed`) · timestamps · short title.
- **Not stored in the database:** the API key (N9), images, PDFs.
- **Autosave** after every turn.
- **My problems** screen: In progress and Completed, newest first. Opening one restores the problem, checklist, and current step with **no AI call**.
- **Delete:** per problem, plus **Delete all problems** in Settings.
- **Schema migrations** are versioned so updates never break or wipe existing data.
- No profiles in v1: one list per computer (per OS user account).

---

## 11. AI provider & key (bring your own key)

### 11.1 Key handling
- First launch: onboarding screen explaining how to get a key. Tutoring is disabled until a key tests successfully.
- **Settings → AI provider:** provider, model, key (password field with show/hide), **Test key**, **Remove key**.
- The key is saved with `keyring` to the OS credential store: Windows Credential Manager or macOS Keychain. It is not written to the database, config files, or logs.
- The key is only sent to the provider the user selected.
- Logging redacts the key, and provider error messages are scrubbed before logging or display.
- If the OS credential store is unavailable, show a clear error; do not silently fall back to a plain-text file.

### 11.2 Provider adapters
- One interface (e.g. `LLMProvider`): streaming chat, vision extraction (image → LaTeX), structured JSON output.
- Each adapter declares **capabilities** (vision, structured output, streaming). Features are gated on them; for example, photo/PDF input is disabled for a model without vision, with a note explaining why.
- **Tested list:** providers/models that pass the acceptance tests (§14) are listed normally.
- **Untested models are allowed** behind a warning: *"Untested model. It may reveal answers, misread photos, or break the display box. Answers are still checked for leaks."*
  - **Test key** also runs a quick capability probe and disables features the model fails.
  - Repeated malformed structured output → a one-line notice suggesting a tested model; the display box stays empty.
- The leak guardrail and SymPy checks apply to every provider.
- Rollout: **Anthropic in Phase 1**; OpenAI, Gemini, OpenRouter in Phase 5.

### 11.3 Errors
Clear, key-free messages for: invalid key, expired or revoked key, out of credits, rate-limited, provider outage, and missing capability.

---

## 12. Packaging & distribution ($0)

### 12.1 Builds
- PyInstaller bundles Python, SymPy, the backend, and the built frontend into one app per OS. **Users do not need Python installed.**
- PyInstaller does not cross-compile: the Mac build must be made on a Mac. **GitHub Actions** builds both on its Windows and macOS runners.
  - The repo is **public**, so standard GitHub-hosted runners (Windows and macOS) are free.
- Mac: build a universal or per-architecture app (Apple Silicon + Intel), decided in Phase 3.

### 12.2 Releases
- Each tagged version publishes the Windows and Mac downloads to **GitHub Releases**.

### 12.3 Unsigned apps
No paid code signing (Apple's developer program is a yearly fee). Users see a one-time warning:
- **Windows (SmartScreen):** "More info" → "Run anyway".
- **Mac (Gatekeeper):** try to open, then System Settings → Privacy & Security → "Open Anyway".

The README walks through both with screenshots.

### 12.4 Updates
- Optional update check on launch against the GitHub Releases API → "Update available" link. Can be turned off in Settings.
- Updating = download the new version and replace the old one. Data and key live outside the app (§10, §11), so nothing is lost.

---

## 13. Phases

| Phase | Scope | Done when |
|-------|-------|-----------|
| **1 — Core loop (dev mode)** | Local server (§3.1), typed input + MathLive keyboard (all tabs), BYOK + keyring + Anthropic adapter, SymPy solve, intake call (level + step plan), turn loop, answer checking, leak guardrail, off-topic handling, display box (`latex` + `steps`, §9), saved problems (§10), cost controls (§7.5). Runs via a dev command. | Learner can type an arithmetic problem and a calculus problem and be tutored to the answer with no leak, and resume after restarting |
| **2 — Image/PDF input** | Webcam, photo/screenshot upload, clipboard paste, PDF via pdf.js; crop; vision → LaTeX → confirm | All paths land an editable problem in the field |
| **3 — Packaging** | PyInstaller for Windows + Mac, GitHub Actions, Releases, update check, README first-run guide | A non-developer on each OS can download, open, and use it without installing anything else |
| **4 — Richer visuals** | `graph` and `diagram` display types | Render correctly and pass the guardrail |
| **5 — More providers** | OpenAI, Gemini, OpenRouter adapters; capability gating; tested-list registry | Each listed provider passes §14 |

---

## 14. Acceptance tests (Phase 1 minimum)

**Tutoring**
- 5×5 → L1 register; uses groups/arrays; never says "25".
- d/dx sin(x²) → L5 register; chain-rule steps; never shows "2x cos(x²)" before the learner does.
- Learner answers `2(x+1)` where `2x+2` expected → accepted.
- "just tell me the answer" ×3 → still no answer.
- Model forced to leak (test hook) → guardrail blocks and substitutes a safe hint.

**Staying on task**
- "what's your favorite movie" → one-line redirect + current question repeated, with **zero** AI calls.

**Display box**
- Wipes on step advance, correct step answer, and new problem; `steps` checklist persists.

**Cost**
- A normal tutoring turn makes exactly **one** AI call (counted in tests).
- Resuming a saved problem makes **zero** AI calls.

**Saved problems**
- Close the app mid-problem, reopen → problem under In progress, resumes at the same step.
- Delete (single and all) removes the records.

**Key & local-only**
- Key is stored in the OS credential store; a search of the database, config files, and logs for the key string finds nothing, including after a forced provider error.
- No key → onboarding shown; tutoring disabled. Invalid key → clear error that doesn't echo the key.
- Server is unreachable from another device on the network (bound to 127.0.0.1).
- API request without the session token → rejected.
- With the update check off, the only outbound traffic during a session is to the selected AI provider.

---

## 15. Open decisions

1. App name.
2. ~~Level override~~ — **Decided: none; level is fully automatic.**
3. ~~Repo visibility~~ — **Decided: public.**
4. Mac build: universal app vs separate Apple Silicon / Intel downloads (Phase 3).
5. Update check on by default?
6. ~~License~~ — **Decided: MIT.** A future commercial version would be a separate product.

### Decision log
- Browser-based UI, running **locally** on the user's computer (Windows + Mac). No hosting, no monthly cost.
- Standalone **public** repo under the **MIT** license, no dependency on Whiskers.
- Bring your own key, stored in the OS credential store. Anthropic first; untested models allowed behind a warning.
- No voice. No personalities: one neutral, direct tone.
- Level calibration fully automatic, no override.
- No profiles in v1.
- Display box: automatic but gated, wiped when no longer needed.
- Problems saved locally in SQLite for resume.
- Not a commercial product for now.
- Hidden-answer protection is against accidental AI leaks, not determined users; the answer is stored locally in plain form.
- 2026-09-28: N4 amended. Explaining is required only after a mistake; correct answers (including the final answer) are otherwise accepted immediately. Reason: being made to explain a correct answer felt like the app refusing to accept it.

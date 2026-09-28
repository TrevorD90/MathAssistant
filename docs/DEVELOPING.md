# Developing MathAssistant

Everything a developer needs; the end-user guide is the [README](../README.md).

## Requirements

- Python **3.12** (with tkinter; the python.org installers include it)
- Node.js **20+** (22 used in CI)
- Git

## Set up

```bash
python -m venv .venv
.venv/Scripts/pip install -e "backend[dev]"          # macOS/Linux: .venv/bin/pip
cd web && npm install && cd ..
```

## Run from source

```bash
.venv/Scripts/python -m mathassistant       # builds web/ if stale, starts on 127.0.0.1:51789, opens the browser
```

- Dev key (optional): copy `.env.example` to `.env`, set `DEV_MODE=true` and `ANTHROPIC_DEV_API_KEY`. Only honoured with `DEV_MODE=true` and never in bundled builds.
- **Offline UI demo** (no key, no AI; canned replies):
  `DEV_MODE=true MATHASSISTANT_DEMO=1 .venv/Scripts/python -m mathassistant`
- Hot-reload frontend: start the backend with `MATHASSISTANT_PORT=8765`, run `npm run dev` in `web/`, open `http://localhost:5173/#token=<token printed by the backend>`.
- Other switches: `MATHASSISTANT_PORT`, `MATHASSISTANT_NO_BROWSER=1`, `MATHASSISTANT_DATA_DIR` (tests), `MATHASSISTANT_KEYRING_SERVICE` (tests).

## Tests

```bash
.venv/Scripts/python -m pytest backend/tests                   # offline suite
.venv/Scripts/python -m pytest backend/tests/live -m live -s    # real API: uses your saved key, costs a few cents
MATHASSISTANT_LIVE_MODEL=claude-sonnet-5 .venv/Scripts/python -m pytest backend/tests/live -m live -s
cd web && npm test
```

A model that passes the live suite can be marked `tested=True` in `backend/mathassistant/providers/registry.py`.

## Build the app (this computer's OS)

```bash
.venv/Scripts/pip install -e "backend[dev,package]"   # adds PyInstaller + Pillow (build-time only)
.venv/Scripts/python packaging/build.py               # web build -> icon -> PyInstaller -> self-test -> zip
```

Output: `dist/MathAssistant/` (Windows) or `dist/MathAssistant.app` (macOS), and `release/MathAssistant-<version>-<platform>.zip`.

- `packaging/mathassistant.spec`: what goes into the bundle (web app, SymPy's LaTeX grammars, keyring backends, Uvicorn submodules).
- The built app accepts `--self-test`: starts the server, calls the API, serves the page, parses math, exits 0/1. No AI calls.
- PyInstaller doesn't cross-compile: build Windows on Windows, macOS on macOS (or let CI do it).

## Release

1. Bump `__version__` in `backend/mathassistant/__init__.py` (and `version` in `backend/pyproject.toml` and `web/package.json`).
2. Update `docs/CHANGELOG.md`, commit, push.
3. Tag and push:
   ```bash
   git tag v0.3.0 && git push origin v0.3.0
   ```
4. GitHub Actions (`.github/workflows/release.yml`) builds Windows, Mac Apple Silicon and Mac Intel on GitHub's runners, runs all tests plus each app's self-test, and publishes a GitHub Release with the three zips. The in-app update check sees it right away.

To test the builds without publishing: Actions tab → **Build & release** → **Run workflow**. The zips appear as run artifacts.

## Rules

Build rules, non-negotiables and the decision log are in [../CLAUDE.md](../CLAUDE.md). The spec in [MATH_TUTOR_SPEC.md](MATH_TUTOR_SPEC.md) is the source of truth.

# MathAssistant

A math-only Socratic tutor that runs entirely on your own computer (Windows or Mac). You give it a problem; it breaks the problem into steps and guides you with questions. It never hands over the answer.

- **Local only.** A small server runs on `127.0.0.1` and opens in your browser. No accounts, no telemetry.
- **Bring your own AI key.** Your key is stored in your OS credential store (Windows Credential Manager / macOS Keychain) and sent only to the provider you choose.
- **Math is checked by code.** Answers are verified with SymPy, not by the AI.

> Status: Phase 1 (developer build). Downloadable apps for Windows and Mac arrive in Phase 3, with a first-run guide for the unsigned-app warnings.

## Developer setup

Requirements: Python 3.12, Node 20+.

```bash
python -m venv .venv
.venv/Scripts/pip install -e "backend[dev]"     # macOS/Linux: .venv/bin/pip
cd web && npm install && cd ..
.venv/Scripts/python -m mathassistant           # builds the web app if needed, starts the server, opens the browser
```

Run tests:

```bash
.venv/Scripts/python -m pytest backend/tests
cd web && npm test
```

See `docs/MATH_TUTOR_SPEC.md` for the design and `docs/ARCHITECTURE.md` for how the code is laid out.

## License

MIT — see `LICENSE`.

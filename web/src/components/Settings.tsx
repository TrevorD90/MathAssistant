// Settings → AI provider (spec §11.1): onboarding, provider/model, key entry
// (password with show/hide), Test key, Remove key, untested-model warning,
// usage meter, Delete all problems.

import { useEffect, useState } from "react";
import { useApp } from "../store/app";

function Onboarding({ keyUrl }: { keyUrl: string }) {
  return (
    <div className="onboarding">
      <h1>Welcome to MathAssistant</h1>
      <p>MathAssistant uses an AI model to ask you questions about your math problem. It runs on your computer and
        uses <strong>your own</strong> AI key, so you pay the provider directly for what you use (usually a fraction
        of a cent per problem).</p>
      <ol>
        <li>Create an account with Anthropic and add a small amount of credit.</li>
        <li>Create an API key at <span className="mono">{keyUrl}</span> and copy it.</li>
        <li>Paste it below and press <strong>Test key</strong>.</li>
      </ol>
      <p className="muted small">Your key is saved in your computer's credential store (Windows Credential Manager or
        macOS Keychain) and is only sent to the provider you choose.</p>
    </div>
  );
}

export function Settings() {
  const { status, providers, problem, busy, setModel, testKey, removeKey, deleteAll, setUpdateCheck } = useApp();
  const [provider, setProvider] = useState(status?.provider ?? "anthropic");
  const [model, setModelLocal] = useState(status?.model ?? "claude-haiku-4-5");
  const [custom, setCustom] = useState(false);
  const [key, setKey] = useState("");
  const [showKey, setShowKey] = useState(false);
  const [result, setResult] = useState<string | null>(null);

  useEffect(() => {
    if (status) {
      setProvider(status.provider);
      setModelLocal(status.model);
      setCustom(!status.known_model);
    }
  }, [status]);

  if (!status || !providers) return null;
  const pinfo = providers.providers.find((p) => p.id === provider) ?? providers.providers[0];
  const minfo = pinfo.models.find((m) => m.id === model);
  const untested = !minfo || !minfo.tested;

  const onTest = async () => {
    setResult(null);
    const ok = await testKey(provider, model, key || undefined);
    if (ok) {
      setKey("");
      setResult("Key works. You're ready to go.");
    }
  };

  return (
    <section className="settings">
      {!status.tutoring_enabled && <Onboarding keyUrl={pinfo.key_url} />}
      <h1>AI provider</h1>

      {!status.keystore_available && (
        <div className="error">Your computer's credential store isn't available, so a key can't be saved safely.
          MathAssistant won't store keys in a plain file.</div>
      )}

      <label className="field">
        <span>Provider</span>
        <select value={provider} onChange={(e) => setProvider(e.target.value)}>
          {providers.providers.map((p) => <option key={p.id} value={p.id}>{p.label}</option>)}
        </select>
      </label>

      <label className="field">
        <span>Model</span>
        {custom ? (
          <input value={model} onChange={(e) => setModelLocal(e.target.value.trim())} placeholder="model id" />
        ) : (
          <select value={model} onChange={(e) => setModelLocal(e.target.value)}>
            {pinfo.models.map((m) => <option key={m.id} value={m.id}>{m.label}</option>)}
          </select>
        )}
      </label>
      <label className="check">
        <input type="checkbox" checked={custom} onChange={(e) => {
          setCustom(e.target.checked);
          if (!e.target.checked) setModelLocal(providers.default_model);
        }} />
        Use another model
      </label>
      {minfo?.note && <p className="muted small">{minfo.note}</p>}
      {untested && <div className="warning" role="alert">{providers.untested_warning}</div>}

      <label className="field">
        <span>API key</span>
        <div className="key-row">
          <input type={showKey ? "text" : "password"} value={key} autoComplete="off" spellCheck={false}
                 placeholder={status.has_key ? "Saved (enter a new key to replace it)" : "Paste your key"}
                 onChange={(e) => setKey(e.target.value)} />
          <button type="button" onClick={() => setShowKey((s) => !s)}>{showKey ? "Hide" : "Show"}</button>
        </div>
      </label>

      <div className="row">
        <button className="primary" disabled={busy || (!key && !status.has_key)} onClick={onTest}>
          {busy ? "Testing…" : "Test key"}
        </button>
        {status.has_key && (
          <button className="danger" disabled={busy} onClick={() => {
            if (window.confirm("Remove the saved key from this computer?")) void removeKey(provider);
          }}>Remove key</button>
        )}
        {(provider !== status.provider || model !== status.model) && (
          <button disabled={busy} onClick={() => void setModel(provider, model)}>Save model</button>
        )}
      </div>
      {result && <div className="ok">{result}</div>}
      <p className="muted small">
        Status: {status.has_key ? (status.key_verified ? "key saved and tested" : "key saved, not tested for this model")
          : "no key"}
        {status.dev_mode && " · dev mode"}
      </p>

      <h2>Usage</h2>
      {problem ? (
        <p>Current problem: about {(problem.usage.tokens_in + problem.usage.tokens_out).toLocaleString()} tokens
          ({problem.usage.tokens_in.toLocaleString()} in, {problem.usage.tokens_out.toLocaleString()} out) across{" "}
          {problem.usage.ai_calls} AI call{problem.usage.ai_calls === 1 ? "" : "s"}.</p>
      ) : (
        <p className="muted">Open a problem to see its usage.</p>
      )}

      <h2>Updates</h2>
      <label className="check">
        <input type="checkbox" checked={status.update_check} disabled={busy}
               onChange={(e) => void setUpdateCheck(e.target.checked)} />
        Check for a new version when MathAssistant starts
      </label>
      <p className="muted small">
        Only asks GitHub for the latest version number; nothing about you is sent. You're on version {status.version}.
      </p>

      <h2>Saved problems</h2>
      <button className="danger" disabled={busy} onClick={async () => {
        if (window.confirm("Delete ALL saved problems? This can't be undone.")) {
          const n = await deleteAll();
          setResult(`Deleted ${n} problem${n === 1 ? "" : "s"}.`);
        }
      }}>Delete all problems</button>
    </section>
  );
}

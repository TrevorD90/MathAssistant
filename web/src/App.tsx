import { useEffect } from "react";
import { useApp } from "./store/app";
import { TutorScreen } from "./components/TutorScreen";
import { ProblemsScreen } from "./components/ProblemsScreen";
import { Settings } from "./components/Settings";

export function App({ hasToken }: { hasToken: boolean }) {
  const { screen, go, status, error, clearError, init, quit, stopped } = useApp();

  useEffect(() => {
    if (hasToken) void init();
  }, [hasToken, init]);

  if (!hasToken) {
    return (
      <main className="center">
        <h1>MathAssistant</h1>
        <p>Open MathAssistant from its app launcher. This page needs the link the launcher opens.</p>
      </main>
    );
  }
  if (stopped) {
    return (
      <main className="center">
        <h1>MathAssistant has stopped</h1>
        <p>You can close this tab. Your problems are saved.</p>
      </main>
    );
  }

  const enabled = status?.tutoring_enabled ?? false;
  return (
    <div className="app">
      <nav className="topbar">
        <span className="brand">MathAssistant</span>
        <button className={screen === "tutor" ? "on" : ""} disabled={!enabled} onClick={() => go("tutor")}>Tutor</button>
        <button className={screen === "problems" ? "on" : ""} onClick={() => go("problems")}>My problems</button>
        <button className={screen === "settings" ? "on" : ""} onClick={() => go("settings")}>Settings</button>
        <span className="spacer" />
        <button className="quit" onClick={() => { if (window.confirm("Quit MathAssistant?")) void quit(); }}>Quit</button>
      </nav>
      {error && (
        <div className="error" role="alert">
          {error} <button className="ghost" onClick={clearError} aria-label="Dismiss">✕</button>
        </div>
      )}
      <main>
        {screen === "tutor" && enabled && <TutorScreen />}
        {screen === "problems" && <ProblemsScreen />}
        {(screen === "settings" || (screen === "tutor" && !enabled)) && <Settings />}
      </main>
    </div>
  );
}

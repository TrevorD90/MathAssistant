// Last-resort guard: an unexpected rendering error shows a recoverable message
// instead of a blank page. Saved problems are on the server, so nothing is lost.

import { Component, type ReactNode } from "react";

interface State {
  failed: boolean;
}

export class ErrorBoundary extends Component<{ children: ReactNode }, State> {
  state: State = { failed: false };

  static getDerivedStateFromError(): State {
    return { failed: true };
  }

  componentDidCatch(error: unknown) {
    console.error("MathAssistant UI error", error);
  }

  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <main className="center">
        <h1>Something went wrong on this screen</h1>
        <p>Your problems are saved. Reload to continue.</p>
        <button className="primary" onClick={() => window.location.reload()}>Reload</button>
      </main>
    );
  }
}

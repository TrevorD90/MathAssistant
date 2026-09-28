// Problem entry + the tutoring conversation.

import { useEffect, useRef, useState } from "react";
import { useApp } from "../store/app";
import { DisplayBox } from "./DisplayBox";
import { MathInput } from "./MathInput";
import { Latex, MathText } from "./MathText";

function ProblemEntry() {
  const { startProblem, busy } = useApp();
  const [latex, setLatex] = useState("");
  const submit = () => {
    if (latex.trim() && !busy) void startProblem(latex);
  };
  return (
    <section className="entry">
      <h1>What problem are you working on?</h1>
      <p className="muted">Type it below, or use the keyboard icon in the field for the math keyboard.</p>
      <MathInput value={latex} onChange={setLatex} onSubmit={submit} ariaLabel="Problem" autoFocus
                 placeholder="\text{e.g. } 5\times5" />
      <div className="row">
        <button className="primary" onClick={submit} disabled={busy || !latex.trim()}>
          {busy ? "Planning the steps…" : "Start"}
        </button>
      </div>
    </section>
  );
}

function AnswerBar() {
  const { sendTurn, busy, problem } = useApp();
  const [mode, setMode] = useState<"math" | "words">("math");
  const [latex, setLatex] = useState("");
  const [text, setText] = useState("");
  const done = problem?.status === "completed";

  const submit = () => {
    if (busy || done) return;
    if (mode === "math" && latex.trim()) {
      void sendTurn("", latex);
      setLatex("");
    } else if (mode === "words" && text.trim()) {
      void sendTurn(text, "");
      setText("");
    }
  };

  if (done) return null;
  return (
    <div className="answer-bar">
      <div className="mode-switch" role="tablist" aria-label="Answer type">
        <button role="tab" aria-selected={mode === "math"} className={mode === "math" ? "on" : ""}
                onClick={() => setMode("math")}>Math</button>
        <button role="tab" aria-selected={mode === "words"} className={mode === "words" ? "on" : ""}
                onClick={() => setMode("words")}>Words</button>
      </div>
      {mode === "math" ? (
        // Inputs stay enabled while the tutor replies (disabling drops focus and
        // loses typing); `submit` ignores sends while busy.
        <MathInput value={latex} onChange={setLatex} onSubmit={submit} ariaLabel="Your answer" autoFocus />
      ) : (
        <input className="text-input" value={text} maxLength={1000} placeholder="Explain or ask about this step…"
               aria-label="Your answer in words" autoFocus
               onChange={(e) => setText(e.target.value)}
               onKeyDown={(e) => { if (e.key === "Enter") submit(); }} />
      )}
      <button className="primary" onClick={submit} disabled={busy}>{busy ? "…" : "Send"}</button>
    </div>
  );
}

function Conversation() {
  const { problem, busy } = useApp();
  const endRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    // Braces matter: newer browsers return a Promise from scrollIntoView, and an
    // effect must return nothing or a cleanup function.
    endRef.current?.scrollIntoView({ block: "end" });
  }, [problem?.transcript.length, busy]);
  if (!problem) return null;
  return (
    <div className="conversation" aria-live="polite">
      {problem.transcript.map((e, i) => (
        <div key={i} className={`msg msg-${e.role} ${e.kind === "redirect" ? "msg-redirect" : ""}`}>
          <MathText text={e.text} />
        </div>
      ))}
      {busy && <div className="msg msg-tutor msg-pending">…</div>}
      <div ref={endRef} />
    </div>
  );
}

export function TutorScreen() {
  const { problem, newProblem } = useApp();
  if (!problem) return <ProblemEntry />;
  const done = problem.status === "completed";
  return (
    <div className="tutor">
      <section className="tutor-main">
        <header className="problem-header">
          <div>
            <div className="muted small">{problem.title}</div>
            <div className="problem-latex"><Latex latex={problem.problem_latex} display /></div>
          </div>
          <button onClick={newProblem}>New problem</button>
        </header>
        {problem.notice && <div className="notice">{problem.notice}</div>}
        <Conversation />
        {done ? (
          <div className="done">Solved. <button className="primary" onClick={newProblem}>Try another problem</button></div>
        ) : (
          <AnswerBar />
        )}
      </section>
      <DisplayBox steps={problem.steps} payload={problem.display} />
    </div>
  );
}

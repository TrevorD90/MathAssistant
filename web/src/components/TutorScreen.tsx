// Problem entry + the tutoring conversation.

import { useEffect, useRef, useState } from "react";
import { useApp } from "../store/app";
import type { Extraction } from "../api/types";
import { imageFromClipboard } from "../capture/image";
import { CaptureFlow, type CaptureStart } from "./capture/CaptureFlow";
import { DisplayBox } from "./DisplayBox";
import { MathInput } from "./MathInput";
import { Latex, MathText } from "./MathText";

function ProblemEntry() {
  const { startProblem, busy, status } = useApp();
  const [kind, setKind] = useState<"math" | "words">("math");
  const [latex, setLatex] = useState("");
  const [text, setText] = useState("");
  const [capture, setCapture] = useState<CaptureStart | null>(null);
  const [extracted, setExtracted] = useState<Extraction | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const canSee = status?.capabilities.vision ?? false;
  const ready = kind === "math" ? latex.trim() : text.trim();

  const submit = () => {
    if (!ready || busy) return;
    const exId = extracted?.extraction_id ?? null;
    if (kind === "math") void startProblem(latex, "", exId);
    else void startProblem("", text, exId);
  };

  // Screenshot paste (Ctrl+V / Cmd+V) anywhere on the entry screen. Text
  // pastes into the fields work as usual; only image pastes are intercepted.
  useEffect(() => {
    if (!canSee || capture) return;
    const onPaste = (e: ClipboardEvent) => {
      const file = imageFromClipboard(e.clipboardData);
      if (file) {
        e.preventDefault();
        setCapture({ type: "file", file });
      }
    };
    window.addEventListener("paste", onPaste);
    return () => window.removeEventListener("paste", onPaste);
  }, [canSee, capture]);

  // The AI's reading goes into the normal fields so the learner can confirm or edit it.
  const onExtracted = (ex: Extraction) => {
    setExtracted(ex);
    setCapture(null);
    setKind(ex.kind);
    if (ex.kind === "math") setLatex(ex.latex);
    else setText(ex.text);
  };

  if (capture) {
    return (
      <section className="entry">
        <h1>Add a problem from an image</h1>
        <CaptureFlow start={capture} onExtracted={onExtracted} onCancel={() => setCapture(null)} />
      </section>
    );
  }

  return (
    <section className="entry">
      <h1>What problem are you working on?</h1>
      <div className="image-sources" aria-label="Add from an image">
        <button disabled={!canSee} onClick={() => setCapture({ type: "camera" })}>📷 Camera</button>
        <button disabled={!canSee} onClick={() => fileRef.current?.click()}>🖼 Photo, screenshot, or PDF</button>
        <span className="muted small">{canSee ? "or paste a screenshot (Ctrl+V)" : "The selected model can't read images. Pick one that can in Settings."}</span>
        <input ref={fileRef} type="file" hidden accept="image/png,image/jpeg,image/webp,image/gif,application/pdf"
               onChange={(e) => {
                 const f = e.target.files?.[0];
                 e.target.value = "";
                 if (f) setCapture({ type: "file", file: f });
               }} />
      </div>
      {extracted && (
        <div className="notice confirm" role="status">
          <span>
            <strong>Check the problem below.</strong> Fix anything that was misread, then press Start.
            {extracted.instruction && <> The image says: “{extracted.instruction}”.</>}
            {extracted.note && extracted.note !== "demo" && <> ({extracted.note})</>}
          </span>
          <button className="ghost" onClick={() => setExtracted(null)} aria-label="Dismiss">✕</button>
        </div>
      )}
      <div className="mode-switch entry-switch" role="tablist" aria-label="Problem type">
        <button role="tab" aria-selected={kind === "math"} className={kind === "math" ? "on" : ""}
                onClick={() => setKind("math")}>Math</button>
        <button role="tab" aria-selected={kind === "words"} className={kind === "words" ? "on" : ""}
                onClick={() => setKind("words")}>Word problem</button>
      </div>
      {kind === "math" ? (
        <>
          <p className="muted">Type it below, or use the keyboard icon in the field for the math keyboard.</p>
          <MathInput value={latex} onChange={setLatex} onSubmit={submit} ariaLabel="Problem" autoFocus
                     placeholder="\text{e.g. } 5\times5" />
        </>
      ) : (
        <>
          <p className="muted">Type or paste the word problem exactly as it's written.</p>
          <textarea className="word-problem" value={text} maxLength={2000} rows={5} autoFocus
                    aria-label="Word problem"
                    placeholder="e.g. Sam has 3 bags with 12 apples in each bag. How many apples does Sam have?"
                    onChange={(e) => setText(e.target.value)}
                    onKeyDown={(e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) submit(); }} />
          <p className="muted small">Press Ctrl+Enter or Start.</p>
        </>
      )}
      <div className="row">
        <button className="primary" onClick={submit} disabled={busy || !ready}>
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
            <div className="problem-latex">
              {problem.problem_kind === "words"
                ? <p className="word-problem-text"><MathText text={problem.problem_latex} /></p>
                : <Latex latex={problem.problem_latex} display />}
            </div>
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

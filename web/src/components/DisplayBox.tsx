// Display box (spec §9): the local `steps` checklist (persists for the whole
// problem) plus the tutor's `latex` examples (wiped by the engine; empty is normal).

import type { DisplayPayload, StepItem } from "../api/types";
import { Latex, MathText } from "./MathText";

export function StepChecklist({ steps }: { steps: StepItem[] }) {
  return (
    <ol className="steps" aria-label="Steps">
      {steps.map((s) => (
        <li key={s.index} className={`step step-${s.status}`}>
          <span className="step-mark" aria-hidden>
            {s.status === "done" ? "✓" : s.status === "current" ? "→" : "•"}
          </span>
          <span className="step-title">
            {s.status === "locked" ? <span className="muted">Step {s.index}</span> : `Step ${s.index}: ${s.title}`}
          </span>
        </li>
      ))}
    </ol>
  );
}

// Only the known `latex` type renders; anything else leaves the box empty.
export function isRenderable(p: DisplayPayload | null): p is DisplayPayload {
  return Boolean(p && p.type === "latex" && Array.isArray(p.items) && p.items.length > 0);
}

export function DisplayBox({ steps, payload }: { steps: StepItem[]; payload: DisplayPayload | null }) {
  return (
    <aside className="display-box" aria-label="Display box">
      <StepChecklist steps={steps} />
      <div className="examples" aria-live="polite">
        {isRenderable(payload) && (
          <figure className="example">
            {payload.title && <figcaption className="example-title"><MathText text={payload.title} /></figcaption>}
            {payload.items.map((it, i) => (
              <div key={i} className="example-item">
                <Latex latex={it.latex} display />
                {/* captions may contain $...$ math (e.g. "Combine: $5 + 9 = 14$") */}
                {it.caption && <div className="caption"><MathText text={it.caption} /></div>}
              </div>
            ))}
          </figure>
        )}
      </div>
    </aside>
  );
}

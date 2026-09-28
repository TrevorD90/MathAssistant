// A worksheet with several problems: pick one to start with; optionally save
// the others to "Up next" (no AI cost until each is started).

import { useState } from "react";
import type { ExtractedProblem } from "../../api/types";
import { Latex, MathText } from "../MathText";

interface Props {
  problems: ExtractedProblem[];
  busy: boolean;
  onPick: (chosen: ExtractedProblem, saveRest: boolean) => void;
  onCancel: () => void;
}

export function problemPreview(p: ExtractedProblem) {
  return p.kind === "math" ? <Latex latex={p.latex} /> : <MathText text={p.text} />;
}

export function ProblemPicker({ problems, busy, onPick, onCancel }: Props) {
  const [saveRest, setSaveRest] = useState(true);
  return (
    <div className="picker">
      <p><strong>Found {problems.length} problems.</strong> Choose one to start with.</p>
      <ol className="picker-list">
        {problems.map((p, i) => (
          <li key={i}>
            <button className="picker-item" disabled={busy} onClick={() => onPick(p, saveRest)}>
              <span className="picker-label">{p.label || i + 1}</span>
              <span className="picker-body">
                {p.instruction && <span className="muted small">{p.instruction} </span>}
                {problemPreview(p)}
              </span>
              <span className="picker-go">Start with this one →</span>
            </button>
          </li>
        ))}
      </ol>
      <label className="check">
        <input type="checkbox" checked={saveRest} onChange={(e) => setSaveRest(e.target.checked)} />
        Save the other {problems.length - 1} to <strong>Up next</strong> in My problems
      </label>
      <div className="row"><button onClick={onCancel} disabled={busy}>Cancel</button></div>
    </div>
  );
}

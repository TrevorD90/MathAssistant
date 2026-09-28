// My problems (spec §10): In progress / Completed, newest first. Opening one
// resumes with no AI call.

import { useApp } from "../store/app";
import type { ProblemSummary } from "../api/types";
import { Latex, MathText } from "./MathText";

function List({ items, empty }: { items: ProblemSummary[]; empty: string }) {
  const { openProblem, deleteProblem } = useApp();
  if (items.length === 0) return <p className="muted">{empty}</p>;
  return (
    <ul className="problem-list">
      {items.map((p) => (
        <li key={p.id}>
          <button className="problem-open" onClick={() => void openProblem(p.id)}>
            <span className="problem-title">{p.title}</span>
            <span className="problem-mini">
              {p.problem_kind === "words"
                ? <MathText text={p.problem_latex.length > 90 ? p.problem_latex.slice(0, 87) + "…" : p.problem_latex} />
                : <Latex latex={p.problem_latex} />}
            </span>
            <span className="muted small">{new Date(p.updated_at).toLocaleString()}</span>
          </button>
          <button className="danger ghost" aria-label={`Delete ${p.title}`}
                  onClick={() => { if (window.confirm("Delete this problem?")) void deleteProblem(p.id); }}>
            Delete
          </button>
        </li>
      ))}
    </ul>
  );
}

export function ProblemsScreen() {
  const { problems } = useApp();
  return (
    <section className="problems">
      <h1>My problems</h1>
      <h2>In progress</h2>
      <List items={problems?.in_progress ?? []} empty="Nothing in progress." />
      <h2>Completed</h2>
      <List items={problems?.completed ?? []} empty="No completed problems yet." />
    </section>
  );
}

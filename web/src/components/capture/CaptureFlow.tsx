// Phase 2 capture flow (spec §4): camera / photo / screenshot / PDF ->
// crop (optional) -> one vision call per image -> pick a problem (if there
// are several) -> hand it back to the entry screen to confirm.

import { useEffect, useState } from "react";
import type { PDFDocumentProxy } from "pdfjs-dist";
import { api, ApiError } from "../../api/client";
import type { ExtractedProblem } from "../../api/types";
import { cropAndEncode, loadImageFile, type Rect } from "../../capture/image";
import { CameraView } from "./CameraView";
import { Cropper } from "./Cropper";
import { ProblemPicker } from "./ProblemPicker";

export type CaptureStart =
  | { type: "camera" }
  | { type: "file"; file: File };

export interface CaptureResult {
  problem: ExtractedProblem;
  extractionIds: string[];   // vision calls to count toward this problem's usage
}

interface Props {
  start: CaptureStart;
  onPicked: (result: CaptureResult) => void;
  onCancel: () => void;
}

const MAX_PDF_PAGES_AT_ONCE = 10;

type Stage =
  | { kind: "camera" }
  | { kind: "loading"; label: string }
  | { kind: "pdf"; doc: PDFDocumentProxy; page: number; preview: HTMLCanvasElement | null }
  | { kind: "crop"; source: HTMLCanvasElement | ImageBitmap }
  | { kind: "pick"; problems: ExtractedProblem[]; extractionIds: string[] }
  | { kind: "error"; message: string };

function sourceName(start: CaptureStart): string {
  return start.type === "file" ? start.file.name.slice(0, 100) : "camera";
}

export function CaptureFlow({ start, onPicked, onCancel }: Props) {
  const [stage, setStage] = useState<Stage>(start.type === "camera" ? { kind: "camera" } : { kind: "loading", label: "Opening…" });
  const [busy, setBusy] = useState(false);
  const [readError, setReadError] = useState<string | null>(null);

  // Open an uploaded / pasted file: images go to crop, PDFs to the page picker.
  useEffect(() => {
    if (start.type !== "file") return;
    let cancelled = false;
    (async () => {
      try {
        const f = start.file;
        if (f.type === "application/pdf" || f.name.toLowerCase().endsWith(".pdf")) {
          const { openPdf } = await import("../../capture/pdf");
          const doc = await openPdf(f);
          if (!cancelled) setStage({ kind: "pdf", doc, page: 1, preview: null });
        } else {
          const bmp = await loadImageFile(f);
          if (!cancelled) setStage({ kind: "crop", source: bmp });
        }
      } catch (e) {
        if (!cancelled) setStage({ kind: "error", message: e instanceof Error ? e.message : "That file couldn't be opened." });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [start]);

  // Render the selected PDF page as a preview.
  const pdfStage = stage.kind === "pdf" ? stage : null;
  useEffect(() => {
    if (!pdfStage || pdfStage.preview) return;
    let cancelled = false;
    (async () => {
      const { renderPage } = await import("../../capture/pdf");
      try {
        const canvas = await renderPage(pdfStage.doc, pdfStage.page);
        if (!cancelled) setStage({ ...pdfStage, preview: canvas });
      } catch {
        if (!cancelled) setStage({ kind: "error", message: "That page couldn't be shown." });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [pdfStage]);

  // One problem -> straight to confirm. Several -> let the learner choose.
  const finish = (problems: ExtractedProblem[], extractionIds: string[]) => {
    if (problems.length === 1) onPicked({ problem: problems[0], extractionIds });
    else setStage({ kind: "pick", problems, extractionIds });
  };

  const read = async (source: HTMLCanvasElement | ImageBitmap, rect: Rect | null) => {
    setBusy(true);
    setReadError(null);
    try {
      const img = cropAndEncode(source, source.width, source.height, rect);
      const ex = await api.extract(img.base64, img.mediaType);
      if (!ex.readable || ex.problems.length === 0) {
        setReadError(`No problem could be read${ex.note ? ` (${ex.note})` : ""}. Try a tighter crop or a clearer picture.`);
        return;
      }
      finish(ex.problems, [ex.extraction_id]);
    } catch (e) {
      setReadError(e instanceof ApiError ? e.message : "Something went wrong reading the image.");
    } finally {
      setBusy(false);
    }
  };

  // Multi-page PDF: read each page (one vision call per page) and merge the lists.
  const readAllPages = async (doc: PDFDocumentProxy) => {
    const pages = Math.min(doc.numPages, MAX_PDF_PAGES_AT_ONCE);
    setBusy(true);
    setReadError(null);
    const all: ExtractedProblem[] = [];
    const ids: string[] = [];
    try {
      const { renderPage } = await import("../../capture/pdf");
      for (let n = 1; n <= pages; n++) {
        setStage({ kind: "loading", label: `Reading page ${n} of ${pages}…` });
        const canvas = await renderPage(doc, n);
        const img = cropAndEncode(canvas, canvas.width, canvas.height, null);
        const ex = await api.extract(img.base64, img.mediaType);
        ids.push(ex.extraction_id);
        for (const p of ex.problems) all.push({ ...p, label: `p${n}${p.label ? ` #${p.label}` : ""}` });
      }
      if (all.length === 0) {
        setStage({ kind: "error", message: "No problems could be read from this PDF." });
        return;
      }
      finish(all, ids);
    } catch (e) {
      setStage({ kind: "error", message: e instanceof ApiError ? e.message : "Something went wrong reading the PDF." });
    } finally {
      setBusy(false);
    }
  };

  const pick = async (chosen: ExtractedProblem, saveRest: boolean, problems: ExtractedProblem[], extractionIds: string[]) => {
    if (saveRest) {
      setBusy(true);
      try {
        await api.queue(problems.filter((p) => p !== chosen), sourceName(start));
      } catch (e) {
        setReadError(e instanceof ApiError ? e.message : "The other problems couldn't be saved.");
        setBusy(false);
        return;
      }
      setBusy(false);
    }
    onPicked({ problem: chosen, extractionIds });
  };

  return (
    <section className="capture" aria-label="Add a problem from an image">
      {stage.kind === "camera" && (
        <CameraView onCapture={(frame) => setStage({ kind: "crop", source: frame })} onCancel={onCancel} />
      )}
      {stage.kind === "loading" && <p className="muted">{stage.label}</p>}
      {stage.kind === "error" && (
        <>
          <div className="error inline" role="alert">{stage.message}</div>
          <div className="row"><button onClick={onCancel}>Back</button></div>
        </>
      )}
      {stage.kind === "pdf" && (
        <div className="pdf-picker">
          <div className="row">
            <button disabled={stage.page <= 1 || busy}
                    onClick={() => setStage({ ...stage, page: stage.page - 1, preview: null })}>◀ Prev</button>
            <span>Page {stage.page} of {stage.doc.numPages}</span>
            <button disabled={stage.page >= stage.doc.numPages || busy}
                    onClick={() => setStage({ ...stage, page: stage.page + 1, preview: null })}>Next ▶</button>
            <button className="primary" disabled={!stage.preview || busy}
                    onClick={() => stage.preview && setStage({ kind: "crop", source: stage.preview })}>
              Use this page
            </button>
            {stage.doc.numPages > 1 && (
              <button disabled={busy} onClick={() => void readAllPages(stage.doc)}
                      title={`One AI read per page${stage.doc.numPages > MAX_PDF_PAGES_AT_ONCE ? `; first ${MAX_PDF_PAGES_AT_ONCE} pages` : ""}`}>
                Read all {Math.min(stage.doc.numPages, MAX_PDF_PAGES_AT_ONCE)} pages
              </button>
            )}
            <button disabled={busy} onClick={onCancel}>Cancel</button>
          </div>
          {stage.preview
            ? <img className="pdf-preview" src={stage.preview.toDataURL("image/png")} alt={`PDF page ${stage.page}`} />
            : <p className="muted">Rendering page…</p>}
        </div>
      )}
      {stage.kind === "crop" && (
        <Cropper source={stage.source} busy={busy} onConfirm={(r) => void read(stage.source, r)} onCancel={onCancel} />
      )}
      {stage.kind === "pick" && (
        <ProblemPicker problems={stage.problems} busy={busy} onCancel={onCancel}
                       onPick={(p, saveRest) => void pick(p, saveRest, stage.problems, stage.extractionIds)} />
      )}
      {readError && <div className="error inline" role="alert">{readError}</div>}
    </section>
  );
}

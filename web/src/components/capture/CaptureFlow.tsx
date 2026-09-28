// Phase 2 capture flow (spec §4): camera / photo / screenshot / PDF ->
// crop -> one vision call -> hand the text back to the entry screen to confirm.

import { useEffect, useState } from "react";
import type { PDFDocumentProxy } from "pdfjs-dist";
import { api, ApiError } from "../../api/client";
import type { Extraction } from "../../api/types";
import { cropAndEncode, loadImageFile, type Rect } from "../../capture/image";
import { CameraView } from "./CameraView";
import { Cropper } from "./Cropper";

export type CaptureStart =
  | { type: "camera" }
  | { type: "file"; file: File };

interface Props {
  start: CaptureStart;
  onExtracted: (ex: Extraction) => void;
  onCancel: () => void;
}

type Stage =
  | { kind: "camera" }
  | { kind: "loading"; label: string }
  | { kind: "pdf"; doc: PDFDocumentProxy; page: number; preview: HTMLCanvasElement | null }
  | { kind: "crop"; source: HTMLCanvasElement | ImageBitmap }
  | { kind: "error"; message: string };

export function CaptureFlow({ start, onExtracted, onCancel }: Props) {
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

  const read = async (source: HTMLCanvasElement | ImageBitmap, rect: Rect | null) => {
    setBusy(true);
    setReadError(null);
    try {
      const img = cropAndEncode(source, source.width, source.height, rect);
      const ex = await api.extract(img.base64, img.mediaType);
      if (!ex.readable) {
        setReadError(`The problem couldn't be read${ex.note ? ` (${ex.note})` : ""}. Try a tighter crop or a clearer picture.`);
        return;
      }
      onExtracted(ex);
    } catch (e) {
      setReadError(e instanceof ApiError ? e.message : "Something went wrong reading the image.");
    } finally {
      setBusy(false);
    }
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
            <button disabled={stage.page <= 1}
                    onClick={() => setStage({ ...stage, page: stage.page - 1, preview: null })}>◀ Prev</button>
            <span>Page {stage.page} of {stage.doc.numPages}</span>
            <button disabled={stage.page >= stage.doc.numPages}
                    onClick={() => setStage({ ...stage, page: stage.page + 1, preview: null })}>Next ▶</button>
            <button className="primary" disabled={!stage.preview}
                    onClick={() => stage.preview && setStage({ kind: "crop", source: stage.preview })}>
              Use this page
            </button>
            <button onClick={onCancel}>Cancel</button>
          </div>
          {stage.preview
            ? <img className="pdf-preview" src={stage.preview.toDataURL("image/png")} alt={`PDF page ${stage.page}`} />
            : <p className="muted">Rendering page…</p>}
        </div>
      )}
      {stage.kind === "crop" && (
        <>
          <Cropper source={stage.source} busy={busy} onConfirm={(r) => void read(stage.source, r)} onCancel={onCancel} />
          {readError && <div className="error inline" role="alert">{readError}</div>}
        </>
      )}
    </section>
  );
}

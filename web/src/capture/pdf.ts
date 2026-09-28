// PDF input (spec §4): render a chosen page with pdf.js (Apache-2.0), bundled
// locally and loaded only when a PDF is opened (keeps the main bundle small).
// Its fonts, character maps and WASM decoders are copied into the build by
// vite.config.ts under /pdfjs/.

import type { PDFDocumentProxy } from "pdfjs-dist";

let lib: typeof import("pdfjs-dist") | null = null;

async function pdfjs() {
  if (!lib) {
    lib = await import("pdfjs-dist");
    const worker = await import("pdfjs-dist/build/pdf.worker.min.mjs?url");
    lib.GlobalWorkerOptions.workerSrc = worker.default;
  }
  return lib;
}

export async function openPdf(file: Blob): Promise<PDFDocumentProxy> {
  const p = await pdfjs();
  const data = new Uint8Array(await file.arrayBuffer());
  try {
    return await p.getDocument({
      data,
      cMapUrl: "/pdfjs/cmaps/",
      cMapPacked: true,
      standardFontDataUrl: "/pdfjs/standard_fonts/",
      wasmUrl: "/pdfjs/wasm/",
      // No scripting, no external fetches: this is a viewer for one page.
      enableXfa: false,
      isEvalSupported: false,
    } as Parameters<typeof p.getDocument>[0]).promise;
  } catch {
    throw new Error("That PDF couldn't be opened. It may be damaged or password-protected.");
  }
}

/** Render one page (1-based) to a canvas at a resolution good enough to read small print. */
export async function renderPage(doc: PDFDocumentProxy, pageNumber: number, targetWidth = 1600): Promise<HTMLCanvasElement> {
  const page = await doc.getPage(pageNumber);
  const base = page.getViewport({ scale: 1 });
  const scale = Math.min(3, targetWidth / base.width);
  const viewport = page.getViewport({ scale });
  const canvas = document.createElement("canvas");
  canvas.width = Math.ceil(viewport.width);
  canvas.height = Math.ceil(viewport.height);
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("Canvas isn't available in this browser.");
  ctx.fillStyle = "#ffffff";
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  await page.render({ canvas, canvasContext: ctx, viewport } as Parameters<typeof page.render>[0]).promise;
  return canvas;
}

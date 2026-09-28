// Image helpers for Phase 2 (spec §4): crop to the one problem, downscale,
// encode. Everything happens in the browser; only the final cropped image is
// sent to the local server (and from there to the AI provider, once).

export interface Rect {
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface EncodedImage {
  base64: string; // no data: prefix
  mediaType: "image/png" | "image/jpeg";
  width: number;
  height: number;
}

// Anthropic's guidance: images over ~1.15 megapixels or 1568px on a side are
// downscaled server-side anyway, so sending more only costs upload time.
export const MAX_PIXELS = 1_150_000;
export const MAX_SIDE = 1568;
const PNG_BUDGET_BYTES = 1_500_000; // above this, use JPEG

/** Scale (w, h) down to fit the pixel and side limits. Never scales up. */
export function fitWithin(w: number, h: number, maxPixels = MAX_PIXELS, maxSide = MAX_SIDE): { w: number; h: number } {
  let scale = Math.min(1, maxSide / Math.max(w, h));
  if (w * scale * h * scale > maxPixels) scale = Math.sqrt(maxPixels / (w * h));
  return { w: Math.max(1, Math.round(w * scale)), h: Math.max(1, Math.round(h * scale)) };
}

/** Rectangle from two drag points, clamped to the image. */
export function rectFromPoints(ax: number, ay: number, bx: number, by: number, imgW: number, imgH: number): Rect {
  const clamp = (v: number, max: number) => Math.min(Math.max(v, 0), max);
  const x1 = clamp(Math.min(ax, bx), imgW);
  const y1 = clamp(Math.min(ay, by), imgH);
  const x2 = clamp(Math.max(ax, bx), imgW);
  const y2 = clamp(Math.max(ay, by), imgH);
  return { x: x1, y: y1, w: x2 - x1, h: y2 - y1 };
}

/** Tiny drags (accidental clicks) mean "use the whole image". */
export function isUsableRect(r: Rect | null, minSide = 12): r is Rect {
  return Boolean(r && r.w >= minSide && r.h >= minSide);
}

function base64FromDataUrl(url: string): string {
  return url.slice(url.indexOf(",") + 1);
}

/** Crop `source` to `rect` (image pixels), downscale, and encode. */
export function cropAndEncode(source: CanvasImageSource, srcW: number, srcH: number, rect: Rect | null): EncodedImage {
  const r = isUsableRect(rect) ? rect : { x: 0, y: 0, w: srcW, h: srcH };
  const { w, h } = fitWithin(r.w, r.h);
  const canvas = document.createElement("canvas");
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("Canvas isn't available in this browser.");
  ctx.fillStyle = "#ffffff"; // transparent PNGs/screenshots -> white background
  ctx.fillRect(0, 0, w, h);
  ctx.imageSmoothingQuality = "high";
  ctx.drawImage(source, r.x, r.y, r.w, r.h, 0, 0, w, h);
  // PNG keeps text sharp; fall back to JPEG for large photos.
  let url = canvas.toDataURL("image/png");
  let mediaType: EncodedImage["mediaType"] = "image/png";
  if (url.length * 0.75 > PNG_BUDGET_BYTES) {
    url = canvas.toDataURL("image/jpeg", 0.9);
    mediaType = "image/jpeg";
  }
  return { base64: base64FromDataUrl(url), mediaType, width: w, height: h };
}

/** Decode an image file (upload or pasted screenshot) into a drawable bitmap. */
export async function loadImageFile(file: Blob): Promise<ImageBitmap> {
  if (!file.type.startsWith("image/")) throw new Error("That file isn't an image.");
  try {
    return await createImageBitmap(file);
  } catch {
    throw new Error("That image couldn't be opened. Try a PNG or JPEG.");
  }
}

/** First image in a paste event, if any (screenshots from the clipboard). */
export function imageFromClipboard(data: DataTransfer | null): File | null {
  if (!data) return null;
  for (const item of Array.from(data.items)) {
    if (item.kind === "file" && item.type.startsWith("image/")) return item.getAsFile();
  }
  return null;
}

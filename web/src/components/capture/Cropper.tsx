// Crop to the one problem (spec §4): drag a box over the image. Keeps the
// image small (lower cost) and stops the AI reading the wrong problem.
// Pointer events cover mouse, pen and touch.

import { useEffect, useRef, useState } from "react";
import { rectFromPoints, isUsableRect, type Rect } from "../../capture/image";

interface Props {
  source: HTMLCanvasElement | ImageBitmap;
  busy: boolean;
  onConfirm: (rect: Rect | null) => void; // null = whole image
  onCancel: () => void;
}

export function Cropper({ source, busy, onConfirm, onCancel }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [rect, setRect] = useState<Rect | null>(null);
  const drag = useRef<{ x: number; y: number } | null>(null);
  const imgW = source.width;
  const imgH = source.height;

  // Draw the image, dimming everything outside the selection.
  useEffect(() => {
    const c = canvasRef.current;
    const ctx = c?.getContext("2d");
    if (!c || !ctx) return;
    c.width = imgW;
    c.height = imgH;
    ctx.drawImage(source, 0, 0);
    if (isUsableRect(rect)) {
      ctx.fillStyle = "rgba(0,0,0,0.45)";
      ctx.fillRect(0, 0, imgW, rect.y);
      ctx.fillRect(0, rect.y + rect.h, imgW, imgH - rect.y - rect.h);
      ctx.fillRect(0, rect.y, rect.x, rect.h);
      ctx.fillRect(rect.x + rect.w, rect.y, imgW - rect.x - rect.w, rect.h);
      ctx.strokeStyle = "#2f5bd3";
      ctx.lineWidth = Math.max(2, imgW / 400);
      ctx.strokeRect(rect.x, rect.y, rect.w, rect.h);
    }
  }, [source, rect, imgW, imgH]);

  // Screen coordinates -> image pixel coordinates.
  const toImage = (e: React.PointerEvent) => {
    const box = canvasRef.current!.getBoundingClientRect();
    return { x: ((e.clientX - box.left) / box.width) * imgW, y: ((e.clientY - box.top) / box.height) * imgH };
  };

  return (
    <div className="cropper">
      <p><strong>Drag a box around just the one problem.</strong> <span className="muted">Or use the whole image.</span></p>
      <canvas
        ref={canvasRef}
        className="crop-canvas"
        aria-label="Image to crop"
        onPointerDown={(e) => {
          (e.target as HTMLElement).setPointerCapture(e.pointerId);
          drag.current = toImage(e);
          setRect(null);
        }}
        onPointerMove={(e) => {
          if (!drag.current) return;
          const p = toImage(e);
          setRect(rectFromPoints(drag.current.x, drag.current.y, p.x, p.y, imgW, imgH));
        }}
        onPointerUp={(e) => {
          // Also finish the box on release, in case no move events arrived.
          if (drag.current) {
            const p = toImage(e);
            setRect(rectFromPoints(drag.current.x, drag.current.y, p.x, p.y, imgW, imgH));
          }
          drag.current = null;
        }}
      />
      <div className="row">
        <button className="primary" disabled={busy} onClick={() => onConfirm(isUsableRect(rect) ? rect : null)}>
          {busy ? "Reading the problem…" : isUsableRect(rect) ? "Read this part" : "Read whole image"}
        </button>
        {isUsableRect(rect) && <button disabled={busy} onClick={() => setRect(null)}>Clear box</button>}
        <button disabled={busy} onClick={onCancel}>Cancel</button>
      </div>
    </div>
  );
}

// Webcam capture (spec §4). Works without HTTPS because 127.0.0.1 is a
// secure context. The stream is stopped as soon as a frame is taken or the
// view closes, so the camera light turns off.

import { useEffect, useRef, useState } from "react";

interface Props {
  onCapture: (frame: HTMLCanvasElement) => void;
  onCancel: () => void;
}

function cameraError(e: unknown): string {
  const name = (e as { name?: string })?.name ?? "";
  if (name === "NotAllowedError") return "Camera access was blocked. Allow the camera for this page in your browser's address bar, then try again.";
  if (name === "NotFoundError" || name === "OverconstrainedError") return "No camera was found on this computer. Upload a photo instead.";
  if (name === "NotReadableError") return "The camera is being used by another app. Close it and try again.";
  return "The camera couldn't be started. Upload a photo instead.";
}

export function CameraView({ onCapture, onCancel }: Props) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      if (!navigator.mediaDevices?.getUserMedia) {
        setError("This browser can't use the camera. Upload a photo instead.");
        return;
      }
      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: "environment", width: { ideal: 1920 }, height: { ideal: 1080 } },
          audio: false,
        });
        if (cancelled) {
          stream.getTracks().forEach((t) => t.stop());
          return;
        }
        streamRef.current = stream;
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
          await videoRef.current.play().catch(() => undefined);
        }
      } catch (e) {
        if (!cancelled) setError(cameraError(e));
      }
    })();
    return () => {
      cancelled = true;
      streamRef.current?.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    };
  }, []);

  const take = () => {
    const v = videoRef.current;
    if (!v || !v.videoWidth) return;
    const c = document.createElement("canvas");
    c.width = v.videoWidth;
    c.height = v.videoHeight;
    c.getContext("2d")?.drawImage(v, 0, 0);
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    onCapture(c);
  };

  return (
    <div className="camera">
      {error ? (
        <div className="error inline" role="alert">{error}</div>
      ) : (
        <video ref={videoRef} className="camera-video" playsInline muted onLoadedMetadata={() => setReady(true)}
               aria-label="Camera preview" />
      )}
      <div className="row">
        {!error && <button className="primary" onClick={take} disabled={!ready}>Take picture</button>}
        <button onClick={onCancel}>Cancel</button>
      </div>
      {!error && <p className="muted small">Hold the problem steady and fill the frame. You'll crop it next.</p>}
    </div>
  );
}

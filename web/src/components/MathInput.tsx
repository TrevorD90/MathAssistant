// MathLive <math-field> wrapper with the custom keyboard (spec §5).
// Emits LaTeX. Used for both the initial problem and learner answers.

import { useEffect, useRef } from "react";
import { MathfieldElement } from "mathlive";
import type { MathfieldElement as MF } from "mathlive";
import { LAYOUTS } from "./keyboard/layouts";

let configured = false;

// MathLive finishes setting up a newly mounted <math-field> asynchronously.
// Touching it (focus/setValue) in the same tick can throw inside MathLive, so
// such calls run on the next animation frame and never take the app down.
function whenReady(fn: () => void) {
  requestAnimationFrame(() => {
    try {
      fn();
    } catch (e) {
      console.warn("math field not ready", e);
    }
  });
}

function configureMathlive() {
  if (configured) return;
  configured = true;
  // Fonts are copied into the build (vite.config.ts); no CDN, no sounds.
  MathfieldElement.fontsDirectory = "/mathlive-fonts";
  MathfieldElement.soundsDirectory = null;
  MathfieldElement.plonkSound = null;
  MathfieldElement.keypressSound = null;
  // Custom tabs only (Basic, Algebra, Functions, Calculus, Advanced).
  window.mathVirtualKeyboard.layouts = LAYOUTS;
}

declare module "react" {
  // eslint-disable-next-line @typescript-eslint/no-namespace
  namespace JSX {
    interface IntrinsicElements {
      "math-field": React.DetailedHTMLProps<React.HTMLAttributes<MF>, MF> & {
        "math-virtual-keyboard-policy"?: string;
      };
    }
  }
}

interface Props {
  value: string;
  onChange: (latex: string) => void;
  onSubmit?: () => void;
  placeholder?: string;
  ariaLabel: string;
  autoFocus?: boolean;
  disabled?: boolean;
}

export function MathInput({ value, onChange, onSubmit, placeholder, ariaLabel, autoFocus, disabled }: Props) {
  const ref = useRef<MF>(null);
  const initialValue = useRef(value);
  const onChangeRef = useRef(onChange);
  const onSubmitRef = useRef(onSubmit);
  onChangeRef.current = onChange;
  onSubmitRef.current = onSubmit;

  useEffect(() => {
    configureMathlive();
    const mf = ref.current;
    if (!mf) return;
    mf.smartFence = true;
    mf.mathVirtualKeyboardPolicy = "manual";
    mf.menuItems = []; // no context menu: keep the surface simple
    const handleInput = () => onChangeRef.current(mf.getValue("latex"));
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        onSubmitRef.current?.();
      }
    };
    mf.addEventListener("input", handleInput);
    mf.addEventListener("keydown", handleKey, { capture: true });
    if (autoFocus) whenReady(() => mf.focus());
    return () => {
      mf.removeEventListener("input", handleInput);
      mf.removeEventListener("keydown", handleKey, { capture: true });
    };
  }, [autoFocus]);

  // Keep the field in sync when the parent clears/sets the value.
  useEffect(() => {
    const mf = ref.current;
    if (!mf) return;
    whenReady(() => {
      if (mf.getValue("latex") !== value) mf.setValue(value, { silenceNotifications: true });
    });
  }, [value]);

  useEffect(() => {
    if (ref.current) ref.current.disabled = Boolean(disabled);
  }, [disabled]);

  useEffect(() => {
    if (ref.current) ref.current.placeholder = placeholder ?? "";
  }, [placeholder]);

  return (
    <div className="math-input">
      {/* The starting value goes in as text content: MathLive reads it when the
          element initializes (setValue on a brand-new field can be ignored). */}
      <math-field ref={ref} aria-label={ariaLabel}>{initialValue.current}</math-field>
    </div>
  );
}

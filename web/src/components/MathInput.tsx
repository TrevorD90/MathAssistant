// MathLive <math-field> wrapper with the custom keyboard (spec §5).
// Emits LaTeX. Used for both the initial problem and learner answers.

import { useEffect, useRef } from "react";
import { MathfieldElement } from "mathlive";
import type { MathfieldElement as MF } from "mathlive";
import { LAYOUTS } from "./keyboard/layouts";

let configured = false;

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
    if (autoFocus) mf.focus();
    return () => {
      mf.removeEventListener("input", handleInput);
      mf.removeEventListener("keydown", handleKey, { capture: true });
    };
  }, [autoFocus]);

  // Keep the field in sync when the parent clears/sets the value.
  useEffect(() => {
    const mf = ref.current;
    if (mf && mf.getValue("latex") !== value) mf.setValue(value, { silenceNotifications: true });
  }, [value]);

  useEffect(() => {
    if (ref.current) ref.current.disabled = Boolean(disabled);
  }, [disabled]);

  useEffect(() => {
    if (ref.current) ref.current.placeholder = placeholder ?? "";
  }, [placeholder]);

  return (
    <div className="math-input">
      <math-field ref={ref} aria-label={ariaLabel} />
    </div>
  );
}

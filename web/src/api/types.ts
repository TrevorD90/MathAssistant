// Shapes returned by the backend (see backend/mathassistant/engine/turn_loop.py `view`).

export interface Capabilities {
  vision: boolean;
  structured_output: boolean;
  streaming: boolean;
}

export interface Status {
  provider: string;
  model: string;
  has_key: boolean;
  key_verified: boolean;
  keystore_available: boolean;
  tutoring_enabled: boolean;
  tested: boolean;
  untested_warning: string | null;
  known_model: boolean;
  capabilities: Capabilities;
  dev_mode: boolean;
}

export interface ModelInfo {
  id: string;
  label: string;
  tested: boolean;
  note: string;
}

export interface ProviderInfo {
  id: string;
  label: string;
  key_url: string;
  models: ModelInfo[];
}

export interface ProvidersResponse {
  providers: ProviderInfo[];
  default_provider: string;
  default_model: string;
  untested_warning: string;
}

export interface StepItem {
  index: number;
  title: string;
  status: "done" | "current" | "locked";
}

export interface DisplayItem {
  latex: string;
  caption: string;
}

export interface DisplayPayload {
  type: "latex";
  title: string;
  items: DisplayItem[];
}

export interface TranscriptEntry {
  role: "learner" | "tutor";
  text: string;
  kind: string;
}

export interface ProblemView {
  id: string;
  title: string;
  problem_latex: string;
  problem_kind: "math" | "words";
  level: number;
  status: "in_progress" | "completed";
  phase: "working" | "checking" | "final" | "done";
  step_index: number;
  step_count: number;
  steps: StepItem[];
  current_question: string;
  display: DisplayPayload | null;
  transcript: TranscriptEntry[];
  usage: { tokens_in: number; tokens_out: number; ai_calls: number };
  notice: string | null;
  updated_at: string;
  turn_ai_calls?: number;
}

export interface ProblemSummary {
  id: string;
  title: string;
  problem_latex: string;
  problem_kind: "math" | "words";
  level: number;
  status: string;
  created_at: string;
  updated_at: string;
}

// Phase 2: what the vision call read from an image (for the learner to confirm).
export interface Extraction {
  extraction_id: string;
  readable: boolean;
  kind: "math" | "words";
  latex: string;
  text: string;
  instruction: string;
  note: string;
}

export interface ProblemList {
  in_progress: ProblemSummary[];
  completed: ProblemSummary[];
}

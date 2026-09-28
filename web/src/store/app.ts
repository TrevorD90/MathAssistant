// Global UI state (Zustand). The backend is the source of truth for tutoring
// state; this store only caches the latest views and drives navigation.

import { create } from "zustand";
import { api, ApiError } from "../api/client";
import type { ProblemList, ProblemView, ProvidersResponse, Status } from "../api/types";

export type Screen = "tutor" | "problems" | "settings";

interface AppState {
  screen: Screen;
  status: Status | null;
  providers: ProvidersResponse | null;
  problem: ProblemView | null;
  problems: ProblemList | null;
  busy: boolean;
  error: string | null;
  stopped: boolean;

  init: () => Promise<void>;
  go: (screen: Screen) => void;
  refreshStatus: () => Promise<void>;
  startProblem: (latex: string, text?: string, extractionId?: string | null) => Promise<void>;
  sendTurn: (text: string, latex: string) => Promise<void>;
  newProblem: () => void;
  openProblem: (id: string) => Promise<void>;
  loadProblems: () => Promise<void>;
  deleteProblem: (id: string) => Promise<void>;
  deleteAll: () => Promise<number>;
  setModel: (provider: string, model: string) => Promise<void>;
  testKey: (provider: string, model: string, key?: string) => Promise<boolean>;
  removeKey: (provider: string) => Promise<void>;
  quit: () => Promise<void>;
  clearError: () => void;
}

function message(e: unknown): string {
  return e instanceof ApiError ? e.message : "Something went wrong.";
}

export const useApp = create<AppState>((set, get) => {
  // Run an async action with busy/error handling.
  async function run<T>(fn: () => Promise<T>): Promise<T | undefined> {
    set({ busy: true, error: null });
    try {
      return await fn();
    } catch (e) {
      set({ error: message(e) });
      // Key problems mid-session: refresh status so the UI can route to Settings.
      if (e instanceof ApiError && ["no_key", "key_not_verified", "invalid_key"].includes(e.kind)) {
        void get().refreshStatus();
      }
      return undefined;
    } finally {
      set({ busy: false });
    }
  }

  return {
    screen: "tutor",
    status: null,
    providers: null,
    problem: null,
    problems: null,
    busy: false,
    error: null,
    stopped: false,

    init: async () => {
      await run(async () => {
        const [status, providers] = await Promise.all([api.status(), api.providers()]);
        set({ status, providers, screen: status.tutoring_enabled ? "tutor" : "settings" });
      });
    },

    go: (screen) => {
      set({ screen, error: null });
      if (screen === "problems") void get().loadProblems();
    },

    refreshStatus: async () => {
      try {
        set({ status: await api.status() });
      } catch {
        /* ignore; errors surface on the next action */
      }
    },

    startProblem: async (latex, text = "", extractionId = null) => {
      const view = await run(() => api.startProblem(latex, text, extractionId));
      if (view) set({ problem: view, screen: "tutor" });
    },

    sendTurn: async (text, latex) => {
      const p = get().problem;
      if (!p) return;
      // Optimistically show the learner's message while the tutor replies.
      const shown = latex ? `$${latex}$` : text;
      set({ problem: { ...p, transcript: [...p.transcript, { role: "learner", text: shown, kind: "pending" }] } });
      const view = await run(() => api.turn(p.id, text, latex));
      set({ problem: view ?? p });
    },

    // New problem: the display box and conversation start empty (spec §9.2).
    newProblem: () => set({ problem: null, screen: "tutor", error: null }),

    openProblem: async (id) => {
      const view = await run(() => api.getProblem(id)); // resume: zero AI calls
      if (view) set({ problem: view, screen: "tutor" });
    },

    loadProblems: async () => {
      const problems = await run(() => api.listProblems());
      if (problems) set({ problems });
    },

    deleteProblem: async (id) => {
      await run(() => api.deleteProblem(id));
      if (get().problem?.id === id) set({ problem: null });
      await get().loadProblems();
    },

    deleteAll: async () => {
      const r = await run(() => api.deleteAll());
      set({ problem: null, problems: { in_progress: [], completed: [] } });
      return r?.deleted ?? 0;
    },

    setModel: async (provider, model) => {
      const status = await run(() => api.setModel(provider, model));
      if (status) set({ status });
    },

    testKey: async (provider, model, key) => {
      const r = await run(() => api.testKey(provider, model, key));
      if (r) set({ status: r.status });
      else await get().refreshStatus();
      return Boolean(r?.ok);
    },

    removeKey: async (provider) => {
      const status = await run(() => api.removeKey(provider));
      if (status) set({ status });
    },

    quit: async () => {
      try {
        await api.quit();
      } catch {
        /* server may close before responding */
      }
      set({ stopped: true });
    },

    clearError: () => set({ error: null }),
  };
});

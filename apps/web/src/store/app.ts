import { create } from "zustand";

export type WsStatus = "offline" | "connecting" | "live";

/** Studio interaction mode (v0.9.1): Chat Mode is conversational/read-only,
 * Agent Mode performs project actions. Defaults to Agent Mode so existing
 * Studio behavior is unchanged until the user opts into Chat Mode. */
export type StudioMode = "chat" | "agent";

interface AppState {
  wsStatus: WsStatus;
  setWsStatus: (status: WsStatus) => void;
  studioMode: StudioMode;
  setStudioMode: (mode: StudioMode) => void;
}

export const useAppStore = create<AppState>((set) => ({
  wsStatus: "offline",
  setWsStatus: (wsStatus) => set({ wsStatus }),
  studioMode: "agent",
  setStudioMode: (studioMode) => set({ studioMode }),
}));

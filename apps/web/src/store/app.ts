import { create } from "zustand";

export type WsStatus = "offline" | "connecting" | "live";

interface AppState {
  wsStatus: WsStatus;
  setWsStatus: (status: WsStatus) => void;
}

export const useAppStore = create<AppState>((set) => ({
  wsStatus: "offline",
  setWsStatus: (wsStatus) => set({ wsStatus }),
}));

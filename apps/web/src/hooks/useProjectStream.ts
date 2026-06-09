import { useEffect, useRef } from "react";

import { wsUrl } from "../lib/api";
import type { AgentLabEvent } from "../lib/types";
import { useAppStore } from "../store/app";

/** Subscribe to a project's live event stream with automatic reconnect. */
export function useProjectStream(
  projectId: string | undefined,
  onEvent: (event: AgentLabEvent) => void,
): void {
  const setWsStatus = useAppStore((s) => s.setWsStatus);
  const handlerRef = useRef(onEvent);
  handlerRef.current = onEvent;

  useEffect(() => {
    if (!projectId) return;
    let socket: WebSocket | null = null;
    let closed = false;
    let attempts = 0;
    let timer: number | undefined;

    const connect = () => {
      if (closed) return;
      setWsStatus("connecting");
      socket = new WebSocket(wsUrl(`/ws/projects/${projectId}`));
      socket.onopen = () => {
        attempts = 0;
        setWsStatus("live");
      };
      socket.onmessage = (message: MessageEvent<string>) => {
        try {
          const frame = JSON.parse(message.data) as { type: string; data: AgentLabEvent };
          if (frame.type === "event") handlerRef.current(frame.data);
        } catch {
          // ignore malformed frames
        }
      };
      socket.onclose = () => {
        if (closed) return;
        setWsStatus("offline");
        timer = window.setTimeout(connect, Math.min(1000 * 2 ** attempts++, 10_000));
      };
      socket.onerror = () => socket?.close();
    };

    connect();
    return () => {
      closed = true;
      if (timer !== undefined) window.clearTimeout(timer);
      socket?.close();
      setWsStatus("offline");
    };
  }, [projectId, setWsStatus]);
}

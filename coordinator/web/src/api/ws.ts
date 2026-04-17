import { useEffect, useRef, useCallback } from "react";
import { useQueryClient } from "@tanstack/react-query";
import type { Place, Resource } from "./client";

interface WsMessage {
  type:
    | "initial_state"
    | "place_update"
    | "place_delete"
    | "resource_update"
    | "resource_delete";
  data: Record<string, unknown>;
}

export function useWebSocket() {
  const queryClient = useQueryClient();
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout>>();

  const connect = useCallback(() => {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${protocol}//${window.location.host}/api/ws`;

    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onmessage = (event) => {
      const msg: WsMessage = JSON.parse(event.data);

      switch (msg.type) {
        case "initial_state":
          // Full state replace
          queryClient.setQueryData(
            ["places"],
            (msg.data as { places: Place[] }).places
          );
          queryClient.setQueryData(
            ["resources"],
            (msg.data as { resources: Resource[] }).resources
          );
          break;

        case "place_update":
          queryClient.setQueryData(["places"], (old: Place[] | undefined) => {
            const place = msg.data as unknown as Place;
            if (!old) return [place];
            const idx = old.findIndex((p) => p.name === place.name);
            if (idx >= 0) {
              const next = [...old];
              next[idx] = place;
              return next;
            }
            return [...old, place];
          });
          break;

        case "place_delete": {
          const name = (msg.data as { name: string }).name;
          queryClient.setQueryData(["places"], (old: Place[] | undefined) =>
            old ? old.filter((p) => p.name !== name) : []
          );
          break;
        }

        case "resource_update":
          queryClient.setQueryData(
            ["resources"],
            (old: Resource[] | undefined) => {
              const res = msg.data as unknown as Resource;
              if (!old) return [res];
              const idx = old.findIndex(
                (r) =>
                  r.exporter === res.exporter &&
                  r.group === res.group &&
                  r.name === res.name
              );
              if (idx >= 0) {
                const next = [...old];
                next[idx] = res;
                return next;
              }
              return [...old, res];
            }
          );
          break;

        case "resource_delete": {
          const { exporter, group, name } = msg.data as {
            exporter: string;
            group: string;
            name: string;
          };
          queryClient.setQueryData(
            ["resources"],
            (old: Resource[] | undefined) =>
              old
                ? old.filter(
                    (r) =>
                      !(
                        r.exporter === exporter &&
                        r.group === group &&
                        r.name === name
                      )
                  )
                : []
          );
          break;
        }
      }
    };

    ws.onclose = () => {
      // Reconnect after 3 seconds
      reconnectTimer.current = setTimeout(connect, 3000);
    };

    ws.onerror = () => {
      ws.close();
    };
  }, [queryClient]);

  useEffect(() => {
    connect();
    return () => {
      clearTimeout(reconnectTimer.current);
      wsRef.current?.close();
    };
  }, [connect]);
}

import { useEffect, useRef, useState } from "react";
import { loadStoredToken } from "./auth";

export interface StatsUpdate {
  type: "stats_update";
  sites: string[];
  window: string;
  summary: {
    total_bytes: number;
    protocol_mix: Record<string, number>;
    top_talkers: { src_addr: string; bytes: number }[];
  };
  as_of: string;
}

export interface SiteStatusChanged {
  type: "site_status_changed";
  site_id: string;
  status: "active" | "stale" | "never_connected";
  last_seen_at: string;
}

type RealtimeMessage = StatsUpdate | SiteStatusChanged;

export type ConnectionState = "connecting" | "connected" | "reconnecting";

interface RealtimeState {
  connectionState: ConnectionState;
  latestStats: StatsUpdate | null;
  siteStatus: Record<string, SiteStatusChanged["status"]>;
}

const RECONNECT_DELAY_MS = 2000;

/** Consumes contracts/realtime-channel.md's stats_update/site_status_changed messages,
 * with a visible reconnect indicator on disconnect (constitution Principle III) rather
 * than silently freezing the last-known values. */
export function useRealtimeStats(siteIds: string[]): RealtimeState {
  const [connectionState, setConnectionState] = useState<ConnectionState>("connecting");
  const [latestStats, setLatestStats] = useState<StatsUpdate | null>(null);
  const [siteStatus, setSiteStatus] = useState<Record<string, SiteStatusChanged["status"]>>({});
  const siteIdsKey = siteIds.join(",");

  const socketRef = useRef<WebSocket | null>(null);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const hasConnectedOnceRef = useRef(false);

  useEffect(() => {
    let cancelled = false;

    function connect(): void {
      const token = loadStoredToken();
      if (!token || cancelled) return;

      const scheme = location.protocol === "https:" ? "wss" : "ws";
      const socket = new WebSocket(`${scheme}://${location.host}/api/v1/realtime?token=${token}`);
      socketRef.current = socket;
      setConnectionState(hasConnectedOnceRef.current ? "reconnecting" : "connecting");

      socket.onopen = () => {
        hasConnectedOnceRef.current = true;
        setConnectionState("connected");
        socket.send(JSON.stringify({ sites: siteIds }));
      };

      socket.onmessage = (event) => {
        const message = JSON.parse(event.data) as RealtimeMessage;
        if (message.type === "stats_update") {
          setLatestStats(message);
        } else if (message.type === "site_status_changed") {
          setSiteStatus((prev) => ({ ...prev, [message.site_id]: message.status }));
        }
      };

      socket.onclose = () => {
        if (cancelled) return;
        setConnectionState("reconnecting");
        reconnectTimerRef.current = setTimeout(connect, RECONNECT_DELAY_MS);
      };

      socket.onerror = () => {
        socket.close();
      };
    }

    connect();

    return () => {
      cancelled = true;
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
      socketRef.current?.close();
    };
    // Depends on siteIdsKey (a stable string), not the siteIds array reference, so the
    // socket only reconnects when the actual site set changes.
  }, [siteIdsKey]);

  return { connectionState, latestStats, siteStatus };
}

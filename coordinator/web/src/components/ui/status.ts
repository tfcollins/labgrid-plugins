export type PlaceStatus = "free" | "acquired" | "offline" | "degraded" | "reservation";

/** Maps a status to its semantic color token. */
export const STATUS_TOKEN: Record<PlaceStatus, string> = {
  free: "status.free",
  acquired: "status.acquired",
  offline: "status.offline",
  degraded: "status.degraded",
  reservation: "status.reservation",
};

/** Default visible label per status (callers may override). */
export const STATUS_LABEL: Record<PlaceStatus, string> = {
  free: "ready",
  acquired: "held",
  offline: "offline",
  degraded: "degraded",
  reservation: "reservation",
};

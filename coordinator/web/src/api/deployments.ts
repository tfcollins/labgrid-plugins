const API_BASE = import.meta.env.VITE_API_URL || "/api";

async function request<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    credentials: "include",
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(`${response.status}: ${text}`);
  }

  return response.json();
}

export type DeploymentStatus =
  | "pending"
  | "in_progress"
  | "succeeded"
  | "failed"
  | "cancelled"
  | "offline";

/** A deployment row returned by GET /api/deployments. */
export interface DeploymentSummary {
  hostname: string;
  /** Current attempt number, starting at one. */
  attempt: number;
  /** Desired node configuration revision. */
  generation: number;
  stage: string;
  status: DeploymentStatus;
  /** Completion percentage in the inclusive range 0..100. */
  progress: number;
  ip_address: string | null;
  mac_address: string | null;
  /** ISO-8601 timestamp at which this node was first observed. */
  first_seen: string;
  /** ISO-8601 timestamp of the most recent node update. */
  last_seen: string;
  /** Ordered deployment errors, oldest first. */
  errors: string[];
}

export interface DeploymentTimelineEntry {
  /** ISO-8601 event timestamp. */
  timestamp: string;
  stage: string;
  status: DeploymentStatus;
  message: string;
  /** Progress at this event, or null when it is not applicable. */
  progress: number | null;
}

/** Full response returned by GET /api/deployments/:hostname. */
export interface DeploymentDetail extends DeploymentSummary {
  /** Chronological deployment events, oldest first. */
  timeline: DeploymentTimelineEntry[];
}

export const deploymentsApi = {
  list: () => request<DeploymentSummary[]>("/deployments"),
  get: (hostname: string) =>
    request<DeploymentDetail>(`/deployments/${encodeURIComponent(hostname)}`),
};

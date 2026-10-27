const API_BASE = import.meta.env.VITE_API_URL || "/api";

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
    credentials: "include",
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(`${response.status}: ${text}`);
  }

  if (response.status === 204) {
    return undefined as unknown as T;
  }

  return response.json();
}

export type HealthStatus = "pending" | "running" | "passed" | "failed" | "busy" | "cancelled" | "untested";

export interface HealthCheckRunSummary {
  id: number;
  place_name?: string;
  status: HealthStatus;
  started_at: number;
  finished_at: number | null;
  duration: number | null;
  boot_strategy: string | null;
  image: string | null;
  ip_address: string | null;
  iiod_reachable: boolean;
  drivers?: string[] | null;
  error_message: string | null;
  trigger: "manual" | "scheduled";
  triggered_by: string | null;
  schedule_id?: number | null;
}

export interface HealthCheckRun extends HealthCheckRunSummary {
  place_name: string;
  log_output: string | null;
}

export interface BoardHealthPlace {
  name: string;
  daughter_board: string | null;
  carrier: string | null;
  boot_strategy: string | null;
  acquired: string | null;
  default_image: string | null;
  last_run: HealthCheckRunSummary | null;
}

export interface BoardHealthSummary {
  total_places: number;
  healthy_count: number;
  failing_count: number;
  untested_count: number;
  running_count: number;
  places: BoardHealthPlace[];
}

export interface HealthCheckSchedule {
  id: number;
  name: string;
  description: string | null;
  cron_expression: string;
  places: string[];
  image: string | null;
  power_down: boolean;
  enabled: boolean;
  created_at: number;
  updated_at: number;
  last_run_at: number | null;
  next_run_at: number | null;
}

export interface TriggerRunInput {
  places: string[];
  image?: string | null;
  power_down?: boolean;
  drivers?: boolean;
}

export interface CreateScheduleInput {
  name: string;
  description?: string | null;
  cron_expression: string;
  places: string[];
  image?: string | null;
  power_down?: boolean;
  enabled?: boolean;
}

export interface UpdateScheduleInput {
  name?: string;
  description?: string | null;
  cron_expression?: string;
  places?: string[];
  image?: string | null;
  power_down?: boolean;
  enabled?: boolean;
}

export const boardHealthApi = {
  getSummary(): Promise<BoardHealthSummary> {
    return request<BoardHealthSummary>("/board-health/summary");
  },

  listRuns(filters: { place?: string; status?: string; limit?: number; offset?: number } = {}): Promise<HealthCheckRunSummary[]> {
    const params = new URLSearchParams();
    if (filters.place) params.set("place", filters.place);
    if (filters.status) params.set("status", filters.status);
    if (filters.limit) params.set("limit", String(filters.limit));
    if (filters.offset) params.set("offset", String(filters.offset));
    const query = params.toString();
    return request<HealthCheckRunSummary[]>(`/board-health/runs${query ? `?${query}` : ""}`);
  },

  getRun(runId: number): Promise<HealthCheckRun> {
    return request<HealthCheckRun>(`/board-health/runs/${runId}`);
  },

  triggerRuns(input: TriggerRunInput): Promise<{ id: number; place_name: string; status: string }[]> {
    return request<{ id: number; place_name: string; status: string }[]>("/board-health/runs", {
      method: "POST",
      body: JSON.stringify(input),
    });
  },

  cancelRun(runId: number): Promise<{ status: string }> {
    return request<{ status: string }>(`/board-health/runs/${runId}/cancel`, {
      method: "POST",
    });
  },

  listSchedules(): Promise<HealthCheckSchedule[]> {
    return request<HealthCheckSchedule[]>("/board-health/schedules");
  },

  getSchedule(scheduleId: number): Promise<HealthCheckSchedule> {
    return request<HealthCheckSchedule>(`/board-health/schedules/${scheduleId}`);
  },

  createSchedule(input: CreateScheduleInput): Promise<HealthCheckSchedule> {
    return request<HealthCheckSchedule>("/board-health/schedules", {
      method: "POST",
      body: JSON.stringify(input),
    });
  },

  updateSchedule(scheduleId: number, input: UpdateScheduleInput): Promise<HealthCheckSchedule> {
    return request<HealthCheckSchedule>(`/board-health/schedules/${scheduleId}`, {
      method: "PUT",
      body: JSON.stringify(input),
    });
  },

  deleteSchedule(scheduleId: number): Promise<void> {
    return request<void>(`/board-health/schedules/${scheduleId}`, {
      method: "DELETE",
    });
  },

  triggerSchedule(scheduleId: number): Promise<{ triggered: boolean; run_ids: number[] }> {
    return request<{ triggered: boolean; run_ids: number[] }>(`/board-health/schedules/${scheduleId}/trigger`, {
      method: "POST",
    });
  },
};

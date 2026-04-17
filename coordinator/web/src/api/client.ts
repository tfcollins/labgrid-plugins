const API_BASE = import.meta.env.VITE_API_URL || "/api";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const resp = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    ...options,
  });
  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(`${resp.status}: ${text}`);
  }
  if (resp.status === 204) return undefined as T;
  return resp.json();
}

// Types
export interface ResourceMatch {
  exporter: string;
  group: string;
  cls: string;
  name?: string;
  rename?: string;
}

export interface Place {
  name: string;
  aliases: string[];
  comment: string;
  tags: Record<string, string>;
  matches: ResourceMatch[];
  acquired: string | null;
  acquired_resources: string[][];
  allowed: string[];
  created: number;
  changed: number;
  reservation: string | null;
  acquired_username: string | null;
}

export interface Resource {
  exporter: string;
  group: string;
  cls: string;
  name: string;
  params: Record<string, unknown>;
  acquired: string | null;
  avail: boolean;
}

export interface Exporter {
  name: string;
  groups: Record<string, Resource[]>;
}

export interface ReservationFilter {
  filter: Record<string, string>;
}

export interface Reservation {
  owner: string;
  token: string;
  state: string;
  prio: number;
  filters: Record<string, ReservationFilter>;
  allocations: Record<string, string>;
  created: number;
  timeout: number;
}

export interface HealthStatus {
  status: string;
  coordinator_connected: boolean;
  coordinator_address: string;
}

export interface Event {
  id: number;
  timestamp: number;
  event_type: string;
  place_name: string | null;
  resource_key: string | null;
  user: string | null;
  details: string | null;
}

export interface EventsResponse {
  events: Event[];
  total: number;
}

export interface PlaceStats {
  place_name: string;
  total_sessions: number;
  total_acquired_seconds: number;
  utilization_percent: number;
  last_acquired_by: string | null;
}

export interface PlaceSession {
  user: string;
  acquired_at: number;
  released_at: number | null;
  duration_seconds: number;
}

export interface ResourceStats {
  resource_key: string;
  uptime_percent: number;
  total_online_seconds: number;
  total_offline_seconds: number;
  last_changed: number | null;
}

export interface ExporterStats {
  exporter: string;
  resource_count: number;
  avg_uptime_percent: number;
}

export interface OverviewStats {
  total_events_24h: number;
  avg_acquisition_duration_hours: number;
  busiest_hour: number;
  most_used_place: string | null;
  avg_uptime_percent: number;
}

// API methods
export const api = {
  // Health
  getHealth: () => request<HealthStatus>("/health"),

  // Places
  getPlaces: () => request<Place[]>("/places"),
  getPlace: (name: string) => request<Place>(`/places/${name}`),
  createPlace: (name: string) =>
    request("/places", { method: "POST", body: JSON.stringify({ name }) }),
  deletePlace: (name: string) =>
    request(`/places/${name}`, { method: "DELETE" }),
  acquirePlace: (name: string) =>
    request(`/places/${name}/acquire`, { method: "POST" }),
  releasePlace: (name: string) =>
    request(`/places/${name}/release`, { method: "POST" }),
  setPlaceTags: (name: string, tags: Record<string, string>) =>
    request(`/places/${name}/tags`, {
      method: "PUT",
      body: JSON.stringify({ tags }),
    }),
  setPlaceComment: (name: string, comment: string) =>
    request(`/places/${name}/comment`, {
      method: "PUT",
      body: JSON.stringify({ comment }),
    }),
  addPlaceMatch: (name: string, pattern: string, rename?: string) =>
    request(`/places/${name}/matches`, {
      method: "POST",
      body: JSON.stringify({ pattern, rename }),
    }),
  deletePlaceMatch: (name: string, pattern: string, rename?: string) =>
    request(`/places/${name}/matches`, {
      method: "DELETE",
      body: JSON.stringify({ pattern, rename }),
    }),

  // Resources
  getResources: (params?: {
    exporter?: string;
    cls?: string;
    avail?: boolean;
  }) => {
    const searchParams = new URLSearchParams();
    if (params?.exporter) searchParams.set("exporter", params.exporter);
    if (params?.cls) searchParams.set("cls", params.cls);
    if (params?.avail !== undefined)
      searchParams.set("avail", String(params.avail));
    const qs = searchParams.toString();
    return request<Resource[]>(`/resources${qs ? `?${qs}` : ""}`);
  },
  getExporters: () => request<Exporter[]>("/exporters"),

  // Reservations
  getReservations: () => request<Reservation[]>("/reservations"),
  createReservation: (
    filters: Record<string, Record<string, string>>,
    prio = 0
  ) =>
    request<Reservation>("/reservations", {
      method: "POST",
      body: JSON.stringify({ filters, prio }),
    }),
  cancelReservation: (token: string) =>
    request(`/reservations/${token}`, { method: "DELETE" }),
  pollReservation: (token: string) =>
    request<Reservation>(`/reservations/${token}/poll`, { method: "POST" }),

  // History & Statistics
  getEvents: (params?: {
    limit?: number;
    offset?: number;
    event_type?: string;
    place_name?: string;
  }) => {
    const searchParams = new URLSearchParams();
    if (params?.limit) searchParams.set("limit", String(params.limit));
    if (params?.offset) searchParams.set("offset", String(params.offset));
    if (params?.event_type) searchParams.set("event_type", params.event_type);
    if (params?.place_name) searchParams.set("place_name", params.place_name);
    const qs = searchParams.toString();
    return request<EventsResponse>(`/events${qs ? `?${qs}` : ""}`);
  },
  getStatsOverview: () => request<OverviewStats>("/stats/overview"),
  getPlaceStats: (days = 30) => request<PlaceStats[]>(`/stats/places?days=${days}`),
  getPlaceSessions: (name: string) => request<PlaceSession[]>(`/stats/places/${name}/sessions`),
  getResourceStats: (days = 30) => request<ResourceStats[]>(`/stats/resources?days=${days}`),
  getExporterStats: (days = 30) => request<ExporterStats[]>(`/stats/exporters?days=${days}`),
};

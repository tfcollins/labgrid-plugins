const API_BASE = import.meta.env.VITE_API_URL || "/api";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const resp = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    ...options,
  });
  if (!resp.ok) throw new Error(`${resp.status}: ${await resp.text()}`);
  if (resp.status === 204) return undefined as T;
  return resp.json();
}

export interface Recording {
  id: string;
  place_name: string;
  resource_name: string;
  user_id: number;
  started_at: number;
  ended_at: number | null;
  byte_count: number;
  terminated_reason: string | null;
}

export const recordingsApi = {
  list: (params?: { place_name?: string; resource_name?: string }) => {
    const qs = new URLSearchParams();
    if (params?.place_name) qs.set("place_name", params.place_name);
    if (params?.resource_name) qs.set("resource_name", params.resource_name);
    const tail = qs.toString() ? `?${qs}` : "";
    return request<Recording[]>(`/recordings${tail}`);
  },
  get: (id: string) => request<Recording>(`/recordings/${id}`),
  castUrl: (id: string) => `${API_BASE}/recordings/${id}/cast`,
  delete: (id: string) => request<void>(`/recordings/${id}`, { method: "DELETE" }),
};

const API_BASE = import.meta.env.VITE_API_URL || "/api";

async function request<T>(path: string): Promise<T> {
  const resp = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    credentials: "include",
  });
  if (!resp.ok) throw new Error(`${resp.status}: ${await resp.text()}`);
  return resp.json();
}

export interface NetBoxPowerConnection {
  port_name: string;
  connected_device: string | null;
  connected_outlet: string | null;
}

export interface NetBoxConsoleConnection {
  port_name: string;
  connected_device: string | null;
  connected_port: string | null;
}

export interface NetBoxDevice {
  id: number;
  name: string;
  display: string | null;
  url: string;
  status: string | null;
  site: string | null;
  location: string | null;
  rack: string | null;
  rack_url: string | null;
  position: number | null;
  face: string | null;
  device_type: string | null;
  manufacturer: string | null;
  role: string | null;
  primary_ip: string | null;
  comments: string | null;
  power_connections: NetBoxPowerConnection[];
  console_connections: NetBoxConsoleConnection[];
}

/** `configured` is false when the API has no NetBox URL/token set; `error`
 * says why NetBox couldn't be asked (so "not matched" isn't mistaken for
 * "not in NetBox"). */
export interface PlaceNetBox {
  configured: boolean;
  matched: boolean;
  device: NetBoxDevice | null;
  error: string | null;
}

export const netboxApi = {
  getPlace: (place: string) =>
    request<PlaceNetBox>(`/places/${encodeURIComponent(place)}/netbox`),
};

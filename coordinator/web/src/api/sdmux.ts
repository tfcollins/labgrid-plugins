const API_BASE = import.meta.env.VITE_API_URL || "/api";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const resp = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    ...options,
  });
  if (!resp.ok) throw new Error(`${resp.status}: ${await resp.text()}`);
  return resp.json();
}

export type SDMuxAction = "dut" | "host" | "off" | "client" | "get";
export type SDMuxMode = "dut" | "host" | "off" | "client" | null;

export interface SDMuxResult {
  action: SDMuxAction;
  place: string;
  resource: string | null;
  stdout: string;
  mode: SDMuxMode;
}

export const sdmuxApi = {
  control: (place: string, action: SDMuxAction, resource?: string) => {
    const qs = resource ? `?resource=${encodeURIComponent(resource)}` : "";
    return request<SDMuxResult>(
      `/places/${encodeURIComponent(place)}/sdmux/${action}${qs}`,
      { method: "POST" }
    );
  },
};

// Network-exposed SD mux resources expose PowerProtocol+SDMuxProtocol drivers.
// Match both built-in (USBSDMux/SDWire) and any plugin variants.
const SDMUX_KEYWORDS = ["SDMux", "SDWire"];
export function isSDMuxResource(cls: string): boolean {
  return SDMUX_KEYWORDS.some((k) => cls.includes(k));
}

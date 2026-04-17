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

export type PowerAction = "on" | "off" | "cycle" | "get";

export interface PowerResult {
  action: PowerAction;
  place: string;
  resource: string | null;
  stdout: string;
  state: "on" | "off" | null;
}

export const powerApi = {
  control: (place: string, action: PowerAction, resource?: string) => {
    const qs = resource ? `?resource=${encodeURIComponent(resource)}` : "";
    return request<PowerResult>(
      `/places/${encodeURIComponent(place)}/power/${action}${qs}`,
      { method: "POST" }
    );
  },
};

// Resource class names that map to a labgrid PowerProtocol driver.
// "Power" covers labgrid built-ins (NetworkPowerPort, USBPowerPort,
// YKUSHPowerPort, NetworkUSBPowerPort, ...). "Outlet" covers ADI plugin
// resources (VesyncOutlet, CyberPowerOutlet, HomeAssistantOutlet).
const POWER_CLS_KEYWORDS = ["Power", "Outlet"];
export function isPowerResource(cls: string): boolean {
  return POWER_CLS_KEYWORDS.some((k) => cls.includes(k));
}

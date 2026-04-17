const WS_BASE = (() => {
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${window.location.host}/api`;
})();

export function consoleWebSocketUrl(place: string, resource: string): string {
  return `${WS_BASE}/places/${encodeURIComponent(place)}/resources/${encodeURIComponent(resource)}/console`;
}

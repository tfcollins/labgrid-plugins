/** Render the age of a unix-epoch (seconds) timestamp as a compact string:
 * "0s" / "30s" / "59s" / "1m" / "59m" / "1h" / "23h" / "1d" / "Nd".
 * Future timestamps are clamped to "0s". */
export function formatAge(epochSeconds: number): string {
  const secs = Math.max(0, Math.floor(Date.now() / 1000 - epochSeconds));
  if (secs < 60) return `${secs}s`;
  if (secs < 3600) return `${Math.floor(secs / 60)}m`;
  if (secs < 86400) return `${Math.floor(secs / 3600)}h`;
  return `${Math.floor(secs / 86400)}d`;
}

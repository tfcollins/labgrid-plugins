/** Client-side mirror of the server's infer_strategy() in env_gen.py.
 * Used only for the DownloadEnvModal strategy badge; the server is
 * authoritative for the actual generated yaml. */
export function inferStrategy(resourceClasses: Set<string>): string | null {
  const has = (cls: string) => resourceClasses.has(cls);
  if (
    has("KuiperRelease") &&
    has("NetworkUSBMassStorage") &&
    has("NetworkUSBSDMuxDevice")
  ) {
    return "BootFPGASoC";
  }
  if (has("XilinxDeviceJTAG") && has("XilinxVivadoTool")) {
    return "BootFabric";
  }
  return null;
}

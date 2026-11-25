import { useCallback, useState } from "react";

export const SIDEBAR_COLLAPSED_KEY = "sidebar-collapsed";

function readStored(): boolean {
  try {
    return localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === "true";
  } catch {
    return false;
  }
}

/** Per-browser "sidebar collapsed to the icon rail" preference. Storage
 *  failures (private mode, blocked site data) degrade to in-memory state. */
export function useSidebarCollapsed() {
  const [collapsed, setCollapsed] = useState<boolean>(readStored);

  const toggle = useCallback(() => {
    const next = !collapsed;
    setCollapsed(next);
    try {
      localStorage.setItem(SIDEBAR_COLLAPSED_KEY, String(next));
    } catch {
      // Storage unavailable: the preference lasts for this page load only.
    }
  }, [collapsed]);

  return { collapsed, toggle };
}

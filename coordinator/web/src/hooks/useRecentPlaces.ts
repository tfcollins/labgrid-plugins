import { useCallback, useEffect, useState } from "react";
import { useAuth } from "../auth/AuthContext";

const MAX_RECENT = 5;
const storageKey = (username: string) => `recent-places:${username}`;

/** Client-side "places I've recently opened" list, keyed by username.
 * `record(name)` pushes to the head, dedupes, caps to MAX_RECENT. */
export function useRecentPlaces() {
  const { user } = useAuth();
  const key = user ? storageKey(user.username) : null;

  const [recent, setRecent] = useState<string[]>(() => {
    if (!key) return [];
    try {
      const raw = localStorage.getItem(key);
      return raw ? JSON.parse(raw) : [];
    } catch {
      return [];
    }
  });

  useEffect(() => {
    if (!key) return;
    try {
      const raw = localStorage.getItem(key);
      setRecent(raw ? JSON.parse(raw) : []);
    } catch {
      setRecent([]);
    }
  }, [key]);

  const record = useCallback(
    (name: string) => {
      if (!key) return;
      setRecent((prev) => {
        const next = [name, ...prev.filter((x) => x !== name)].slice(0, MAX_RECENT);
        localStorage.setItem(key, JSON.stringify(next));
        return next;
      });
    },
    [key],
  );

  return { recent, record };
}

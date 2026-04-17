import { useMemo } from "react";
import type { Place, Exporter, ResourceMatch } from "../api/client";
import { usePlaces } from "./usePlaces";
import { useExporters } from "./useResources";

export interface ExporterSummary {
  name: string;
  online: boolean;
}
export interface PlaceSummary {
  name: string;
  acquired: string | null;
}
export type PlaceHealth = "ready" | "held" | "degraded";

export interface Relationships {
  /** place name -> distinct exporters that currently contribute a live resource. */
  placeToExporters: Map<string, ExporterSummary[]>;
  /** exporter name -> places that match this exporter (regardless of live-match status). */
  exporterToPlaces: Map<string, PlaceSummary[]>;
  /** "exporter/group/cls/name" -> places currently matching that live resource. */
  resourceToPlaces: Map<string, PlaceSummary[]>;
  /** place name -> match rules that didn't resolve to any live resource. */
  placeToMissingMatches: Map<string, ResourceMatch[]>;
  /** place name -> overall health signal. */
  placeHealth: Map<string, PlaceHealth>;
}

/** Wildcards supported: exporter, group, cls can each be "*". `name` is only
 * considered when the match rule specifies it (undefined or missing = match any name). */
function matchApplies(
  m: ResourceMatch,
  r: { exporter: string; group: string; cls: string; name: string },
): boolean {
  if (m.exporter !== "*" && m.exporter !== r.exporter) return false;
  if (m.group !== "*" && m.group !== r.group) return false;
  if (m.cls !== "*" && m.cls !== r.cls) return false;
  if (m.name && m.name !== r.name) return false;
  return true;
}

const resourceKey = (exporter: string, group: string, cls: string, name: string) =>
  `${exporter}/${group}/${cls}/${name}`;

/** Pure, testable derivation. Exposed separately so tests don't need
 * the React Query + WebSocket stack. */
export function deriveRelationships(places: Place[], exporters: Exporter[]): Relationships {
  const placeToExporters = new Map<string, ExporterSummary[]>();
  const exporterToPlaces = new Map<string, PlaceSummary[]>();
  const resourceToPlaces = new Map<string, PlaceSummary[]>();
  const placeToMissingMatches = new Map<string, ResourceMatch[]>();
  const placeHealth = new Map<string, PlaceHealth>();

  const liveResources = exporters.flatMap((e) =>
    Object.entries(e.groups).flatMap(([g, list]) =>
      list.filter((r) => r.avail).map((r) => ({ ...r, group: g, exporter: e.name })),
    ),
  );
  const exporterIsOnline = new Map<string, boolean>(
    exporters.map((e) => [e.name, Object.keys(e.groups).length > 0]),
  );

  for (const place of places) {
    const contributing = new Set<string>();
    const missing: ResourceMatch[] = [];

    for (const m of place.matches) {
      const hits = liveResources.filter((r) => matchApplies(m, r));
      if (hits.length === 0) {
        missing.push(m);
        continue;
      }
      for (const hit of hits) {
        contributing.add(hit.exporter);
        const key = resourceKey(hit.exporter, hit.group, hit.cls, hit.name);
        const arr = resourceToPlaces.get(key) ?? [];
        if (!arr.some((p) => p.name === place.name)) {
          arr.push({ name: place.name, acquired: place.acquired });
        }
        resourceToPlaces.set(key, arr);
      }
    }

    placeToExporters.set(
      place.name,
      [...contributing]
        .sort()
        .map((name) => ({ name, online: exporterIsOnline.get(name) ?? false })),
    );
    placeToMissingMatches.set(place.name, missing);

    placeHealth.set(
      place.name,
      place.acquired ? "held" : missing.length > 0 ? "degraded" : "ready",
    );

    // exporterToPlaces: include any exporter named in a match, even if the
    // rule doesn't currently resolve. A user viewing the exporter page wants
    // to see every place that references it.
    const named = new Set<string>();
    for (const m of place.matches) {
      if (m.exporter !== "*") named.add(m.exporter);
    }
    for (const exp of exporters) {
      const referenced =
        [...named].includes(exp.name) || place.matches.some((m) => m.exporter === "*");
      if (!referenced) continue;
      const arr = exporterToPlaces.get(exp.name) ?? [];
      if (!arr.some((p) => p.name === place.name)) {
        arr.push({ name: place.name, acquired: place.acquired });
      }
      exporterToPlaces.set(exp.name, arr);
    }
  }

  return {
    placeToExporters,
    exporterToPlaces,
    resourceToPlaces,
    placeToMissingMatches,
    placeHealth,
  };
}

/** React Query-backed hook used by real pages. Memoizes on the underlying
 * places/exporters query data so consumers re-render only when upstream does. */
export function useRelationships(): Relationships {
  const places = usePlaces().data ?? [];
  const exporters = useExporters().data ?? [];
  return useMemo(() => deriveRelationships(places, exporters), [places, exporters]);
}

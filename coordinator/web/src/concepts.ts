// coordinator/web/src/concepts.ts

export interface ConceptEntry {
  /** CLI / UI term as it appears (e.g. "Place"). */
  label: string;
  /** One-sentence plain-language gloss shown under headings and in tooltips. */
  gloss: string;
  /** Chakra color keyword / hex used by Topology legend and the Dashboard
   *  glance card, so visual identity is consistent across pages. */
  color: string;
}

export const CONCEPTS = {
  exporter: {
    label: "Exporter",
    gloss: "A lab host running labgrid-exporter that publishes hardware to the coordinator.",
    color: "#0071ba", // matches Topology EXPORTER_COLOR
  },
  group: {
    label: "Group",
    gloss: "A named set of resources an exporter publishes together (for example `tlab`).",
    color: "#1e9bd7", // matches Topology GROUP_COLOR
  },
  resource: {
    label: "Resource",
    gloss: "An individual piece of hardware an exporter publishes — a serial port, power outlet, SD mux, etc.",
    color: "#2b6cb0",
  },
  place: {
    label: "Place",
    gloss: "A bundle of hardware you reserve. Each place matches one or more resources from one or more exporters.",
    color: "#38a169", // matches Topology PLACE_FREE_COLOR
  },
  acquire: {
    label: "Acquire",
    gloss: "Take an exclusive lock on a place. Only the user who holds the lock can use the place's resources until they release it.",
    color: "#dd6b20", // matches Topology PLACE_ACQUIRED_COLOR
  },
  match: {
    label: "Match",
    gloss: "A rule on a place that says which exporter resources it pulls (for example `bq/tlab/*`).",
    color: "#4a5568",
  },
  rename: {
    label: "Rename",
    gloss: "Optional alias that lets a place expose a resource under a friendlier name to drivers and strategies.",
    color: "#4a5568",
  },
  reservation: {
    label: "Reservation",
    gloss: "A queued claim on a place that matches a tag filter. The coordinator allocates a matching place when one frees; the holder can then acquire it.",
    color: "#ecc94b",
  },
} as const;

export type ConceptName = keyof typeof CONCEPTS;

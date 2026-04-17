import { describe, it, expect } from "vitest";
import { deriveRelationships } from "../useRelationships";
import type { Place, Exporter } from "../../api/client";

const makeExporter = (name: string, groups: Record<string, string[]>, avail = true): Exporter => ({
  name,
  groups: Object.fromEntries(
    Object.entries(groups).map(([g, cls]) => [
      g,
      cls.map((c) => ({
        exporter: name, group: g, cls: c, name: c,
        params: {}, acquired: null, avail,
      })),
    ]),
  ),
});

const makePlace = (
  name: string,
  matches: Array<{ exporter: string; group: string; cls: string; name?: string }>,
  acquired: string | null = null,
): Place => ({
  name, aliases: [], comment: "", tags: {}, matches,
  acquired, acquired_resources: [], allowed: [],
  created: 0, changed: 0, reservation: null,
  acquired_username: acquired ? "alice" : null,
});

describe("deriveRelationships", () => {
  it("links a place to its contributing exporters", () => {
    const exp = makeExporter("bq", { tlab: ["NetworkSerialPort"] });
    const p = makePlace("bq", [{ exporter: "bq", group: "tlab", cls: "*" }]);
    const r = deriveRelationships([p], [exp]);
    expect(r.placeToExporters.get("bq")?.map((e) => e.name)).toEqual(["bq"]);
    expect(r.exporterToPlaces.get("bq")?.map((p) => p.name)).toEqual(["bq"]);
  });

  it("supports wildcard exporter match", () => {
    const e1 = makeExporter("bq", { tlab: ["NetworkSerialPort"] });
    const e2 = makeExporter("mini2", { tlab: ["NetworkSerialPort"] });
    const p = makePlace("wild", [{ exporter: "*", group: "tlab", cls: "*" }]);
    const r = deriveRelationships([p], [e1, e2]);
    expect(new Set(r.placeToExporters.get("wild")?.map((e) => e.name))).toEqual(new Set(["bq", "mini2"]));
  });

  it("flags a match rule as missing when no live resource matches", () => {
    const exp = makeExporter("bq", { tlab: ["NetworkSerialPort"] });
    const p = makePlace("bq", [{ exporter: "bq", group: "tlab", cls: "USBSDMuxDevice" }]);
    const r = deriveRelationships([p], [exp]);
    const missing = r.placeToMissingMatches.get("bq") ?? [];
    expect(missing).toHaveLength(1);
    expect(missing[0].cls).toBe("USBSDMuxDevice");
  });

  it("reports placeHealth=degraded when any match is missing", () => {
    const exp = makeExporter("bq", { tlab: ["NetworkSerialPort"] });
    const p = makePlace("bq", [
      { exporter: "bq", group: "tlab", cls: "NetworkSerialPort" },
      { exporter: "bq", group: "tlab", cls: "USBSDMuxDevice" },
    ]);
    expect(deriveRelationships([p], [exp]).placeHealth.get("bq")).toBe("degraded");
  });

  it("reports placeHealth=held when acquired, regardless of match health", () => {
    const exp = makeExporter("bq", { tlab: ["NetworkSerialPort"] });
    const p = makePlace("bq", [{ exporter: "bq", group: "tlab", cls: "*" }], "alice");
    expect(deriveRelationships([p], [exp]).placeHealth.get("bq")).toBe("held");
  });

  it("resourceToPlaces maps live resource keys to their matching places", () => {
    const exp = makeExporter("bq", { tlab: ["NetworkSerialPort"] });
    const p = makePlace("bq", [{ exporter: "bq", group: "tlab", cls: "*" }]);
    const r = deriveRelationships([p], [exp]);
    expect(r.resourceToPlaces.get("bq/tlab/NetworkSerialPort/NetworkSerialPort")?.map((p) => p.name)).toEqual(["bq"]);
  });

  it("treats an exporter with no groups as offline for place-health purposes", () => {
    const exp: Exporter = { name: "bq", groups: {} };
    const p = makePlace("bq", [{ exporter: "bq", group: "tlab", cls: "*" }]);
    expect(deriveRelationships([p], [exp]).placeHealth.get("bq")).toBe("degraded");
  });

  it("keeps exporterToPlaces entries even when the match has no live resource", () => {
    // exporter is published but has no resources of the class the place wants
    const exp = makeExporter("bq", { tlab: ["NetworkSerialPort"] });
    const p = makePlace("bq", [{ exporter: "bq", group: "tlab", cls: "USBSDMuxDevice" }]);
    const r = deriveRelationships([p], [exp]);
    expect(r.exporterToPlaces.get("bq")?.map((p) => p.name)).toEqual(["bq"]);
    // And the place itself is flagged as degraded via the missing match.
    expect(r.placeToMissingMatches.get("bq")).toHaveLength(1);
  });

  it("supports wildcard cls combined with a specific resource name", () => {
    const exp = makeExporter("bq", { tlab: ["NetworkSerialPort", "USBSDMuxDevice"] });
    const p = makePlace("bq", [{ exporter: "bq", group: "tlab", cls: "*", name: "USBSDMuxDevice" }]);
    const r = deriveRelationships([p], [exp]);
    // Only the resource whose `name` matches should be picked up.
    expect(r.resourceToPlaces.get("bq/tlab/USBSDMuxDevice/USBSDMuxDevice")?.map((p) => p.name)).toEqual(["bq"]);
    expect(r.resourceToPlaces.get("bq/tlab/NetworkSerialPort/NetworkSerialPort")).toBeUndefined();
  });
});

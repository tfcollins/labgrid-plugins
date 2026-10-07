import { afterEach, describe, expect, it, vi } from "vitest";
import { deploymentsApi } from "../deployments";

describe("deploymentsApi", () => {
  afterEach(() => vi.restoreAllMocks());

  it("lists deployments with credentials", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify([]), { status: 200 }),
    );

    await deploymentsApi.list();

    expect(fetchMock).toHaveBeenCalledWith("/api/deployments", {
      headers: { "Content-Type": "application/json" },
      credentials: "include",
    });
  });

  it("encodes hostnames in detail requests", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({}), { status: 200 }),
    );

    await deploymentsApi.get("rack/node 1");

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/deployments/rack%2Fnode%201",
      expect.any(Object),
    );
  });
});

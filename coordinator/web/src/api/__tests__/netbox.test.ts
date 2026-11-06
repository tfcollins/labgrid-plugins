import { afterEach, describe, expect, it, vi } from "vitest";
import { netboxApi } from "../netbox";

describe("netboxApi", () => {
  afterEach(() => vi.restoreAllMocks());

  it("requests the place's NetBox lookup with credentials", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ configured: false, matched: false, device: null }), {
        status: 200,
      }),
    );

    const res = await netboxApi.getPlace("rack/a b");

    expect(fetchMock).toHaveBeenCalledWith("/api/places/rack%2Fa%20b/netbox", {
      headers: { "Content-Type": "application/json" },
      credentials: "include",
    });
    expect(res.configured).toBe(false);
  });
});

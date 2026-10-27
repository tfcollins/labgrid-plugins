import { afterEach, describe, expect, it, vi } from "vitest";
import { boardHealthApi } from "../boardHealth";

describe("boardHealthApi", () => {
  afterEach(() => vi.restoreAllMocks());

  it("fetches summary", async () => {
    const mockSummary = {
      total_places: 2,
      healthy_count: 1,
      failing_count: 0,
      untested_count: 1,
      running_count: 0,
      places: [],
    };
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify(mockSummary), { status: 200 }),
    );

    const data = await boardHealthApi.getSummary();
    expect(data.total_places).toBe(2);
    expect(fetchMock).toHaveBeenCalledWith("/api/board-health/summary", expect.any(Object));
  });

  it("triggers health checks with json payload", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify([{ id: 1, place_name: "mini2", status: "pending" }]), { status: 202 }),
    );

    await boardHealthApi.triggerRuns({ places: ["mini2"], image: "2023_R2_P1" });

    expect(fetchMock).toHaveBeenCalledWith("/api/board-health/runs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({ places: ["mini2"], image: "2023_R2_P1" }),
    });
  });

  it("creates recurring schedule", async () => {
    const mockSched = {
      id: 1,
      name: "Nightly Check",
      cron_expression: "0 2 * * *",
      places: ["*"],
    };
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify(mockSched), { status: 201 }),
    );

    const sched = await boardHealthApi.createSchedule({
      name: "Nightly Check",
      cron_expression: "0 2 * * *",
      places: ["*"],
    });

    expect(sched.id).toBe(1);
    expect(fetchMock).toHaveBeenCalledWith("/api/board-health/schedules", expect.any(Object));
  });
});

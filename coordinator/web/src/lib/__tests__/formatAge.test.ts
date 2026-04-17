import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { formatAge } from "../formatAge";

// Freeze "now" at a deterministic epoch so elapsed math is predictable.
const NOW_EPOCH_SEC = 1_700_000_000;

describe("formatAge", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date(NOW_EPOCH_SEC * 1000));
  });
  afterEach(() => vi.useRealTimers());

  it("renders seconds under a minute", () => {
    expect(formatAge(NOW_EPOCH_SEC)).toBe("0s");
    expect(formatAge(NOW_EPOCH_SEC - 30)).toBe("30s");
    expect(formatAge(NOW_EPOCH_SEC - 59)).toBe("59s");
  });

  it("renders minutes between 1m and 1h", () => {
    expect(formatAge(NOW_EPOCH_SEC - 60)).toBe("1m");
    expect(formatAge(NOW_EPOCH_SEC - 3599)).toBe("59m");
  });

  it("renders hours between 1h and 1d", () => {
    expect(formatAge(NOW_EPOCH_SEC - 3600)).toBe("1h");
    expect(formatAge(NOW_EPOCH_SEC - 86_399)).toBe("23h");
  });

  it("renders days at and beyond 1d", () => {
    expect(formatAge(NOW_EPOCH_SEC - 86_400)).toBe("1d");
    expect(formatAge(NOW_EPOCH_SEC - 172_800)).toBe("2d");
  });

  it("clamps negative (future) timestamps to 0s", () => {
    expect(formatAge(NOW_EPOCH_SEC + 100)).toBe("0s");
  });
});

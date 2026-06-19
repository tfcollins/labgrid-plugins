import { describe, it, expect } from "vitest";
import { colors, fonts, radii } from "../tokens";

describe("theme tokens", () => {
  it("keeps the ADI brand blue palette anchored at 500/400", () => {
    expect(colors.adi[500]).toBe("#0071ba");
    expect(colors.adi[400]).toBe("#1e9bd7");
  });

  it("uses the new distinctive font families, not Inter", () => {
    expect(fonts.heading).toContain("Hanken Grotesk");
    expect(fonts.body).toContain("Public Sans");
    expect(fonts.mono).toContain("IBM Plex Mono");
    expect(`${fonts.heading} ${fonts.body}`).not.toContain("Inter");
  });

  it("defines a small consistent radius scale", () => {
    expect(radii.md).toBe("5px");
  });
});

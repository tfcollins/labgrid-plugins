import { describe, it, expect } from "vitest";
import theme from "../index";

describe("assembled theme", () => {
  it("preserves color-mode config", () => {
    expect(theme.config.initialColorMode).toBe("light");
    expect(theme.config.useSystemColorMode).toBe(true);
  });
  it("wires fonts, the ADI palette, and semantic tokens together", () => {
    expect(theme.fonts.body).toContain("Public Sans");
    expect(theme.colors.adi[500]).toBe("#0071ba");
    expect(theme.semanticTokens.colors["status.free"].default).toBe("#38a169");
  });
});

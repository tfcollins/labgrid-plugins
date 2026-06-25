import { describe, it, expect } from "vitest";
import { semanticTokens } from "../semanticTokens";

const c = semanticTokens.colors;

describe("semantic tokens", () => {
  it("defines co-equal light + dark surfaces", () => {
    expect(c["page.bg"]).toEqual({ default: "#fafbfc", _dark: "#0b0f14" });
    expect(c["surface.bg"]).toEqual({ default: "#ffffff", _dark: "#0e141b" });
    expect(c["surface.subtle"]).toEqual({ default: "#f3f5f7", _dark: "#161f2a" });
    expect(c["border.hairline"]).toEqual({ default: "#e4e8ec", _dark: "#1c2530" });
  });

  it("maps accent, link and the retained accent.text alias to ADI blue per mode", () => {
    const adi = { default: "adi.500", _dark: "adi.400" };
    expect(c["accent"]).toEqual(adi);
    expect(c["link"]).toEqual(adi);
    expect(c["accent.text"]).toEqual(adi); // retained so Statistics.tsx:42 keeps working
  });

  it("defines all five status tokens with AA-safe dark variants", () => {
    expect(c["status.free"]).toEqual({ default: "#38a169", _dark: "#48bb78" });
    expect(c["status.acquired"]).toEqual({ default: "#dd6b20", _dark: "#ed8936" });
    expect(c["status.offline"]).toEqual({ default: "#718096", _dark: "#a0aec0" });
    expect(c["status.degraded"]).toEqual({ default: "#e53e3e", _dark: "#fc8181" });
    expect(c["status.reservation"]).toEqual({ default: "#d69e2e", _dark: "#f6e05e" });
  });

  it("keeps text.secondary AA-legible (no faint grays)", () => {
    expect(c["text.secondary"]).toEqual({ default: "#52606d", _dark: "#9fb0c0" });
  });
});

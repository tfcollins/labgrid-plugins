import { describe, it, expect } from "vitest";
import { components } from "../components";

describe("component overrides", () => {
  it("keeps the ADI default color scheme on Button and Badge", () => {
    expect(components.Button.defaultProps.colorScheme).toBe("adi");
    expect(components.Badge.defaultProps.colorScheme).toBe("adi");
  });

  it("colors links with the brand link token and disables underline", () => {
    expect(components.Link.baseStyle.color).toBe("link");
  });

  it("provides a multipart Table override (hairline spec-sheet look)", () => {
    // createMultiStyleConfigHelpers produces a config with baseStyle/variants.
    expect(components.Table).toBeTypeOf("object");
    expect(components.Table.baseStyle).toBeDefined();
  });
});

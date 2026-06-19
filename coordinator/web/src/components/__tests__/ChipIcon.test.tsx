import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";
import ChipIcon from "../ChipIcon";

describe("ChipIcon", () => {
  it("uses currentColor for the chip body so it adapts to the sidebar fg", () => {
    const { container } = render(<ChipIcon size={36} />);
    const strokes = [...container.querySelectorAll("[stroke]")].map((n) => n.getAttribute("stroke"));
    expect(strokes).toContain("currentColor");
    expect(strokes).not.toContain("#e6edf3"); // the old hardcoded light color is gone
  });
});

import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { ChakraProvider } from "@chakra-ui/react";
import theme from "../../../theme";
import UtilizationBar from "../UtilizationBar";

const wrap = (ui: React.ReactNode) => <ChakraProvider theme={theme}>{ui}</ChakraProvider>;

describe("UtilizationBar", () => {
  it("describes the breakdown for screen readers and renders 3 segments", () => {
    render(wrap(<UtilizationBar free={6} acquired={4} offline={2} />));
    const bar = screen.getByRole("img");
    expect(bar).toHaveAttribute("aria-label", "12 places: 6 free, 4 acquired, 2 offline");
    expect(bar.querySelectorAll("[data-seg]").length).toBe(3);
  });
  it("does not crash when there are no places", () => {
    render(wrap(<UtilizationBar free={0} acquired={0} offline={0} />));
    expect(screen.getByRole("img")).toHaveAttribute("aria-label", "0 places: 0 free, 0 acquired, 0 offline");
  });
});

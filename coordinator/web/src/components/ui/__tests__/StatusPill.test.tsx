import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { ChakraProvider } from "@chakra-ui/react";
import theme from "../../../theme";
import StatusPill from "../StatusPill";

const wrap = (ui: React.ReactNode) => <ChakraProvider theme={theme}>{ui}</ChakraProvider>;

describe("StatusPill", () => {
  it("renders the default label for a status", () => {
    render(wrap(<StatusPill status="free" />));
    expect(screen.getByText("ready")).toBeInTheDocument();
  });
  it("renders an overriding label (e.g. the degraded count)", () => {
    render(wrap(<StatusPill status="degraded">3 not live</StatusPill>));
    expect(screen.getByText("3 not live")).toBeInTheDocument();
    expect(screen.getByTestId("status-dot")).toHaveAttribute("data-status", "degraded");
  });
});

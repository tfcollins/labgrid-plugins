import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { ChakraProvider } from "@chakra-ui/react";
import theme from "../../../theme";
import StatusDot from "../StatusDot";

const wrap = (ui: React.ReactNode) => <ChakraProvider theme={theme}>{ui}</ChakraProvider>;

describe("StatusDot", () => {
  it("exposes its status for assertions", () => {
    render(wrap(<StatusDot status="degraded" />));
    expect(screen.getByTestId("status-dot")).toHaveAttribute("data-status", "degraded");
  });
});

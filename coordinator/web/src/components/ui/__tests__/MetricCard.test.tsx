import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { ChakraProvider } from "@chakra-ui/react";
import { MemoryRouter } from "react-router-dom";
import theme from "../../../theme";
import MetricCard from "../MetricCard";

const wrap = (ui: React.ReactNode) => (
  <ChakraProvider theme={theme}><MemoryRouter>{ui}</MemoryRouter></ChakraProvider>
);

describe("MetricCard", () => {
  it("renders label + value", () => {
    render(wrap(<MetricCard label="Places" value="12 total" />));
    expect(screen.getByText("Places")).toBeInTheDocument();
    expect(screen.getByText("12 total")).toBeInTheDocument();
  });
  it("wraps in a router link when `to` is provided", () => {
    render(wrap(<MetricCard label="Places" value="12" to="/places" />));
    expect(screen.getByRole("link")).toHaveAttribute("href", "/places");
  });
});

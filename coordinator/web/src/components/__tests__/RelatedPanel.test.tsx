import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { ChakraProvider } from "@chakra-ui/react";
import RelatedPanel from "../RelatedPanel";

const wrap = (ui: React.ReactNode) => (
  <ChakraProvider>
    <MemoryRouter>{ui}</MemoryRouter>
  </ChakraProvider>
);

describe("RelatedPanel", () => {
  it("renders sections with given title + children", () => {
    render(wrap(
      <RelatedPanel>
        <RelatedPanel.Section title="Exporters">
          <span>bq</span>
        </RelatedPanel.Section>
      </RelatedPanel>
    ));
    expect(screen.getByText("Exporters")).toBeInTheDocument();
    expect(screen.getByText("bq")).toBeInTheDocument();
  });

  it("renders warning-tone section with distinct styling", () => {
    render(wrap(
      <RelatedPanel>
        <RelatedPanel.Section title="Missing" tone="warning">
          <span>foo</span>
        </RelatedPanel.Section>
      </RelatedPanel>
    ));
    const heading = screen.getByText("Missing");
    expect(heading).toHaveAttribute("data-tone", "warning");
  });

  it("renders footer with a router link", () => {
    render(wrap(
      <RelatedPanel>
        <RelatedPanel.Footer to="/topology?focus=place:mini2">
          Show in Topology →
        </RelatedPanel.Footer>
      </RelatedPanel>
    ));
    const link = screen.getByRole("link", { name: /show in topology/i });
    expect(link).toHaveAttribute("href", "/topology?focus=place:mini2");
  });
});

import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { ChakraProvider } from "@chakra-ui/react";
import theme from "../../../theme";
import Panel from "../Panel";
import { MicroLabel, SectionLabel } from "../Labels";

const wrap = (ui: React.ReactNode) => <ChakraProvider theme={theme}>{ui}</ChakraProvider>;

describe("Panel + labels", () => {
  it("renders Panel children", () => {
    render(wrap(<Panel>inside</Panel>));
    expect(screen.getByText("inside")).toBeInTheDocument();
  });
  it("renders an uppercased micro-label and a section label", () => {
    render(wrap(<><MicroLabel>exporters</MicroLabel><SectionLabel>Places</SectionLabel></>));
    expect(screen.getByText("exporters")).toBeInTheDocument();
    expect(screen.getByText("Places")).toBeInTheDocument();
  });
});

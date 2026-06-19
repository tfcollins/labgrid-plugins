import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { ChakraProvider } from "@chakra-ui/react";
import { MemoryRouter } from "react-router-dom";
import { MdDashboard } from "react-icons/md";
import theme from "../../../theme";
import NavItem from "../NavItem";

const wrap = (ui: React.ReactNode) => (
  <ChakraProvider theme={theme}><MemoryRouter>{ui}</MemoryRouter></ChakraProvider>
);

describe("NavItem", () => {
  it("marks the active item with aria-current=page", () => {
    render(wrap(<NavItem to="/" icon={MdDashboard} label="Dashboard" isActive />));
    expect(screen.getByRole("link", { name: "Dashboard" })).toHaveAttribute("aria-current", "page");
  });
  it("does not set aria-current when inactive", () => {
    render(wrap(<NavItem to="/places" icon={MdDashboard} label="Places" isActive={false} />));
    expect(screen.getByRole("link", { name: "Places" })).not.toHaveAttribute("aria-current");
  });
});

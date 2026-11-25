import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import { ChakraProvider } from "@chakra-ui/react";
import { MemoryRouter } from "react-router-dom";
import theme from "../../theme";
import Layout from "../Layout";
import { SIDEBAR_COLLAPSED_KEY } from "../../hooks/useSidebarCollapsed";

vi.mock("../AccountMenu", () => ({ default: () => null }));

const wrap = (ui: React.ReactNode) => (
  <ChakraProvider theme={theme}>
    <MemoryRouter>{ui}</MemoryRouter>
  </ChakraProvider>
);

const renderLayout = () => render(wrap(<Layout><p>page body</p></Layout>));

const originalMatchMedia = window.matchMedia;

/** Make every max-width media query (the narrow-screen check) match. */
function useNarrowViewport() {
  window.matchMedia = ((query: string) => ({
    matches: query.includes("max-width"),
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  })) as typeof window.matchMedia;
}

describe("Layout sidebar", () => {
  beforeEach(() => localStorage.clear());
  afterEach(() => {
    window.matchMedia = originalMatchMedia;
  });

  it("starts expanded with a labelled toggle button controlling the sidebar", () => {
    renderLayout();
    const toggle = screen.getByRole("button", { name: "Collapse sidebar" });
    expect(toggle.tagName).toBe("BUTTON");
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    const nav = screen.getByRole("navigation", { name: "Main" });
    expect(toggle).toHaveAttribute("aria-controls", nav.id);
    expect(within(nav).getByText("Dashboard")).toBeInTheDocument();
    expect(within(nav).getByText("Coordinator Dashboard")).toBeInTheDocument();
  });

  it("collapses to an icon rail that keeps every link reachable by name", () => {
    renderLayout();
    fireEvent.click(screen.getByRole("button", { name: "Collapse sidebar" }));

    const toggle = screen.getByRole("button", { name: "Expand sidebar" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    const nav = screen.getByRole("navigation", { name: "Main" });
    expect(within(nav).queryByText("Dashboard")).not.toBeInTheDocument();
    expect(within(nav).queryByText("Coordinator Dashboard")).not.toBeInTheDocument();
    expect(within(nav).getByRole("link", { name: "Dashboard" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(within(nav).getByRole("link", { name: "Places" })).toBeInTheDocument();
    expect(within(nav).getByRole("link", { name: "labgrid-plugins docs" })).toBeInTheDocument();
    expect(screen.getByText("page body")).toBeInTheDocument();
  });

  it("expands again on a second click", () => {
    renderLayout();
    fireEvent.click(screen.getByRole("button", { name: "Collapse sidebar" }));
    fireEvent.click(screen.getByRole("button", { name: "Expand sidebar" }));
    expect(screen.getByRole("button", { name: "Collapse sidebar" })).toHaveAttribute(
      "aria-expanded",
      "true",
    );
    expect(screen.getByText("Coordinator Dashboard")).toBeInTheDocument();
  });

  it("remembers the collapsed state across mounts", () => {
    const first = renderLayout();
    fireEvent.click(screen.getByRole("button", { name: "Collapse sidebar" }));
    expect(localStorage.getItem(SIDEBAR_COLLAPSED_KEY)).toBe("true");
    first.unmount();

    renderLayout();
    expect(screen.getByRole("button", { name: "Expand sidebar" })).toHaveAttribute(
      "aria-expanded",
      "false",
    );
  });

  describe("on a narrow screen", () => {
    beforeEach(() => useNarrowViewport());

    it("takes the sidebar out of the page flow behind a menu button", () => {
      renderLayout();
      expect(screen.queryByRole("navigation")).not.toBeInTheDocument();
      const toggle = screen.getByRole("button", { name: "Open navigation menu" });
      expect(toggle).toHaveAttribute("aria-expanded", "false");
      expect(toggle).toHaveAttribute("aria-haspopup", "dialog");
      expect(screen.getByText("page body")).toBeInTheDocument();
    });

    it("opens the full sidebar in a drawer without touching the saved preference", async () => {
      renderLayout();
      fireEvent.click(screen.getByRole("button", { name: "Open navigation menu" }));

      const dialog = await screen.findByRole("dialog", { name: "Navigation menu" });
      expect(within(dialog).getByRole("link", { name: "Places" })).toBeInTheDocument();
      expect(within(dialog).getByText("Coordinator Dashboard")).toBeInTheDocument();
      expect(localStorage.getItem(SIDEBAR_COLLAPSED_KEY)).toBeNull();
    });

    it("ignores a saved collapsed preference and shows labels in the drawer", async () => {
      localStorage.setItem(SIDEBAR_COLLAPSED_KEY, "true");
      renderLayout();
      fireEvent.click(screen.getByRole("button", { name: "Open navigation menu" }));
      const dialog = await screen.findByRole("dialog", { name: "Navigation menu" });
      expect(within(dialog).getByText("Places")).toBeInTheDocument();
    });

    it("closes the drawer after picking a destination", async () => {
      renderLayout();
      fireEvent.click(screen.getByRole("button", { name: "Open navigation menu" }));
      const dialog = await screen.findByRole("dialog", { name: "Navigation menu" });
      fireEvent.click(within(dialog).getByRole("link", { name: "Places" }));
      await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    });

    it("closes the drawer from its close button", async () => {
      renderLayout();
      fireEvent.click(screen.getByRole("button", { name: "Open navigation menu" }));
      const dialog = await screen.findByRole("dialog", { name: "Navigation menu" });
      fireEvent.click(within(dialog).getByRole("button", { name: "Close navigation menu" }));
      await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    });
  });
});

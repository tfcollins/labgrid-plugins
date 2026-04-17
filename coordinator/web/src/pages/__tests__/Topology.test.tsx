import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { ChakraProvider } from "@chakra-ui/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import Topology from "../Topology";

vi.mock("../../api/ws", () => ({ useWebSocket: () => undefined }));

// ReactFlow requires ResizeObserver which is not available in jsdom.
// Mock the whole reactflow module to avoid the dependency.
// Only render place nodes to avoid duplicate text (exporters share names with places in tests).
vi.mock("reactflow", () => ({
  default: ({ nodes, children }: { nodes?: Array<{ id: string; data: { label: string } }>; children?: React.ReactNode }) => (
    <div data-testid="reactflow-mock">
      {(nodes ?? []).filter((n) => n.id?.startsWith("place:")).map((n, i) => (
        <div key={i} data-testid="rf-node">{String(n.data?.label ?? "")}</div>
      ))}
      {children}
    </div>
  ),
  Background: () => null,
  Controls: () => null,
  MiniMap: () => null,
  Position: { Left: "left", Right: "right" },
  useNodesState: (initial: unknown[]) => [initial, () => {}, () => {}],
  useEdgesState: (initial: unknown[]) => [initial, () => {}, () => {}],
}));

vi.mock("../../auth/AuthContext", () => ({
  useAuth: () => ({ user: null }),
}));

vi.mock("../../hooks/usePlaces", () => ({
  usePlaces: () => ({
    data: [
      { name: "mini2", aliases: [], comment: "", tags: {},
        matches: [{ exporter: "mini2", group: "tlab", cls: "*" }],
        acquired: null, acquired_resources: [], allowed: [],
        created: 0, changed: 0, reservation: null, acquired_username: null },
      { name: "nuc", aliases: [], comment: "", tags: {},
        matches: [{ exporter: "nuc", group: "tlab", cls: "*" }],
        acquired: "alice", acquired_resources: [], allowed: [],
        created: 0, changed: 0, reservation: null, acquired_username: "alice" },
    ],
    isLoading: false,
  }),
}));

vi.mock("../../hooks/useResources", () => ({
  useExporters: () => ({
    data: [
      { name: "mini2", groups: { tlab: [
        { exporter: "mini2", group: "tlab", cls: "NetworkSerialPort", name: "serial",
          params: {}, acquired: null, avail: true },
      ] } },
      { name: "nuc", groups: { tlab: [
        { exporter: "nuc", group: "tlab", cls: "XilinxDeviceJTAG", name: "jtag",
          params: {}, acquired: null, avail: true },
      ] } },
    ],
    isLoading: false,
  }),
}));

const renderAt = (url: string) => {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <ChakraProvider>
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={[url]}>
          <Routes>
            <Route path="/topology" element={<Topology />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    </ChakraProvider>
  );
};

describe("Topology", () => {
  beforeEach(() => localStorage.clear());

  it("renders the legend with the concept rows", () => {
    renderAt("/topology");
    // Use exact matches on the legend row labels (switches contain the
    // words "exporters" / "places" too, so a regex match would collide).
    expect(screen.getByText("Exporters")).toBeInTheDocument();
    expect(screen.getByText("Groups")).toBeInTheDocument();
    expect(screen.getByText("Places (free)")).toBeInTheDocument();
    expect(screen.getByText("Places (held)")).toBeInTheDocument();
    expect(screen.getByText(/Match rules/)).toBeInTheDocument();
  });

  it("free-text filter hides non-matching nodes", () => {
    renderAt("/topology");
    const input = screen.getByPlaceholderText(/filter/i);
    fireEvent.change(input, { target: { value: "mini2" } });
    // The `nuc` node (rendered by reactflow or its mock) should disappear;
    // switch labels and other chrome don't contain the bare string "nuc".
    expect(screen.queryByText("nuc")).toBeNull();
    expect(screen.getAllByText("mini2").length).toBeGreaterThan(0);
  });

  it("?focus=place:mini2 deep-link prefills the filter", () => {
    renderAt("/topology?focus=place:mini2");
    const input = screen.getByPlaceholderText(/filter/i) as HTMLInputElement;
    expect(input.value).toBe("mini2");
  });
});

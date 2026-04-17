import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { ChakraProvider } from "@chakra-ui/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import PlaceDetail from "../PlaceDetail";

vi.mock("../../api/client", () => ({
  api: {
    getPlace: vi.fn().mockResolvedValue({
      name: "vcu118-lab1",
      aliases: [],
      comment: "",
      tags: {},
      matches: [],
      acquired: null,
      acquired_resources: [],
      allowed: [],
      created: 0,
      changed: 0,
      reservation: null,
      acquired_username: null,
    }),
    getResources: vi.fn().mockResolvedValue([
      { exporter: "lab1-host", group: "VCU118_AD9081", cls: "NetworkSerialPort",
        name: "NetworkSerialPort", params: { host: "h", port: 9000 }, acquired: null, avail: true },
    ]),
    acquirePlace: vi.fn().mockResolvedValue({ acquired: "vcu118-lab1" }),
    releasePlace: vi.fn().mockResolvedValue({ released: "vcu118-lab1" }),
  },
}));

vi.mock("../../auth/AuthContext", () => ({
  useAuth: () => ({
    user: { username: "alice", role: "user" },
    loading: false,
  }),
}));

const wrap = (ui: React.ReactNode) => {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <ChakraProvider>
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={["/places/vcu118-lab1"]}>
          <Routes>
            <Route path="/places/:name" element={ui} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    </ChakraProvider>
  );
};

describe("PlaceDetail", () => {
  beforeEach(() => vi.clearAllMocks());

  it("shows acquire button when no owner", async () => {
    render(wrap(<PlaceDetail />));
    expect(await screen.findByRole("button", { name: /acquire/i })).toBeInTheDocument();
  });

  it("calls acquirePlace on click", async () => {
    const { api } = await import("../../api/client");
    render(wrap(<PlaceDetail />));
    fireEvent.click(await screen.findByRole("button", { name: /acquire/i }));
    await waitFor(() => expect(api.acquirePlace).toHaveBeenCalledWith("vcu118-lab1"));
  });
});

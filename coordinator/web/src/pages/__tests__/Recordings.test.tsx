import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { ChakraProvider } from "@chakra-ui/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import Recordings from "../Recordings";

vi.mock("../../api/recordings", () => ({
  recordingsApi: {
    list: vi.fn().mockResolvedValue([
      { id: "abc", place_name: "vcu118", resource_name: "serial", user_id: 1,
        started_at: 1000, ended_at: 1100, byte_count: 42, terminated_reason: "normal" },
    ]),
    castUrl: (id: string) => `/api/recordings/${id}/cast`,
    delete: vi.fn(),
  },
}));

vi.mock("../../auth/AuthContext", () => ({
  useAuth: () => ({ user: { username: "alice", role: "user" }, loading: false }),
}));

const wrap = (ui: React.ReactNode) => {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <ChakraProvider>
      <QueryClientProvider client={qc}>
        <MemoryRouter>{ui}</MemoryRouter>
      </QueryClientProvider>
    </ChakraProvider>
  );
};

describe("Recordings", () => {
  beforeEach(() => vi.clearAllMocks());

  it("renders rows", async () => {
    render(wrap(<Recordings />));
    expect(await screen.findByText("vcu118")).toBeInTheDocument();
    expect(screen.getByText("serial")).toBeInTheDocument();
  });
});

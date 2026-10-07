import { fireEvent, render, screen } from "@testing-library/react";
import { ChakraProvider } from "@chakra-ui/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import Deployments from "../Deployments";
import { deploymentsApi } from "../../api/deployments";
import theme from "../../theme";

vi.mock("../../api/deployments", () => ({
  deploymentsApi: {
    list: vi.fn(),
    get: vi.fn(),
  },
}));

const summary = {
  hostname: "node-01",
  attempt: 2,
  generation: 7,
  stage: "installing",
  status: "in_progress" as const,
  progress: 42,
  ip_address: "192.0.2.10",
  mac_address: "02:00:00:00:00:01",
  first_seen: "2026-10-07T12:00:00Z",
  last_seen: "2026-10-07T12:05:00Z",
  errors: ["first boot timed out"],
};

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <ChakraProvider theme={theme}>
      <QueryClientProvider client={queryClient}>
        <Deployments />
      </QueryClientProvider>
    </ChakraProvider>,
  );
}

describe("Deployments", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(deploymentsApi.list).mockResolvedValue([summary]);
    vi.mocked(deploymentsApi.get).mockResolvedValue({
      ...summary,
      timeline: [
        {
          timestamp: "2026-10-07T12:01:00Z",
          stage: "discovery",
          status: "succeeded",
          message: "Node discovered",
          progress: 10,
        },
      ],
    });
  });

  it("renders deployment state and node identity", async () => {
    renderPage();

    expect(await screen.findByText("node-01")).toBeInTheDocument();
    expect(screen.getByText("2 / 7")).toBeInTheDocument();
    expect(screen.getByText("installing")).toBeInTheDocument();
    expect(screen.getByText("in progress")).toBeInTheDocument();
    expect(screen.getByText("42%")).toBeInTheDocument();
    expect(screen.getByText("192.0.2.10")).toBeInTheDocument();
    expect(screen.getByText("02:00:00:00:00:01")).toBeInTheDocument();
    expect(screen.getByText("first boot timed out")).toBeInTheDocument();
  });

  it("loads and expands the hostname detail timeline", async () => {
    renderPage();

    fireEvent.click(
      await screen.findByRole("button", { name: "Show details for node-01" }),
    );

    expect(deploymentsApi.get).toHaveBeenCalledWith("node-01");
    expect(await screen.findByText("Node discovered")).toBeInTheDocument();
    expect(screen.getByText("discovery")).toBeInTheDocument();
  });

  it("shows an empty state", async () => {
    vi.mocked(deploymentsApi.list).mockResolvedValue([]);
    renderPage();

    expect(
      await screen.findByText("No node deployments have been reported."),
    ).toBeInTheDocument();
  });
});
